"""
[Sub-Agent] Redis 통합 어댑터 — Store + TaskQueue + ProgressPublisher
======================================================================
책임: Redis를 통한 영속성/큐잉/이벤트 발행의 통합 구현 (3개 Port 구현)
아키텍처 위치: Adapter Layer — Outbound (Store/TaskQueue/ProgressPublisher)

구현하는 Port:
  - Store: 태스크 CRUD + Idempotency + Swarm State + 메시지 히스토리
  - TaskQueue: LPUSH/BRPOPLPUSH 기반 Reliable Queue
  - ProgressPublisher: Redis Stream 기반 SSE 이벤트 발행

Redis 키 구조:
  package:subagent:task:{task_id}                    — 태스크 상태
  package:subagent:idempotency:{request_id}          — Idempotency
  package:subagent:events:{task_id}                  — 이벤트 스트림
  package:subagent:task_queue                        — 작업 큐
  package:subagent:task_processing                   — 처리 중인 작업
  package:subagent:conversation:{session_id}         — 대화 히스토리
  package:subagent:swarm_state:{session_id}          — Swarm 상태

Reliable Queue (BRPOPLPUSH):
  - 큐잉: LPUSH
  - 디큐: BRPOPLPUSH (원자적으로 main → processing 이동)
  - ACK: LREM (processing에서 제거)
  - NACK: LREM + LPUSH (processing → main 재등록)

낙관적 락 (save_task):
  - WATCH로 감시 → GET으로 버전 확인 → MULTI/EXEC로 원자적 저장
  - 버전 충돌 시 최대 5회 재시도 (지수 백오프)
"""

import json
import asyncio
import redis.asyncio as redis
from typing import Optional, Dict, Any, List
from ...ports.interfaces import Store, TaskQueue, ProgressPublisher
from ...domain.models import AgentTask
from ...domain.enums import ProcessStatus
from ...core.config import settings
import structlog

logger = structlog.get_logger(__name__)

class RedisAdapter(Store, TaskQueue, ProgressPublisher):
    """
    Redis 통합 어댑터.
    단일 Redis 연결로 Store, TaskQueue, ProgressPublisher의 3개 Port 구현.
    """
    def __init__(self, redis_url: str):
        self.client = redis.from_url(
            redis_url, 
            decode_responses=True,
            socket_timeout=20.0,
            socket_connect_timeout=10.0
        )
        
        agent_settings = settings.agent
        prefixes = agent_settings.redis_prefixes
        
        self.base_prefix = f"{prefixes.global_prefix}:"
        self.queue_key = f"{self.base_prefix}subagent:task_queue"
        self.processing_key = f"{self.base_prefix}subagent:task_processing"
        self.task_prefix = f"{self.base_prefix}{prefixes.task}:"
        self.idempotency_prefix = f"{self.base_prefix}{prefixes.idempotency}:"
        self.event_stream_prefix = f"{self.base_prefix}{prefixes.events}:"
        self.ttl = agent_settings.redis_ttl

    # ============================================================
    # Store Port 구현
    # ============================================================

    async def check_and_reserve_idempotency(self, request_id: str, task_id: str) -> bool:
        """SET NX로 Idempotency 키 예약. 이미 존재하면 False (중복 요청)."""
        key = f"{self.idempotency_prefix}{request_id}"
        result = await self.client.set(key, task_id, nx=True, ex=self.ttl)
        return bool(result)

    async def save_task(self, task: AgentTask, max_retries: int = 5) -> None:
        """
        낙관적 락(CAS)으로 태스크 저장.
        WATCH → GET(버전 확인) → MULTI/EXEC(SET) → WatchError 재시도
        """
        key = f"{self.task_prefix}{task.task_id}"
        retries = 0
        
        while retries < max_retries:
            async with self.client.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    current_data = await pipe.get(key)
                    
                    if current_data:
                        current_task = AgentTask.model_validate_json(current_data)
                        if task.state_version < current_task.state_version:
                            logger.warning("optimistic_locking_conflict", 
                                           task_id=task.task_id, 
                                           our_version=task.state_version, 
                                           current_version=current_task.state_version)
                            raise ValueError(f"State version conflict for {task.task_id}")
                    
                    pipe.multi()
                    pipe.set(key, task.model_dump_json(), ex=self.ttl)
                    await pipe.execute()
                    return
                    
                except redis.WatchError:
                    retries += 1
                    logger.info("redis_watch_error_retrying", task_id=task.task_id, attempt=retries)
                    await asyncio.sleep(0.1 * retries)
                    continue
                except Exception as e:
                    logger.error("save_task_failed", task_id=task.task_id, error=str(e))
                    raise

        raise RuntimeError(f"Failed to save task {task.task_id} after {max_retries} attempts due to conflicts")

    async def load_task(self, task_id: str) -> Optional[AgentTask]:
        """태스크 상태 조회 (Pydantic 역직렬화)"""
        key = f"{self.task_prefix}{task_id}"
        data = await self.client.get(key)
        if data:
            try:
                return AgentTask.model_validate_json(data)
            except Exception as e:
                logger.error("task_validation_failed", task_id=task_id, error=str(e), data=data)
                raise
        return None

    async def update_task_status(self, task_id: str, status: ProcessStatus) -> None:
        """태스크 상태 업데이트 (단순 set, CAS는 상위 coordinator에서 처리)"""
        task = await self.load_task(task_id)
        if task:
            task.status = status
            await self.save_task(task)

    async def save_swarm_state(self, session_id: str, state: Dict[str, Any]) -> None:
        """Swarm(Federation) 공유 상태 저장"""
        key = f"{self.base_prefix}subagent:swarm_state:{session_id}"
        await self.client.set(key, json.dumps(state), ex=self.ttl)

    async def load_swarm_state(self, session_id: str) -> Dict[str, Any]:
        """Swarm 공유 상태 조회"""
        key = f"{self.base_prefix}subagent:swarm_state:{session_id}"
        data = await self.client.get(key)
        return json.loads(data) if data else {}

    async def save_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """대화 메시지 저장 (Redis List, RPUSH)"""
        key = f"{self.base_prefix}subagent:conversation:{session_id}"
        await self.client.rpush(key, json.dumps(message))
        await self.client.expire(key, self.ttl)

    async def get_messages(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """최근 N개 대화 메시지 조회 (LRANGE, 최신순)"""
        key = f"{self.base_prefix}subagent:conversation:{session_id}"
        data = await self.client.lrange(key, -limit, -1)
        return [json.loads(m) for m in data]

    # ============================================================
    # TaskQueue Port 구현 (Reliable Queue)
    # ============================================================

    async def enqueue(self, task_data: Dict[str, Any]) -> None:
        """작업 큐에 등록 (LPUSH → FIFO)"""
        await self.client.lpush(self.queue_key, json.dumps(task_data))

    async def dequeue(self, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        BRPOPLPUSH로 원자적 디큐.
        main queue → processing queue로 이동 (At-Least-Once 보장).
        """
        result = await self.client.brpoplpush(self.queue_key, self.processing_key, timeout=timeout)
        if result:
            return json.loads(result)
        return None

    async def ack(self, task_data: Dict[str, Any]) -> None:
        """처리 완료 → processing queue에서 제거"""
        await self.client.lrem(self.processing_key, 1, json.dumps(task_data))

    async def nack(self, task_data: Dict[str, Any]) -> None:
        """처리 실패 → processing → main queue 재등록 (재시도)"""
        msg_json = json.dumps(task_data)
        async with self.client.pipeline() as pipe:
            await pipe.lrem(self.processing_key, 1, msg_json)
            await pipe.lpush(self.queue_key, msg_json)
            await pipe.execute()

    # ============================================================
    # ProgressPublisher Port 구현 (Redis Stream)
    # ============================================================

    async def publish(
        self, 
        session_id: str, 
        task_id: str, 
        event_data: Dict[str, Any],
        trace_id: Optional[str] = None
    ) -> None:
        """진행 이벤트를 Redis Stream에 발행 (SSE 소비)"""
        stream_key = f"{self.event_stream_prefix}{task_id}"
        
        payload = {
            "session_id": session_id,
            "task_id": task_id,
            "trace_id": trace_id or event_data.get("trace_id", "unknown"),
            "event_type": event_data.get("event_type", "progress"),
            "payload": json.dumps(event_data.get("payload", {})),
            "is_replayable": "1" if event_data.get("is_replayable", True) else "0"
        }
                
        await self.client.xadd(stream_key, payload, maxlen=1000, approximate=True)
        await self.client.expire(stream_key, self.ttl)

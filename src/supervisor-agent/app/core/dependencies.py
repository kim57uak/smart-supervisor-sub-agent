from typing import Any
from fastapi import Depends
from redis.asyncio import Redis

from .config import settings
from ..infrastructure.redis.redis_client import get_redis

# Stores
from ..adapters.store.redis_stores import (
    RedisTaskStore,
    RedisExecutionSnapshotStore,
    RedisReviewStore,
    RedisGraphCheckpointStore,
    RedisConversationStore,
    RedisSwarmStateStore
)

# Adapters
from ..adapters.llm.llm_planning_service import LlmPlanningService
from ..adapters.llm.llm_compose_service import LlmResponseComposeService
from ..adapters.integration.default_a2a_invocation import DefaultA2AInvocationService
from ..adapters.orchestration.langgraph_factory import LangGraphStateGraphFactory
from ..adapters.orchestration.handoff_policy import DefaultHandoffPolicyService

# CQRS
from ..application.persistence.execution_consistency_coordinator import ExecutionConsistencyCoordinator
from ..application.persistence.supervisor_persistence_strategy_factory import PersistenceStrategyFactory
from ..application.persistence.supervisor_execution_persistence_service import SupervisorExecutionPersistenceService
from ..application.read.supervisor_read_query_factory import ReadQueryFactory
from ..application.read.supervisor_read_facade import SupervisorReadFacade

# Execution
from ..application.execution.supervisor_progress_publisher import SupervisorProgressPublisher
from ..application.execution.supervisor_graph_execution_service import SupervisorGraphExecutionService
from ..application.execution.hitl_gate_service import HitlGateService
from ..application.execution.supervisor_agent_service import SupervisorAgentService
from ..application.execution.task_queue_service import TaskQueueService

# Services
from ..services.fact_governance_service import FactGovernanceService

# Event Stream
from ..application.persistence.task_event_stream_service import TaskEventStreamService

async def get_task_store() -> RedisTaskStore:
    return RedisTaskStore()

async def get_snapshot_store() -> RedisExecutionSnapshotStore:
    return RedisExecutionSnapshotStore()

async def get_conversation_store() -> RedisConversationStore:
    return RedisConversationStore()

async def get_swarm_state_store() -> RedisSwarmStateStore:
    return RedisSwarmStateStore()

async def get_fact_service(
    swarm_state_store: RedisSwarmStateStore = Depends(get_swarm_state_store)
) -> FactGovernanceService:
    return FactGovernanceService(swarm_state_store)

async def get_event_service(redis: Redis = Depends(get_redis)) -> TaskEventStreamService:
    return TaskEventStreamService(redis)

async def get_task_queue_service(redis: Redis = Depends(get_redis)) -> TaskQueueService:
    return TaskQueueService(redis)

async def get_consistency_coordinator(
    task_store: RedisTaskStore = Depends(get_task_store),
    snapshot_store: RedisExecutionSnapshotStore = Depends(get_snapshot_store),
    swarm_state_store: RedisSwarmStateStore = Depends(get_swarm_state_store),
    redis: Redis = Depends(get_redis)
) -> ExecutionConsistencyCoordinator:
    return ExecutionConsistencyCoordinator(task_store, snapshot_store, swarm_state_store, redis)

async def get_persistence_facade(
    coordinator: ExecutionConsistencyCoordinator = Depends(get_consistency_coordinator),
    event_service: TaskEventStreamService = Depends(get_event_service)
) -> SupervisorExecutionPersistenceService:
    factory = PersistenceStrategyFactory(coordinator, event_service)
    return SupervisorExecutionPersistenceService(factory)

async def get_read_facade(
    task_store: RedisTaskStore = Depends(get_task_store),
    snapshot_store: RedisExecutionSnapshotStore = Depends(get_snapshot_store)
) -> SupervisorReadFacade:
    factory = ReadQueryFactory(task_store, snapshot_store)
    return SupervisorReadFacade(factory)

async def get_planning_service() -> LlmPlanningService:
    return LlmPlanningService()

async def get_hitl_gate_service(
    planning_service: LlmPlanningService = Depends(get_planning_service),
    persistence_facade: SupervisorExecutionPersistenceService = Depends(get_persistence_facade),
    conversation_store: RedisConversationStore = Depends(get_conversation_store)
) -> HitlGateService:
    return HitlGateService(planning_service, persistence_facade, conversation_store)

async def get_pre_hitl_a2ui_service() -> Any:
    from ..application.execution.hitl_gate_service import PreHitlA2uiService
    return PreHitlA2uiService()

async def get_invocation_service() -> DefaultA2AInvocationService:
    return DefaultA2AInvocationService()

async def get_handoff_service() -> DefaultHandoffPolicyService:
    return DefaultHandoffPolicyService()

async def get_compose_service() -> LlmResponseComposeService:
    return LlmResponseComposeService()

async def get_progress_publisher(
    event_service: TaskEventStreamService = Depends(get_event_service)
) -> SupervisorProgressPublisher:
    return SupervisorProgressPublisher(event_service)

async def get_supervisor_graph_execution_service(
    invocation_service: DefaultA2AInvocationService = Depends(get_invocation_service),
    handoff_service: DefaultHandoffPolicyService = Depends(get_handoff_service),
    progress_publisher: SupervisorProgressPublisher = Depends(get_progress_publisher),
    persistence_facade: SupervisorExecutionPersistenceService = Depends(get_persistence_facade),
    compose_service: LlmResponseComposeService = Depends(get_compose_service),
    fact_service: FactGovernanceService = Depends(get_fact_service),
    task_store: RedisTaskStore = Depends(get_task_store)
) -> SupervisorGraphExecutionService:
    graph_factory = LangGraphStateGraphFactory(invocation_service, handoff_service, progress_publisher, fact_service, task_store)
    return SupervisorGraphExecutionService(graph_factory, persistence_facade, compose_service, progress_publisher)

async def get_supervisor_agent_service(
    hitl_gate: HitlGateService = Depends(get_hitl_gate_service),
    graph_execution: SupervisorGraphExecutionService = Depends(get_supervisor_graph_execution_service),
    read_facade: SupervisorReadFacade = Depends(get_read_facade),
    persistence_facade: SupervisorExecutionPersistenceService = Depends(get_persistence_facade),
    task_queue: TaskQueueService = Depends(get_task_queue_service),
    pre_hitl_a2ui: Any = Depends(get_pre_hitl_a2ui_service)
) -> SupervisorAgentService:
    return SupervisorAgentService(hitl_gate, graph_execution, read_facade, persistence_facade, task_queue, pre_hitl_a2ui)

# Validators and Translators
from ..application.execution.supervisor_exception_translator import SupervisorExceptionTranslator
from ..services.supervisor_a2a_request_validator import SupervisorA2ARequestValidator
from ..application.execution.worker_execution_service import WorkerExecutionService

async def get_translator() -> SupervisorExceptionTranslator:
    return SupervisorExceptionTranslator()

async def get_validator() -> SupervisorA2ARequestValidator:
    return SupervisorA2ARequestValidator()

async def get_worker_execution_service() -> WorkerExecutionService:
    """
    SOLID: 워커 서비스를 위한 의존성 수동 조립 (FastAPI Depends 외부용)
    """
    from ..infrastructure.redis.redis_client import RedisClient
    redis = await RedisClient.get_client()
    
    task_queue = TaskQueueService(redis)
    event_service = TaskEventStreamService(redis)
    publisher = SupervisorProgressPublisher(event_service)
    compose_service = LlmResponseComposeService()
    
    # Graph execution 조립
    invocation_service = DefaultA2AInvocationService()
    handoff_service = DefaultHandoffPolicyService()
    
    swarm_state_store = RedisSwarmStateStore()
    fact_service = FactGovernanceService(swarm_state_store)
    
    task_store = RedisTaskStore()
    graph_factory = LangGraphStateGraphFactory(invocation_service, handoff_service, publisher, fact_service, task_store)
    
    snapshot_store = RedisExecutionSnapshotStore()
    coordinator = ExecutionConsistencyCoordinator(task_store, snapshot_store, swarm_state_store, redis)
    persistence_factory = PersistenceStrategyFactory(coordinator, event_service)
    persistence_service = SupervisorExecutionPersistenceService(persistence_factory)
    
    graph_execution = SupervisorGraphExecutionService(graph_factory, persistence_service, compose_service, publisher)
    
    return WorkerExecutionService(task_queue, graph_execution, publisher)

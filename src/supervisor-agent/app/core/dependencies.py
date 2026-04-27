from fastapi import Depends
from redis.asyncio import Redis

from .config import settings
from ..infrastructure.redis.redis_client import get_redis

# Stores
from ..adapters.store.redis_stores import (
    RedisA2ATaskStore,
    RedisReviewedExecutionSnapshotStore,
    RedisSupervisorReviewStore,
    RedisGraphCheckpointStore,
    RedisConversationStore
)

# Adapters
from ..adapters.llm.llm_planning_service import LlmSupervisorPlanningService
from ..adapters.llm.llm_compose_service import LlmSupervisorResponseComposeService
from ..adapters.integration.default_a2a_invocation import DefaultA2AInvocationService
from ..adapters.orchestration.langgraph_factory import LangGraphSupervisorStateGraphFactory

# CQRS
from ..application.persistence.execution_consistency_coordinator import ExecutionConsistencyCoordinator
from ..application.persistence.supervisor_persistence_strategy_factory import SupervisorPersistenceStrategyFactory
from ..application.persistence.supervisor_execution_persistence_service import SupervisorExecutionPersistenceService
from ..application.read.supervisor_read_query_factory import SupervisorReadQueryFactory
from ..application.read.supervisor_read_facade import SupervisorReadFacade

# Execution
from ..application.execution.supervisor_progress_publisher import SupervisorProgressPublisher
from ..application.execution.supervisor_graph_execution_service import SupervisorGraphExecutionService
from ..application.execution.hitl_gate_service import HitlGateService
from ..application.execution.supervisor_agent_service import SupervisorAgentService

# Event Stream
from ..application.persistence.task_event_stream_service import TaskEventStreamService

async def get_task_store() -> RedisA2ATaskStore:
    return RedisA2ATaskStore()

async def get_snapshot_store() -> RedisReviewedExecutionSnapshotStore:
    return RedisReviewedExecutionSnapshotStore()

async def get_event_service(redis: Redis = Depends(get_redis)) -> TaskEventStreamService:
    return TaskEventStreamService(redis)

async def get_consistency_coordinator(
    task_store: RedisA2ATaskStore = Depends(get_task_store),
    snapshot_store: RedisReviewedExecutionSnapshotStore = Depends(get_snapshot_store),
    redis: Redis = Depends(get_redis)
) -> ExecutionConsistencyCoordinator:
    return ExecutionConsistencyCoordinator(task_store, snapshot_store, redis)

async def get_persistence_facade(
    coordinator: ExecutionConsistencyCoordinator = Depends(get_consistency_coordinator),
    event_service: TaskEventStreamService = Depends(get_event_service)
) -> SupervisorExecutionPersistenceService:
    factory = SupervisorPersistenceStrategyFactory(coordinator, event_service)
    return SupervisorExecutionPersistenceService(factory)

async def get_read_facade(
    task_store: RedisA2ATaskStore = Depends(get_task_store),
    snapshot_store: RedisReviewedExecutionSnapshotStore = Depends(get_snapshot_store)
) -> SupervisorReadFacade:
    factory = SupervisorReadQueryFactory(task_store, snapshot_store)
    return SupervisorReadFacade(factory)

async def get_planning_service() -> LlmSupervisorPlanningService:
    return LlmSupervisorPlanningService()

async def get_hitl_gate_service(
    planning_service: LlmSupervisorPlanningService = Depends(get_planning_service),
    persistence_facade: SupervisorExecutionPersistenceService = Depends(get_persistence_facade)
) -> HitlGateService:
    return HitlGateService(planning_service, persistence_facade)

async def get_invocation_service() -> DefaultA2AInvocationService:
    return DefaultA2AInvocationService()

async def get_compose_service() -> LlmSupervisorResponseComposeService:
    return LlmSupervisorResponseComposeService()

async def get_progress_publisher(
    event_service: TaskEventStreamService = Depends(get_event_service)
) -> SupervisorProgressPublisher:
    return SupervisorProgressPublisher(event_service)

async def get_graph_execution_service(
    invocation_service: DefaultA2AInvocationService = Depends(get_invocation_service),
    progress_publisher: SupervisorProgressPublisher = Depends(get_progress_publisher),
    persistence_facade: SupervisorExecutionPersistenceService = Depends(get_persistence_facade),
    compose_service: LlmSupervisorResponseComposeService = Depends(get_compose_service)
) -> SupervisorGraphExecutionService:
    graph_factory = LangGraphSupervisorStateGraphFactory(invocation_service, progress_publisher)
    return SupervisorGraphExecutionService(graph_factory, persistence_facade, compose_service, progress_publisher)

async def get_supervisor_agent_service(
    hitl_gate: HitlGateService = Depends(get_hitl_gate_service),
    graph_execution: SupervisorGraphExecutionService = Depends(get_graph_execution_service),
    read_facade: SupervisorReadFacade = Depends(get_read_facade),
    persistence_facade: SupervisorExecutionPersistenceService = Depends(get_persistence_facade)
) -> SupervisorAgentService:
    return SupervisorAgentService(hitl_gate, graph_execution, read_facade, persistence_facade)

# Validators and Translators
from ..application.execution.supervisor_exception_translator import SupervisorExceptionTranslator
from ..services.supervisor_a2a_request_validator import SupervisorA2ARequestValidator

async def get_translator() -> SupervisorExceptionTranslator:
    return SupervisorExceptionTranslator()

async def get_validator() -> SupervisorA2ARequestValidator:
    return SupervisorA2ARequestValidator()



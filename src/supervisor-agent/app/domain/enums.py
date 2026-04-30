from enum import Enum


class TaskState(Enum):
    CREATED = "CREATED"
    WAITING_REVIEW = "WAITING_REVIEW"
    RUNNING = "RUNNING"
    CANCELED = "CANCELED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EventType(Enum):
    ACCEPTED = "accepted"
    PROGRESS = "progress"
    REASONING = "reasoning"
    CHUNK = "chunk"
    A2UI = "a2ui"
    DONE = "done"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class AgentRole(Enum):
    SUPERVISOR = "supervisor"
    PRODUCT = "product"
    RESERVATION = "reservation"
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class RedisNamespace(Enum):
    GLOBAL_PREFIX = "package"
    TASK = "supervisor:task"
    IDEMPOTENCY = "supervisor:idempotency"
    EVENTS = "supervisor:events"
    QUEUE = "supervisor:task_queue"


class ExecutionMode(Enum):
    SEND = "SEND"
    STREAM = "STREAM"


class Decision(Enum):
    APPROVE = "APPROVE"
    CANCEL = "CANCEL"


class ReasonCode(Enum):
    SUCCESS = "SUCCESS"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    SESSION_OWNERSHIP_MISMATCH = "SESSION_OWNERSHIP_MISMATCH"
    TASK_STATE_INVALID = "TASK_STATE_INVALID"
    SNAPSHOT_NOT_FOUND = "SNAPSHOT_NOT_FOUND"
    SNAPSHOT_EXPIRED = "SNAPSHOT_EXPIRED"
    RESUME_TOKEN_MISMATCH = "RESUME_TOKEN_MISMATCH"
    STATE_VERSION_MISMATCH = "STATE_VERSION_MISMATCH"
    REQUEST_HASH_MISMATCH = "REQUEST_HASH_MISMATCH"
    FROZEN_PLAN_HASH_MISMATCH = "FROZEN_PLAN_HASH_MISMATCH"
    PLAN_DRIFT_BLOCKED = "PLAN_DRIFT_BLOCKED"
    DUPLICATE_DECISION = "DUPLICATE_DECISION"
    ALREADY_TERMINAL = "ALREADY_TERMINAL"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"


class ApiMethod(Enum):
    """
    Standardized API methods for JSON-RPC, supporting both legacy and modern naming conventions.
    Using an Enum ensures strict adherence to known contracts and avoids magic strings.
    """
    SEND_MESSAGE = "message/send"
    SEND_MESSAGE_LEGACY = "SendMessage"
    REVIEW_DECIDE = "tasks/review/decide"
    REVIEW_DECIDE_LEGACY = "ReviewDecide"
    REVIEW_GET = "tasks/review/get"
    REVIEW_GET_LEGACY = "GetReview"
    AGENT_CARD = "agent/card"
    AGENT_CARD_LEGACY = "GetAgentCard"
    TASK_EVENTS = "tasks/events"
    TASK_EVENTS_LEGACY = "TaskEvents"


class RpcErrorCode(Enum):
    """
    Standard JSON-RPC error codes to avoid magic numbers.
    """
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    REVIEW_SNAPSHOT_NOT_FOUND = -32001


class ProcessStatus(Enum):
    """
    Internal processing statuses used to represent the workflow state.
    """
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    WAITING_REVIEW = "WAITING_REVIEW"
    STREAMING = "STREAMING"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"
    CANCELED = "CANCELED"
    A2UI_FORM_REQUIRED = "A2UI_FORM_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

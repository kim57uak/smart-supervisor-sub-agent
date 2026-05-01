from enum import Enum

class OrchestrationEngineType(Enum):
    LANGGRAPH = "LANGGRAPH"
    BURR = "BURR"


class ProcessStatus(Enum):
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_REVIEW = "WAITING_REVIEW"

class ReasonCode(Enum):
    SUCCESS = "SUCCESS"
    IDEMPOTENCY_HIT = "IDEMPOTENCY_HIT"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    SNAPSHOT_NOT_FOUND = "SNAPSHOT_NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"

class EventType(Enum):
    PLANNING = "PLANNING"
    EXECUTING_TOOL = "EXECUTING_TOOL"
    TOOL_RESULT = "TOOL_RESULT"
    COMPOSING = "COMPOSING"
    CHUNK = "CHUNK"
    PROGRESS = "PROGRESS"
    DONE = "DONE"
    ERROR = "ERROR"

class AgentRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class RedisNamespace(Enum):
    GLOBAL_PREFIX = "package"
    TASK = "subagent:task"
    IDEMPOTENCY = "subagent:idempotency"
    EVENTS = "subagent:events"
    QUEUE = "subagent:task_queue"

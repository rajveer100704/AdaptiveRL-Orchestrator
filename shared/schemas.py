from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime, timezone
from enum import Enum

def now_utc():
    return datetime.now(timezone.utc)

class RequestState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    RETRYING = "RETRYING"

class WorkerState(str, Enum):
    PROVISIONING = "PROVISIONING"
    WARMING = "WARMING"
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    TERMINATED = "TERMINATED"

class InferenceRequest(BaseModel):
    request_id: UUID = Field(default_factory=uuid4)
    model_name: Optional[str] = None
    payload: Dict[str, Any]
    enqueue_timestamp: datetime = Field(default_factory=now_utc)
    
class RoutingDecision(BaseModel):
    selected_worker: str
    routing_reason: str
    queue_name: str
    policy_version: str
    exploration_used: bool = False
    epsilon_value: Optional[float] = None
    policy_confidence: Optional[float] = None
    action_probability: Optional[float] = None
    shadow_action: Optional[str] = None
    routing_cost: Optional[float] = None
    quality_degradation: Optional[float] = None
    
class WorkerResult(BaseModel):
    request_id: UUID
    worker_id: str
    result: Dict[str, Any]
    status: RequestState
    processing_time_ms: float
    queue_wait_ms: float
    timestamp: datetime = Field(default_factory=now_utc)
    failure_reason: Optional[str] = None
    is_cold_start: bool = False
    degradation: Optional[float] = None

class InferenceResponse(BaseModel):
    request_id: UUID
    routing: RoutingDecision
    worker_result: Optional[WorkerResult] = None
    status: str
    total_latency_ms: float
    error: Optional[str] = None

class WorkerHeartbeat(BaseModel):
    worker_id: str
    status: str
    state: WorkerState = WorkerState.ACTIVE
    active_requests: int
    max_concurrency: int
    avg_latency_ms: float
    timestamp: datetime = Field(default_factory=now_utc)
    loaded_models: Optional[list[str]] = Field(default_factory=list)

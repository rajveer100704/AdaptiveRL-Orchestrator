from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from shared.database import Base
import uuid
import datetime

class RoutingDecisionRecord(Base):
    __tablename__ = "routing_decisions"

    request_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    policy_version = Column(String, nullable=False)
    selected_worker = Column(String, nullable=True)
    queue_name = Column(String, nullable=True)
    request_type = Column(String, nullable=True)
    
    # Event Timeline
    received_at = Column(DateTime, nullable=True)
    enqueued_at = Column(DateTime, nullable=True)
    dequeued_at = Column(DateTime, nullable=True)
    started_processing_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Latency Breakdown
    queue_wait_ms = Column(Float, nullable=True)
    processing_ms = Column(Float, nullable=True)
    total_latency_ms = Column(Float, nullable=True)
    
    retry_count = Column(Integer, default=0)
    outcome = Column(String, nullable=False)  # PENDING, SUCCESS, FAILED, TIMEOUT, RETRYING
    failure_reason = Column(String, nullable=True)
    
    # State tracking for RL
    queue_depth = Column(Integer, nullable=True)
    worker_load = Column(Float, nullable=True)
    
    # Exploration metadata
    exploration_used = Column(Boolean, default=False)
    epsilon_value = Column(Float, nullable=True)
    policy_confidence = Column(Float, nullable=True)
    action_probability = Column(Float, nullable=True)
    
    # Phase 3 Fields
    shadow_action = Column(String, nullable=True)
    routing_cost = Column(Float, nullable=True)
    quality_degradation = Column(Float, nullable=True)
    is_cold_start = Column(Boolean, nullable=True)

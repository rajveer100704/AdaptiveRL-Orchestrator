from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    postgres_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/orchestrator"
    redis_url: str = "redis://localhost:6379/0"
    gateway_port: int = 8000
    gateway_timeout_ms: int = 5000
    worker_timeout_ms: int = 2000
    max_retries: int = 3
    retry_backoff_base_ms: int = 100
    worker_heartbeat_interval_s: int = 5
    worker_heartbeat_timeout_s: int = 15
    max_queue_depth: int = 1000
    
    # Worker config (if running as worker)
    worker_id: str = "default_worker"
    worker_queue: str = "default_queue"
    worker_type: str = "cpu"  # cpu, gpu, quantized
    worker_base_latency_ms: int = 50
    worker_max_concurrency: int = 10
    worker_cost_per_request: float = 0.01
    worker_memory_budget_mb: int = 8000
    worker_quantization_degradation: float = 0.0
    
    # Fault Injection Simulation
    worker_failure_probability: float = 0.0
    worker_stall_probability: float = 0.0
    worker_crash_probability: float = 0.0
    
    # Autoscaling Configs
    provisioning_delay_s: int = 30
    warmup_delay_s: int = 15
    minimum_runtime_s: int = 60
    cooldown_window_s: int = 30
    max_spawn_rate: int = 2
    spawn_cost_dollars: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

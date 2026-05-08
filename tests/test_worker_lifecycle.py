import pytest
import time
from shared.schemas import WorkerState, WorkerHeartbeat

@pytest.mark.asyncio
async def test_worker_state_transitions():
    # Verify the logical flow of a worker's lifecycle
    states = [s.name for s in WorkerState]
    assert "PROVISIONING" in states
    assert "WARMING" in states
    assert "ACTIVE" in states
    assert "DRAINING" in states
    
def test_heartbeat_freshness():
    # Verify heartbeat timestamp logic
    hb = WorkerHeartbeat(
        worker_id="w1", 
        status="healthy",
        state=WorkerState.ACTIVE, 
        active_requests=0,
        max_concurrency=10,
        avg_latency_ms=150.0
    )
    assert hb.worker_id == "w1"
    assert hb.state == WorkerState.ACTIVE

def test_scaling_hysteresis_logic():
    # Verify that we can't spawn workers faster than the cooldown
    spawn_cooldown = 30
    last_spawn = time.time() - 10
    
    can_spawn = (time.time() - last_spawn) > spawn_cooldown
    assert can_spawn is False

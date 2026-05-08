import pytest
import asyncio
from unittest.mock import AsyncMock
from routing.baselines import LeastLoadedRouter, RandomRouter
from shared.schemas import InferenceRequest

@pytest.mark.asyncio
async def test_least_loaded_router_logic(mocker):
    # Mock redis and static_router
    mocker.patch('routing.static_router.static_router.get_healthy_queues', 
                 new_callable=AsyncMock, 
                 return_value=set(["queue_cpu", "queue_gpu"]))
    
    async def mock_depth(q):
        return 10 if q == "queue_cpu" else 2
        
    mocker.patch('broker.redis_manager.redis_manager.get_queue_depth', side_effect=mock_depth)
    
    router = LeastLoadedRouter()
    request = InferenceRequest(payload={"text": "test"}, model_name="tiny")
    
    decision = await router.route(request)
    
    # Should pick queue_gpu
    assert decision.queue_name == "queue_gpu"
    assert "Least Loaded" in decision.routing_reason

@pytest.mark.asyncio
async def test_random_router_logic(mocker):
    mocker.patch('routing.static_router.static_router.get_healthy_queues', 
                 new_callable=AsyncMock, 
                 return_value=set(["queue_cpu"]))
    
    router = RandomRouter()
    request = InferenceRequest(payload={"text": "test"}, model_name="tiny")
    
    decision = await router.route(request)
    assert decision.queue_name == "queue_cpu"
    assert decision.routing_reason == "Random"

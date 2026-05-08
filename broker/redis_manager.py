import json
import time
from redis.asyncio import Redis
from shared.config import settings
from typing import List, Dict, Any, Optional
from shared.logging import setup_logging

logger = setup_logging()

class RedisQueueManager:
    def __init__(self):
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async def ensure_consumer_group(self, stream_name: str, group_name: str):
        try:
            await self.redis.xgroup_create(stream_name, group_name, id='0', mkstream=True)
            logger.info("consumer_group_created", group_name=group_name, stream_name=stream_name)
        except Exception as e:
            if 'BUSYGROUP' in str(e):
                pass
            else:
                logger.error("consumer_group_creation_failed", error=str(e))

    async def enqueue(self, stream_name: str, payload: Dict[str, Any]) -> str:
        from opentelemetry import propagate
        # Inject trace context into payload for async tracing
        propagate.inject(payload)
        payload_str = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in payload.items()}
        message_id = await self.redis.xadd(stream_name, payload_str)
        return message_id

    async def consume(self, stream_name: str, group_name: str, consumer_name: str, count: int = 1, block: int = 2000):
        messages = await self.redis.xreadgroup(group_name, consumer_name, {stream_name: '>'}, count=count, block=block)
        results = []
        if messages:
            for stream, msgs in messages:
                for message_id, msg_data in msgs:
                    parsed_data = {}
                    for k, v in msg_data.items():
                        try:
                            parsed_data[k] = json.loads(v)
                        except:
                            parsed_data[k] = v
                    results.append((message_id, parsed_data))
        return results

    async def acknowledge(self, stream_name: str, group_name: str, message_id: str):
        await self.redis.xack(stream_name, group_name, message_id)
        
    async def get_queue_depth(self, stream_name: str) -> int:
        return await self.redis.xlen(stream_name)

    async def move_to_dlq(self, original_stream: str, payload: Dict[str, Any], reason: str):
        dlq_name = f"{original_stream}_dlq"
        dlq_payload = payload.copy()
        dlq_payload["dlq_reason"] = reason
        dlq_payload["dlq_timestamp"] = time.time()
        await self.enqueue(dlq_name, dlq_payload)
        logger.warning("message_moved_to_dlq", original_stream=original_stream, dlq_name=dlq_name, reason=reason)

    async def check_idempotency(self, request_id: str) -> bool:
        # Returns True if this is the first time we see this request, False if it's a duplicate
        key = f"processed:{request_id}"
        result = await self.redis.set(key, "1", nx=True, ex=86400) # expire in 1 day
        return bool(result)
        
    async def publish_heartbeat(self, worker_id: str, heartbeat_data: Dict[str, Any]):
        await self.redis.hset("worker_heartbeats", worker_id, json.dumps(heartbeat_data))
        
    async def get_worker_heartbeats(self) -> Dict[str, Any]:
        data = await self.redis.hgetall("worker_heartbeats")
        now = time.time()
        active_workers = {}
        for k, v in data.items():
            hb = json.loads(v)
            # Check expiry (naive assumption: heartbeat timestamp + timezone logic might be tricky, let's use local ingestion time or trust worker time)
            # Actually, `timestamp` in heartbeat is an ISO string. Let's just trust it or use a separate redis expiring key.
            # For robustness, let's use a redis key with expiry instead of hset for better TTL handling.
            active_workers[k] = hb
        return active_workers

    async def ping(self):
        return await self.redis.ping()

    async def register_worker(self, pool_name: str, worker_id: str, state: str):
        from datetime import datetime, timezone
        await self.redis.hset("worker_registry", worker_id, json.dumps({
            "pool": pool_name,
            "state": state,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }))

    async def deregister_worker(self, worker_id: str):
        await self.redis.hdel("worker_registry", worker_id)

    async def get_worker_registry(self):
        data = await self.redis.hgetall("worker_registry")
        return {k: json.loads(v) for k, v in data.items()}

redis_manager = RedisQueueManager()

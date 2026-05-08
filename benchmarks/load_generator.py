import asyncio
import httpx
import time
import sys
import random
import numpy as np

MODELS = ["model_tiny", "model_medium", "model_large", "default"]
ZIPF_PROBS = [0.5, 0.3, 0.1, 0.1]
GATEWAY_URL = "http://localhost:8000"

async def send_request(client: httpx.AsyncClient):
    payload = {
        "text": f"Simulated request {random.randint(1000, 9999)}",
        "complexity": random.uniform(0.1, 0.9),
        "model_name": np.random.choice(MODELS, p=ZIPF_PROBS)
    }
    start = time.time()
    try:
        response = await client.post(f"{GATEWAY_URL}/infer", json=payload, headers={"x-routing-policy": "ppo_v2"}, timeout=10.0)
        return response.status_code, time.time() - start
    except Exception as e:
        return 500, time.time() - start

async def run_scenario(scenario: str, total_requests: int):
    print(f"Starting scenario: {scenario} ({total_requests} requests)")
    
    if scenario == "burst":
        concurrency = 100
        complexity_ratio = 0.5
    elif scenario == "failure_storm":
        concurrency = 20
        # Target only the large worker which we could configure with high failure rate
        complexity_ratio = 0.0 
    else: # normal
        concurrency = 10
        complexity_ratio = 0.5
        
    async with httpx.AsyncClient() as client:
        tasks = []
        latencies = []
        successes = 0
        failures = 0
        
        start_time = time.time()
        for i in range(total_requests):
            tasks.append(send_request(client))
            
            if len(tasks) >= concurrency:
                results = await asyncio.gather(*tasks)
                for status, latency in results:
                    latencies.append(latency)
                    if status == 200:
                        successes += 1
                    else:
                        failures += 1
                tasks = []
                
        if tasks:
            results = await asyncio.gather(*tasks)
            for status, latency in results:
                latencies.append(latency)
                if status == 200:
                    successes += 1
                else:
                    failures += 1
                    
        total_time = time.time() - start_time
        
    latencies.sort()
    p50 = latencies[int(len(latencies)*0.5)] if latencies else 0
    p95 = latencies[int(len(latencies)*0.95)] if latencies else 0
    
    print("\n--- Benchmark Results ---")
    print(f"Scenario: {scenario}")
    print(f"Successes: {successes}")
    print(f"Failures: {failures}")
    print(f"Total Time: {total_time:.2f}s")
    print(f"Throughput: {total_requests/total_time:.2f} req/s")
    print(f"p50 Latency: {p50*1000:.2f}ms")
    print(f"p95 Latency: {p95*1000:.2f}ms")

if __name__ == "__main__":
    scenario = sys.argv[1] if len(sys.argv) > 1 else "normal"
    requests = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    asyncio.run(run_scenario(scenario, requests))

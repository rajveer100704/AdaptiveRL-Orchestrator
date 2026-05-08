from prometheus_client import Counter, Histogram, Gauge

# Gateway Metrics
REQUEST_COUNT = Counter('gateway_requests_total', 'Total inference requests received')
ROUTING_DECISIONS = Counter('gateway_routing_decisions_total', 'Routing decisions made', ['target_queue', 'policy_version'])
REQUEST_LATENCY = Histogram('gateway_request_latency_seconds', 'End-to-end request latency in seconds', ['outcome'])
ACTIVE_REQUESTS = Gauge('gateway_active_requests', 'Number of requests currently being processed')
REQUEST_FAILURES = Counter('gateway_request_failures_total', 'Total failed requests', ['reason'])

# Queue Metrics
QUEUE_DEPTH = Gauge('queue_depth', 'Current depth of the queue', ['queue_name'])
DEAD_LETTER_COUNT = Counter('queue_dead_letters_total', 'Messages moved to dead letter queue', ['queue_name'])

# Worker Metrics
WORKER_TASKS_PROCESSED = Counter('worker_tasks_processed_total', 'Tasks processed by worker', ['worker_id', 'status'])
WORKER_QUEUE_WAIT_TIME = Histogram('worker_queue_wait_time_seconds', 'Time spent waiting in queue', ['worker_id', 'queue_name'])
WORKER_PROCESSING_TIME = Histogram('worker_processing_time_seconds', 'Worker task processing time in seconds', ['worker_id'])
WORKER_ACTIVE_TASKS = Gauge('worker_active_tasks', 'Tasks currently being processed by worker', ['worker_id'])

# Capacity & Economic Metrics
INFRA_COST = Counter('infra_cost_dollars_total', 'Accumulated infrastructure cost in dollars', ['pool_type'])
SCALE_EVENTS = Counter('infra_scale_events_total', 'Total scaling actions taken', ['pool_type', 'action'])
WARM_HIT_RATIO = Gauge('infra_warm_hit_ratio', 'Ratio of requests served by warm cache', ['pool_type'])
PROVISIONING_WORKERS = Gauge('infra_provisioning_workers', 'Number of workers currently in provisioning state', ['pool_type'])

# Performance Distribution
LATENCY_P95 = Histogram('request_latency_seconds', 'Latency distribution for p95 analysis', 
                        ['policy_type', 'pool_type'], buckets=(.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0, float("inf")))



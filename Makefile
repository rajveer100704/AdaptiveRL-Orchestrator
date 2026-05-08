.PHONY: setup train eval run clean

setup:
	@echo "Setting up environment..."
	uv venv
	uv sync

train:
	@echo "Training Routing and Capacity models..."
	$env:PYTHONPATH="."; uv run python rl/train.py
	$env:PYTHONPATH="."; uv run python rl/train_capacity.py

eval:
	@echo "Running rigorous benchmark suite (PPO vs Heuristics)..."
	@echo "1. Evaluating PPO Routing..."
	$env:PYTHONPATH="."; uv run python benchmarks/evaluate_temporal.py ppo_v2
	@echo "2. Evaluating LeastLoaded Heuristic..."
	$env:PYTHONPATH="."; uv run python benchmarks/evaluate_temporal.py least_loaded_v1
	@echo "3. Generating Telemetry-Driven Visualizations..."
	$env:PYTHONPATH="."; uv run python benchmarks/visualize_results.py
	@echo "Benchmark complete. Results in docs/images/"


run:
	@echo "Starting full Control Plane..."
	docker compose -f docker/docker-compose.yml up -d --build
	@echo "Services started:"
	@echo " - Gateway: http://localhost:8000"
	@echo " - Grafana: http://localhost:3000"
	@echo " - Jaeger: http://localhost:16686"
	@echo " - Prometheus: http://localhost:9090"

stop:
	@echo "Stopping services..."
	docker compose -f docker/docker-compose.yml down

clean:
	@echo "Cleaning up logs and artifacts..."
	rm -rf logs/ models/*.zip benchmarks/*.json

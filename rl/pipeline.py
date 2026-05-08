import numpy as np
from stable_baselines3 import PPO
from rl.capacity_environment import CapacitySimulationEnv
from shared.logging import setup_logging

logger = setup_logging()

def evaluate_capacity_policy(model_path: str, env: CapacitySimulationEnv, episodes: int = 3):
    try:
        model = PPO.load(model_path)
    except Exception as e:
        logger.error("model_load_failed", path=model_path, error=str(e))
        return None
        
    metrics = {
        "reward": [],
        "cost": [],
        "timeouts": [],
        "oscillations": []
    }
    
    for _ in range(episodes):
        obs, _ = env.reset()
        done = False
        ep_reward = 0
        ep_cost = 0
        ep_timeouts = 0
        ep_oscillations = 0
        
        last_action = None
        
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            
            if last_action is not None:
                for i in range(3):
                    if last_action[i] != 1 and action[i] != 1 and last_action[i] != action[i]:
                        ep_oscillations += 1
                        
            last_action = action
            
            obs, reward, terminated, truncated, info = env.step(action)
            ep_reward += reward
            
            # Re-calculating some metrics here because env doesn't return them directly
            # but we can infer from negative reward components roughly or modify env to return info dict.
            # Let's keep it simple: total reward is the primary holistic metric.
            done = terminated or truncated
            
        metrics["reward"].append(ep_reward)
        metrics["oscillations"].append(ep_oscillations)
        
    return {
        "mean_reward": np.mean(metrics["reward"]),
        "mean_oscillations": np.mean(metrics["oscillations"])
    }

def run_regression_pipeline(active_path: str, candidate_path: str):
    logger.info("starting_regression_pipeline", active=active_path, candidate=candidate_path)
    env = CapacitySimulationEnv(max_steps=600)
    
    active_metrics = evaluate_capacity_policy(active_path, env)
    candidate_metrics = evaluate_capacity_policy(candidate_path, env)
    
    if not candidate_metrics:
        logger.error("candidate_evaluation_failed")
        return False
        
    if not active_metrics:
        logger.warning("no_active_policy_found_promoting_candidate")
        return True
        
    logger.info("evaluation_results", active=active_metrics, candidate=candidate_metrics)
    
    # Promotion criteria:
    # 1. Mean reward must be better or equal
    # 2. Oscillations should not be wildly worse (e.g. not > 50% more)
    
    reward_improved = candidate_metrics["mean_reward"] >= active_metrics["mean_reward"]
    oscillation_stable = candidate_metrics["mean_oscillations"] <= (active_metrics["mean_oscillations"] * 1.5 + 5)
    
    if reward_improved and oscillation_stable:
        logger.info("policy_promoted", reason="metrics_improved_or_stable")
        return True
    else:
        logger.warning("policy_rejected", reason="regression_detected")
        return False

if __name__ == "__main__":
    import shutil
    import os
    
    active = "models/ppo_capacity_v1.zip"
    candidate = "models/ppo_capacity_candidate.zip"
    
    # Dummy creation for test if candidate doesn't exist
    if not os.path.exists(candidate) and os.path.exists(active):
        shutil.copy(active, candidate)
        
    promoted = run_regression_pipeline(active, candidate)
    
    if promoted and os.path.exists(candidate):
        shutil.copy(candidate, active)
        logger.info("deployment_successful", active_model=active)

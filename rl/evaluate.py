import numpy as np
from stable_baselines3 import PPO
from rl.environment import InferenceSimulationEnv

def evaluate_random(env, episodes=5):
    total_rewards = []
    for _ in range(episodes):
        obs, _ = env.reset()
        done = False
        episode_reward = 0
        while not done:
            action = env.action_space.sample()
            obs, reward, terminated, truncated, _ = env.step(action)
            episode_reward += reward
            done = terminated or truncated
        total_rewards.append(episode_reward)
    return np.mean(total_rewards)

def evaluate_least_loaded(env, episodes=5):
    total_rewards = []
    for _ in range(episodes):
        obs, _ = env.reset()
        done = False
        episode_reward = 0
        while not done:
            # obs[5], obs[6], obs[7] are queue depths
            depths = [obs[5], obs[6], obs[7]]
            action = np.argmin(depths)
            obs, reward, terminated, truncated, _ = env.step(action)
            episode_reward += reward
            done = terminated or truncated
        total_rewards.append(episode_reward)
    return np.mean(total_rewards)

def evaluate_ppo(env, model, episodes=5):
    total_rewards = []
    for _ in range(episodes):
        obs, _ = env.reset()
        done = False
        episode_reward = 0
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            action = int(action)
            obs, reward, terminated, truncated, _ = env.step(action)
            episode_reward += reward
            done = terminated or truncated
        total_rewards.append(episode_reward)
    return np.mean(total_rewards)

if __name__ == "__main__":
    env = InferenceSimulationEnv(max_steps=1000)
    
    print("Evaluating Random Router...")
    r_reward = evaluate_random(env)
    
    print("Evaluating Least Loaded Router...")
    ll_reward = evaluate_least_loaded(env)
    
    print("Evaluating PPO Router...")
    try:
        model = PPO.load("models/ppo_v2.zip")
        ppo_reward = evaluate_ppo(env, model)
    except FileNotFoundError:
        print("PPO model not found. Run rl/train.py first.")
        ppo_reward = float('-inf')
        
    print("\n--- Evaluation Results (Total Reward over 1000 steps) ---")
    print(f"Random Router:       {r_reward:.2f}")
    print(f"Least Loaded Router: {ll_reward:.2f}")
    print(f"PPO Router (v2):     {ppo_reward:.2f}")

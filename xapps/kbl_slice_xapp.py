#!/usr/bin/env python3
"""
KBL (Kernel-Based Reinforcement Learning) online slice-aware DL-PRB allocator xApp.
Based on: "Model-Based Reinforcement Learning With Kernels for Resource Allocation in RAN Slices"

Different from PPO: KBL is model-based RL using kernel methods for online learning.
It maintains a model of the environment (transition and reward functions) using
kernel regression, then uses this model to plan optimal actions.

MDP (same as PPO):
  state  (6 floats): [sat_C, sat_P, sat_B, cqi_C, cqi_P, cqi_B]
  action (6 discrete): per-slice DL PRB min-ratio profile (sum=100)
  reward: 0.6*min(sat_C,1)+0.3*min(sat_P,1)+0.1*min(sat_B,1) - penalty*[sat_C<1]

KBL-specific features:
  - Maintains a buffer of (state, action, next_state, reward) transitions
  - Uses kernel regression (Gaussian RBF kernel) to approximate:
    a) Transition function: P(s'|s,a) 
    b) Reward function: R(s,a)
  - Uses fitted Q-iteration or MPC for action selection
  - Online learning with incremental updates
"""
import argparse, signal, json, threading, time, datetime, os
import numpy as np
from collections import deque
from sklearn.kernel_ridge import KernelRidge
from sklearn.metrics.pairwise import rbf_kernel
from lib.xAppBase import xAppBase

# ----------------------------- configuration --------------------------------
WS_URL  = "10.0.2.1:8002"
E2_NODE = "gnbd_001_001_00000213_1"
SLICES  = ["CRITICAL", "PERFORMANCE", "BUSINESS"]

SLA_DL = {"CRITICAL": 9_000_000, "PERFORMANCE": 8_000_000, "BUSINESS": 25_000_000}

# 6 discrete DL PRB min-ratio profiles, [CRITICAL, PERFORMANCE, BUSINESS], sum=100
PROFILES = [
    [34, 33, 33],   # 0 balanced
    [60, 25, 15],   # 1 favor CRITICAL
    [25, 60, 15],   # 2 favor PERFORMANCE
    [15, 25, 60],   # 3 favor BUSINESS
    [45, 45, 10],   # 4 protect CRITICAL+PERFORMANCE
    [10, 10, 80],   # 5 max BUSINESS throughput
]
N_ACT, N_OBS = len(PROFILES), 6
W = np.array([0.6, 0.3, 0.1])
CRIT_PENALTY = 0.3
CRIT_MIN_FLOOR = 30

# KBL hyper-parameters
BUFFER_SIZE = 1000                    # Max transitions to store
GAMMA = 0.99                          # Discount factor
HORIZON = 5                           # Planning horizon for MPC
KERNEL_GAMMA = 0.5                    # RBF kernel parameter
ALPHA = 1e-6                          # Regularization parameter for kernel ridge
UPDATE_INTERVAL = 10                  # Update model every N steps
CKPT_DEFAULT = "/tmp/kbl_slice.pt"
TRAIN_LOG = "/tmp/kbl_train_log.csv"
PRB_FILE = "/tmp/prb_decisions.json"

# ----------------------------- KBL Implementation ----------------------------
class KBL:
    def __init__(self, train=True, ckpt=CKPT_DEFAULT):
        self.train_mode = train
        self.ckpt = ckpt
        
        # Experience buffer
        self.buffer = deque(maxlen=BUFFER_SIZE)
        
        # Kernel ridge regression models
        # We need to model: P(s'|s,a) - we'll use KRR to predict next state
        # For each state dimension, we have a separate KRR model
        self.transition_models = [KernelRidge(alpha=ALPHA, kernel='rbf', gamma=KERNEL_GAMMA) 
                                  for _ in range(N_OBS)]
        
        # Reward model: R(s,a) - one KRR model predicting reward
        self.reward_model = KernelRidge(alpha=ALPHA, kernel='rbf', gamma=KERNEL_GAMMA)
        
        # State for storing previous transitions for training
        self.last_transition = None
        
        self.step_count = 0
        self.update_idx = 0
        
        # For planning
        self.planning_horizon = HORIZON
        
        if os.path.exists(ckpt):
            self.load(ckpt)
            print(f"[KBL] loaded checkpoint {ckpt}")
            
        if train and not os.path.exists(TRAIN_LOG):
            with open(TRAIN_LOG, "w") as f:
                f.write("ts,update,mean_reward,model_error\n")

    def _get_feature_vector(self, state, action):
        """Combine state and action into a feature vector."""
        # One-hot encode action
        action_onehot = np.zeros(N_ACT)
        action_onehot[action] = 1
        return np.concatenate([state, action_onehot])

    def store_transition(self, state, action, next_state, reward):
        """Store a transition in the buffer."""
        self.buffer.append((state.copy(), action, next_state.copy(), reward))
        self.last_transition = (state, action, next_state, reward)
        self.step_count += 1

    def train(self):
        """Train the kernel models on the buffer."""
        if len(self.buffer) < 50:  # Need minimum samples
            return None
            
        # Prepare training data
        X = []
        y_next_state = [[] for _ in range(N_OBS)]
        y_reward = []
        
        for state, action, next_state, reward in self.buffer:
            feat = self._get_feature_vector(state, action)
            X.append(feat)
            for i in range(N_OBS):
                y_next_state[i].append(next_state[i])
            y_reward.append(reward)
        
        X = np.array(X)
        
        # Train transition models (one per state dimension)
        for i in range(N_OBS):
            y = np.array(y_next_state[i])
            self.transition_models[i].fit(X, y)
        
        # Train reward model
        self.reward_model.fit(X, np.array(y_reward))
        
        # Compute model error (for logging)
        pred_reward = self.reward_model.predict(X)
        mse = np.mean((np.array(y_reward) - pred_reward) ** 2)
        
        return mse

    def predict_next_state(self, state, action):
        """Predict next state given current state and action."""
        feat = self._get_feature_vector(state, action).reshape(1, -1)
        next_state = np.zeros(N_OBS)
        for i in range(N_OBS):
            next_state[i] = self.transition_models[i].predict(feat)[0]
        return next_state

    def predict_reward(self, state, action):
        """Predict reward given current state and action."""
        feat = self._get_feature_vector(state, action).reshape(1, -1)
        return self.reward_model.predict(feat)[0]

    def plan_action(self, state, mask):
        """
        Use Model Predictive Control (MPC) to select the best action.
        Simulates HORIZON steps ahead using the learned models.
        """
        # If we don't have enough data, use exploration
        if len(self.buffer) < 50:
            # Random action from valid ones
            valid_actions = np.where(mask)[0]
            return int(np.random.choice(valid_actions))
        
        best_action = 0
        best_value = -float('inf')
        
        # For each valid action, simulate HORIZON steps
        for action in range(N_ACT):
            if not mask[action]:
                continue
                
            # Simulate from current state
            sim_state = state.copy()
            total_reward = 0.0
            current_action = action
            
            for t in range(self.planning_horizon):
                # Predict reward
                reward = self.predict_reward(sim_state, current_action)
                total_reward += (GAMMA ** t) * reward
                
                # Predict next state
                sim_state = self.predict_next_state(sim_state, current_action)
                
                # Clip to valid ranges
                sim_state = np.clip(sim_state, 0, 1.5)
                
                # Pick best action for next step (greedy over valid actions)
                # For simplicity, we'll use the current action for the whole horizon
                # In a more sophisticated version, we'd do full tree search
                # Here we just continue with the same action
            
            # Add terminal value (approximate)
            terminal_value = self.predict_reward(sim_state, 0) * (GAMMA ** self.planning_horizon)
            total_reward += terminal_value
            
            if total_reward > best_value:
                best_value = total_reward
                best_action = action
        
        return best_action

    def select(self, obs_np, mask_np):
        """Select action using the KBL model."""
        if self.train_mode:
            # In training, use MPC for action selection
            action = self.plan_action(obs_np, mask_np)
            # Add some exploration (epsilon-greedy)
            if np.random.random() < 0.05:  # 5% exploration
                valid_actions = np.where(mask_np)[0]
                action = int(np.random.choice(valid_actions))
            return action, 0.0, 0.0
        else:
            # In eval, use greedy MPC
            action = self.plan_action(obs_np, mask_np)
            return action, 0.0, 0.0

    def store(self, obs, act, logp, val, mask, rew):
        """Store transition for training."""
        # We'll store the transition in the buffer when we get the next state
        pass

    def maybe_update(self, last_val, update_idx):
        """Train the model if enough data is available."""
        if not self.train_mode or len(self.buffer) < 50:
            return None
            
        # Train every UPDATE_INTERVAL steps
        if self.step_count % UPDATE_INTERVAL == 0:
            mse = self.train()
            if mse is not None:
                self.update_idx += 1
                self.save(self.ckpt)
                
                # Log training progress
                mean_reward = np.mean([t[3] for t in list(self.buffer)[-ROLLOUT:]])
                with open(TRAIN_LOG, "a") as f:
                    f.write(f"{datetime.datetime.now():%H:%M:%S},{self.update_idx},{mean_reward:.4f},{mse:.4f}\n")
                return mean_reward, 0.0, 0.0, mse
        return None

    def save(self, path):
        """Save the model to disk."""
        import pickle
        model_data = {
            'transition_models': self.transition_models,
            'reward_model': self.reward_model,
            'buffer': self.buffer
        }
        with open(path, 'wb') as f:
            pickle.dump(model_data, f)

    def load(self, path):
        """Load the model from disk."""
        import pickle
        try:
            with open(path, 'rb') as f:
                model_data = pickle.load(f)
                self.transition_models = model_data['transition_models']
                self.reward_model = model_data['reward_model']
                self.buffer = model_data['buffer']
        except:
            print(f"[KBL] Could not load checkpoint, starting fresh")

# ------------------------------ the xApp ------------------------------------
class KBLXApp(xAppBase):
    def __init__(self, c, h, r, interval, kbl):
        super().__init__(c, h, r)
        self.interval = interval
        self.kbl = kbl
        self.m = {}
        self.lock = threading.Lock()
        self.update_idx = 0
        self.prev = None     # (obs, act, logp, val, mask) awaiting reward
        self._ws()

    def _ws(self):
        import websocket
        def on_open(ws):
            ws.send(json.dumps({"cmd": "metrics_subscribe"})); print("[WS] subscribed 8002")
        def on_msg(ws, msg):
            try:
                d = json.loads(msg)
                if "cells" not in d: return
                for cell in d["cells"]:
                    for ue in cell.get("ue_list", []):
                        r = ue.get("rnti")
                        if not r: continue
                        with self.lock:
                            self.m[r] = {"cqi": ue.get("cqi", 1), "sd": ue.get("slice_sd", 3),
                                         "node": ue.get("e2_node", E2_NODE), "f1ap": ue.get("f1ap", 0),
                                         "dl": ue.get("dl_brate", 0), "ts": time.time()}
            except: pass
        def th():
            ws = websocket.WebSocketApp("ws://" + WS_URL, on_open=on_open, on_message=on_msg)
            while ws.run_forever(): time.sleep(1)
        threading.Thread(target=th, daemon=True).start()

    def _slice_of(self, sd):
        return {1: "CRITICAL", 2: "PERFORMANCE", 3: "BUSINESS"}.get(sd, "BUSINESS")

    def _snapshot(self):
        with self.lock:
            act = {r: dict(v) for r, v in self.m.items() if time.time() - v["ts"] < 10}
        slc = {}
        for r, x in act.items():
            name = self._slice_of(x["sd"])
            slc[name] = {"cqi": x["cqi"], "dl": x["dl"], "f1ap": x["f1ap"],
                         "node": x["node"], "rnti": r}
        return slc

    def _state_reward(self, slc):
        sat, cqi = [], []
        for s in SLICES:
            d = slc.get(s, {"cqi": 1, "dl": 0})
            sat.append(min(d["dl"] / SLA_DL[s], 1.5))
            cqi.append(d["cqi"] / 15.0)
        state = np.array(sat + cqi, dtype=np.float32)
        sat_clip = np.clip(np.array(sat), 0, 1.0)
        reward = float(np.dot(W, sat_clip))
        if sat_clip[0] < 1.0:
            reward -= CRIT_PENALTY
        return state, reward, sat_clip

    def _mask(self, sat_clip):
        m = np.ones(N_ACT, dtype=bool)
        if sat_clip[0] < 1.0:
            for i, p in enumerate(PROFILES):
                if p[0] < CRIT_MIN_FLOOR:
                    m[i] = False
        if not m.any(): m[1] = True
        return m

    def _apply(self, action, slc):
        prof = PROFILES[action]
        decisions = {}
        for ratio, s in zip(prof, SLICES):
            if s not in slc: continue
            d = slc[s]
            try:
                self.e2sm_rc.control_slice_level_prb_quota(
                    d["node"], d["f1ap"], int(ratio), 100, dedicated_prb_ratio=100, ack_request=1)
            except Exception as e:
                print(f"  [E2] {s} f1ap={d['f1ap']} FAIL: {e}")
            decisions[str(d["rnti"])] = {
                "prb_min": int(ratio), "prb_max": 100,
                "slice_name": s, "f1ap_id": d["f1ap"],
                "alloc_req_bps": int(SLA_DL[s]),
            }
        try:
            with open(PRB_FILE, "w") as f:
                json.dump(decisions, f)
        except Exception as e:
            print(f"  [PRB-LOG] write failed: {e}")

    def _loop(self):
        mode = "TRAIN" if self.kbl.train_mode else "EVAL"
        print(f"[KBL-CTRL] {mode} | interval={self.interval}s | buffer={BUFFER_SIZE}")
        print(f"[KBL-CTRL] Planning horizon={HORIZON}, Kernel gamma={KERNEL_GAMMA}")
        
        while self.running:
            time.sleep(self.interval)
            slc = self._snapshot()
            if len(slc) < 1:
                print(f"{datetime.datetime.now():%H:%M:%S} (0 UEs)"); continue
            state, reward, sat = self._state_reward(slc)

            # Store transition and train
            if self.prev is not None and self.kbl.train_mode:
                o, a, lp, v, msk = self.prev
                # Store the transition (s, a, s', r)
                self.kbl.store_transition(o, a, state, reward)
                out = self.kbl.maybe_update(last_val=0.0, update_idx=self.update_idx)
                if out:
                    self.update_idx += 1
                    mr, pl, vl, mse = out
                    print(f"  [UPDATE {self.update_idx}] mean_r={mr:.3f} model_mse={mse:.4f}")

            # choose and apply the next action
            mask = self._mask(sat)
            action, logp, val = self.kbl.select(state, mask)
            self._apply(action, slc)
            self.prev = (state, action, logp, val, mask)

            t = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"{t} sat=[{sat[0]:.2f},{sat[1]:.2f},{sat[2]:.2f}] "
                  f"cqi=[{state[3]*15:.0f},{state[4]*15:.0f},{state[5]*15:.0f}] "
                  f"act={action}{PROFILES[action]} r={reward:.3f}")

    @xAppBase.start_function
    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()


# ROLLOUT is used for logging mean reward, not for KBL
ROLLOUT = 32

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="")
    p.add_argument("--http_server_port", type=int, default=8099)
    p.add_argument("--rmr_port", type=int, default=4569)
    p.add_argument("--interval", type=float, default=1.0, help="decision interval (s)")
    p.add_argument("--train", action="store_true", help="online training")
    p.add_argument("--eval", action="store_true", help="frozen greedy policy for comparison")
    p.add_argument("--ckpt", default=CKPT_DEFAULT)
    a = p.parse_args()
    train = not a.eval
    kbl = KBL(train=train, ckpt=a.ckpt)
    x = KBLXApp(a.config, a.http_server_port, a.rmr_port, a.interval, kbl)
    x.e2sm_rc.set_ran_func_id(3)
    for s in (signal.SIGQUIT, signal.SIGTERM, signal.SIGINT):
        signal.signal(s, x.signal_handler)
    x.start()
#!/usr/bin/env python3
"""
Virtual UE traffic generator for Scenario B
Runs forever inside network namespaces vue1/vue2/vue3
vue1 = CRITICAL, vue2 = PERFORMANCE, vue3 = BUSINESS
Requires traffic_server.py running on Tower-2
"""
import subprocess
import threading
import time

SERVER_IP = "10.45.0.1"

def run_in_netns(netns, script, args):
    cmd = ["sudo", "ip", "netns", "exec", netns,
           "python3", script] + args
    while True:
        try:
            subprocess.run(cmd)
        except Exception as e:
            print(f"[{netns}] Error: {e}, restarting in 3s...")
            time.sleep(3)

threads = [
    threading.Thread(target=run_in_netns, daemon=True,
        args=("vue1", "/home/ligm/critical_traffic.py",
              ["--server", SERVER_IP, "--duration", "999999"])),
    threading.Thread(target=run_in_netns, daemon=True,
        args=("vue2", "/home/ligm/performance_traffic.py",
              ["--server", SERVER_IP, "--duration", "999999"])),
    threading.Thread(target=run_in_netns, daemon=True,
        args=("vue3", "/home/ligm/performance_traffic.py",
              ["--server", SERVER_IP, "--duration", "999999"])),
]

print("[VIRTUAL TRAFFIC] Starting Scenario B virtual UE traffic")
print("[VIRTUAL TRAFFIC] vue1=CRITICAL vue2=PERFORMANCE vue3=BUSINESS")
for t in threads:
    t.start()

try:
    while True:
        time.sleep(60)
        print("[VIRTUAL TRAFFIC] Running...")
except KeyboardInterrupt:
    print("[VIRTUAL TRAFFIC] Stopped")

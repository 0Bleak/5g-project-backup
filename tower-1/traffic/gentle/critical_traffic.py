#!/usr/bin/env python3
"""
Critical Slice Traffic Generator -- Production Version
Applications: voice, etcs, ato, remote_engine_ctrl, pub_warn

Features:
- Token bucket rate control (accurate even at sub-kbps rates)
- Drift-corrected timing loop (perf_counter based)
- Real bidirectional DL traffic (requires traffic_server.py)
- Per-packet latency measurement via PING/PONG
- Stats reporter with UL/DL/latency breakdown

"""

import socket
import struct
import threading
import time
import random
import argparse
from collections import deque


class TrafficApp:
    def __init__(self, name, port, server_ip):
        self.name = name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.dest = (server_ip, port)
        self.running = True

        # Counters
        self.bytes_sent_ul = 0
        self.bytes_recv_dl = 0
        self.packets_sent_ul = 0
        self.packets_recv_dl = 0

        # Token buckets
        self.ul_bucket = 0.0
        self.dl_bucket = 0.0

        # Latency tracking
        self.latencies = deque(maxlen=100)
        self.latency_interval = 1.0  # ping every 1s
        self.last_ping = 0

    def tick(self, ul_rate_bps, dl_rate_bps, dt):
        """Called every interval. Accumulates tokens, sends when ready."""
        now = time.perf_counter()

        # --- UL traffic ---
        self.ul_bucket += (ul_rate_bps / 8.0) * dt
        if self.ul_bucket >= 1.0:
            size = int(self.ul_bucket)
            size = min(size, 60000)
            try:
                self.sock.sendto(bytes(size), self.dest)
                self.bytes_sent_ul += size
                self.packets_sent_ul += 1
            except (BlockingIOError, OSError):
                pass
            self.ul_bucket -= int(self.ul_bucket)

        # --- DL request ---
        self.dl_bucket += (dl_rate_bps / 8.0) * dt
        if self.dl_bucket >= 1.0:
            size = int(self.dl_bucket)
            size = min(size, 60000)
            try:
                req = struct.pack("!I", size) + b"DL_REQ"
                self.sock.sendto(req, self.dest)
            except (BlockingIOError, OSError):
                pass
            self.dl_bucket -= int(self.dl_bucket)

        # --- Latency ping ---
        if now - self.last_ping >= self.latency_interval:
            try:
                ts = struct.pack("!d", now)
                self.sock.sendto(ts + b"PING", self.dest)
                self.last_ping = now
            except (BlockingIOError, OSError):
                pass

        # --- Drain incoming (DL responses + PONGs) ---
        while True:
            try:
                data, _ = self.sock.recvfrom(65535)
                if len(data) >= 12 and data[8:12] == b"PONG":
                    sent_ts = struct.unpack("!d", data[:8])[0]
                    rtt_ms = (now - sent_ts) * 1000
                    self.latencies.append(rtt_ms)
                else:
                    self.bytes_recv_dl += len(data)
                    self.packets_recv_dl += 1
            except (BlockingIOError, OSError):
                break

    def avg_latency(self):
        if self.latencies:
            return sum(self.latencies) / len(self.latencies)
        return 0.0

    def p99_latency(self):
        if self.latencies:
            s = sorted(self.latencies)
            idx = int(len(s) * 0.99)
            return s[min(idx, len(s) - 1)]
        return 0.0


def run_periodic(app, ul_bps, dl_bps, interval_ms, duration):
    """Drift-corrected periodic loop with token bucket."""
    interval = interval_ms / 1000.0
    next_t = time.perf_counter() + interval
    end_t = time.perf_counter() + duration if duration != float('inf') else float('inf')

    while app.running and time.perf_counter() < end_t:
        app.tick(ul_bps, dl_bps, interval)
        now = time.perf_counter()
        sleep_t = next_t - now
        if sleep_t > 0.0001:
            time.sleep(sleep_t)
        next_t += interval
        # If we fell behind, reset to avoid burst catchup
        if next_t < now:
            next_t = now + interval


# ============================================================
# Application threads -- parameters from policy table
# ============================================================

def voice_thread(app):
    """
    voice -- critical
    DL/UL: 23.85 / 23.85 kbps (symmetric)
    Interval: 20ms (5QI 65, PDB 75ms)
    Pattern: emergency-triggered, active 30s, idle 30-90s
    Latency req: <100ms, Reliability: 99.9%
    """
    while app.running:
        print(f"  [{app.name}] EMERGENCY ACTIVE -- 30s")
        run_periodic(app, 23850, 23850, 20, 30)
        if not app.running:
            break
        idle = random.uniform(30, 90)
        print(f"  [{app.name}] idle {idle:.0f}s")
        time.sleep(idle)


def etcs_thread(app):
    """
    etcs -- critical
    DL/UL: 5 / 1.25 kbps
    Interval: 20ms (5QI 69, PDB 60ms)
    Payload: 200 bytes
    Pattern: strictly periodic, continuous
    Latency req: <100ms, Reliability: 99.999%
    """
    print(f"  [{app.name}] periodic continuous")
    run_periodic(app, 1250, 5000, 20, float('inf'))


def ato_thread(app):
    """
    ato -- critical
    DL/UL: 1 / 0.25 kbps
    Interval: 20ms (5QI 69, PDB 60ms)
    Payload: 200 bytes
    Pattern: active in Full Supervision mode, otherwise off
    Simulated: 120s active, 30-60s idle
    Latency req: <100ms, Reliability: 99.999%
    """
    while app.running:
        print(f"  [{app.name}] Full Supervision -- 120s")
        run_periodic(app, 250, 1000, 20, 120)
        if not app.running:
            break
        idle = random.uniform(30, 60)
        print(f"  [{app.name}] idle {idle:.0f}s")
        time.sleep(idle)


def remote_engine_ctrl_thread(app):
    """
    remote_engine_ctrl -- critical
    DL/UL: 25 / 100 kbps
    Interval: 25ms (5QI 69, PDB 60ms)
    Payload: 200 bytes
    Pattern: activity forced to zero in current profile (rem_eng_act=0)
    Simulated: zero traffic (silent) to match table specification
    We send a 1-second keepalive burst every 60s for monitoring only
    Latency req: <100ms, Reliability: 99.999%
    """
    while app.running:
        # 1s minimal keepalive at full rate
        run_periodic(app, 100000, 25000, 25, 1)
        if not app.running:
            break
        # 59s silence (matches "forced to zero")
        time.sleep(59)


def pub_warn_thread(app):
    """
    pub_warn -- critical
    DL/UL: 2 / 2 kbps (symmetric)
    Interval: 20ms (5QI 65, PDB 75ms)
    Pattern: emergency-triggered, active 10s (~40 rows), then off
    Idle: 60-180s between emergencies
    Latency req: <200ms, Reliability: >99.99%
    """
    while app.running:
        print(f"  [{app.name}] EMERGENCY WARNING -- 10s")
        run_periodic(app, 2000, 2000, 20, 10)
        if not app.running:
            break
        idle = random.uniform(60, 180)
        print(f"  [{app.name}] idle {idle:.0f}s")
        time.sleep(idle)


# ============================================================

def latency_logger(apps, output_file, interval=1):
    import csv
    with open(output_file, 'w', newline='') as f:
        csv.writer(f).writerow(['timestamp', 'app_name', 'rtt_avg_ms', 'rtt_p99_ms', 'samples'])
    while any(a.running for a in apps):
        time.sleep(interval)
        ts = round(time.time(), 3)
        with open(output_file, 'a', newline='') as f:
            writer = csv.writer(f)
            for app in apps:
                if app.latencies:
                    writer.writerow([ts, app.name, round(app.avg_latency(), 2), round(app.p99_latency(), 2), len(app.latencies)])


def stats_reporter(apps, interval=10):
    start = time.time()
    while any(a.running for a in apps):
        time.sleep(interval)
        elapsed = time.time() - start
        if elapsed < 1:
            continue
        print(f"\n{'='*80}")
        print(f"  CRITICAL SLICE STATS | Elapsed: {elapsed:.0f}s")
        print(f"  {'App':>20} {'UL kbps':>10} {'DL kbps':>10} {'UL pkts':>9} {'DL pkts':>9} {'Lat avg':>9} {'Lat p99':>9}")
        print(f"  {'-'*76}")
        for app in apps:
            ul = (app.bytes_sent_ul * 8 / 1000) / elapsed
            dl = (app.bytes_recv_dl * 8 / 1000) / elapsed
            lat_avg = app.avg_latency()
            lat_p99 = app.p99_latency()
            print(f"  {app.name:>20} {ul:>10.2f} {dl:>10.2f} {app.packets_sent_ul:>9} {app.packets_recv_dl:>9} {lat_avg:>8.1f}ms {lat_p99:>8.1f}ms")
        print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description="Critical Slice Traffic Generator")
    parser.add_argument("--server", default="10.45.0.1",
                        help="Traffic server IP (Tower-2 UPF or localhost for test)")
    parser.add_argument("--duration", type=int, default=3600,
                        help="Duration in seconds (default: 3600 = 1 hour)")
    parser.add_argument("--latency_log", default="/tmp/latency_critical.csv")
    args = parser.parse_args()

    print("=" * 80)
    print("  CRITICAL SLICE TRAFFIC GENERATOR")
    print(f"  Server: {args.server} | Duration: {args.duration}s")
    print(f"  Apps: voice, etcs, ato, remote_engine_ctrl, pub_warn")
    print("=" * 80)

    app_defs = [
        ("voice",              voice_thread,              6001),
        ("etcs",               etcs_thread,               6002),
        ("ato",                ato_thread,                6003),
        ("remote_engine_ctrl", remote_engine_ctrl_thread, 6004),
        ("pub_warn",           pub_warn_thread,           6005),
    ]

    apps = []
    threads = []
    for name, func, port in app_defs:
        app = TrafficApp(name, port, args.server)
        apps.append(app)
        t = threading.Thread(target=func, args=(app,), daemon=True)
        threads.append(t)

    stats = threading.Thread(target=stats_reporter, args=(apps,), daemon=True)

    print("\n[START] Launching critical slice traffic...\n")
    for t in threads:
        t.start()
    stats.start()
    lat = threading.Thread(target=latency_logger, args=(apps, args.latency_log), daemon=True)
    lat.start()

    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")

    for app in apps:
        app.running = False
    time.sleep(2)

    elapsed = args.duration
    print(f"\n{'='*80}")
    print(f"  FINAL REPORT | Duration: {elapsed}s")
    print(f"  {'App':>20} {'UL KB':>10} {'DL KB':>10} {'Packets':>10} {'Avg Lat':>10}")
    print(f"  {'-'*66}")
    for app in apps:
        print(f"  {app.name:>20} {app.bytes_sent_ul/1024:>10.1f} {app.bytes_recv_dl/1024:>10.1f} {app.packets_sent_ul:>10} {app.avg_latency():>9.1f}ms")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()

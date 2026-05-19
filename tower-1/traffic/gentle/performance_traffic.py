#!/usr/bin/env python3
"""
Performance Slice Traffic Generator -- Production Version
Applications: telemetry_nc, equip_ctl, asset_tel, pis, video_surv

Features:
- Token bucket rate control
- Drift-corrected timing loop
- Real bidirectional DL traffic (requires traffic_server.py)
- Per-packet latency measurement
- video_surv: correct DL reduction during emergency UL burst
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

        self.bytes_sent_ul = 0
        self.bytes_recv_dl = 0
        self.packets_sent_ul = 0
        self.packets_recv_dl = 0

        self.ul_bucket = 0.0
        self.dl_bucket = 0.0

        self.latencies = deque(maxlen=100)
        self.latency_interval = 1.0
        self.last_ping = 0

    def tick(self, ul_rate_bps, dl_rate_bps, dt):
        now = time.perf_counter()

        self.ul_bucket += (ul_rate_bps / 8.0) * dt
        if self.ul_bucket >= 1.0:
            size = min(int(self.ul_bucket), 60000)
            try:
                self.sock.sendto(bytes(size), self.dest)
                self.bytes_sent_ul += size
                self.packets_sent_ul += 1
            except (BlockingIOError, OSError):
                pass
            self.ul_bucket -= int(self.ul_bucket)

        self.dl_bucket += (dl_rate_bps / 8.0) * dt
        if self.dl_bucket >= 1.0:
            size = min(int(self.dl_bucket), 60000)
            try:
                req = struct.pack("!I", size) + b"DL_REQ"
                self.sock.sendto(req, self.dest)
            except (BlockingIOError, OSError):
                pass
            self.dl_bucket -= int(self.dl_bucket)

        if now - self.last_ping >= self.latency_interval:
            try:
                ts = struct.pack("!d", now)
                self.sock.sendto(ts + b"PING", self.dest)
                self.last_ping = now
            except (BlockingIOError, OSError):
                pass

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
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    def p99_latency(self):
        if self.latencies:
            s = sorted(self.latencies)
            return s[int(len(s) * 0.99)]
        return 0.0


def run_periodic(app, ul_bps, dl_bps, interval_ms, duration):
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
        if next_t < now:
            next_t = now + interval


# ============================================================
# Application threads
# ============================================================

def telemetry_nc_thread(app):
    """
    telemetry_nc -- performance
    DL/UL: 1 / 5 kbps
    Interval: 190ms (5QI 70, PDB 200ms)
    Pattern: periodic continuous
    Latency req: <100ms, Reliability: >99.9999%
    """
    print(f"  [{app.name}] periodic continuous")
    run_periodic(app, 5000, 1000, 190, float('inf'))


def equip_ctl_thread(app):
    """
    equip_ctl -- performance
    DL/UL: 1 / 1 kbps
    Interval: 20ms (5QI 69, PDB 60ms)
    Pattern: periodic continuous
    Latency req: <100ms, Reliability: >99.9999%
    """
    print(f"  [{app.name}] periodic continuous")
    run_periodic(app, 1000, 1000, 20, float('inf'))


def asset_tel_thread(app):
    """
    asset_tel -- performance
    DL/UL: 4 / 4 kbps
    Interval: 190ms (5QI 70, PDB 200ms)
    Payload: 100 bytes
    Pattern: periodic continuous
    Latency req: 50-100ms, Reliability: 99.999%
    """
    print(f"  [{app.name}] periodic continuous")
    run_periodic(app, 4000, 4000, 190, float('inf'))


def pis_thread(app):
    """
    pis (Passenger Information System) -- performance
    DL/UL: 5 / 5 kbps
    Interval: 280ms (5QI 9, PDB 300ms)
    Pattern: periodic continuous
    Latency/Reliability: NA (best effort within performance slice)
    """
    print(f"  [{app.name}] periodic continuous")
    run_periodic(app, 5000, 5000, 280, float('inf'))


def video_surv_thread(app):
    """
    video_surv -- performance
    Normal: DL 300 kbps / UL 3000 kbps
    Emergency burst: UL 9000 kbps, DL reduced to 10 kbps (light control only)
    Interval: 25ms (5QI 4, PDB 300ms)
    Pattern: 120s normal, 25s emergency UL burst
    Latency: 1-18s acceptable, 1-2.5% packet loss acceptable
    """
    while app.running:
        print(f"  [{app.name}] normal streaming -- 120s")
        run_periodic(app, 3000000, 300000, 25, 120)
        if not app.running:
            break
        print(f"  [{app.name}] EMERGENCY UL BURST -- 25s (DL light control)")
        run_periodic(app, 9000000, 10000, 25, 25)


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
        print(f"  PERFORMANCE SLICE STATS | Elapsed: {elapsed:.0f}s")
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
    parser = argparse.ArgumentParser(description="Performance Slice Traffic Generator")
    parser.add_argument("--server", default="10.45.0.1",
                        help="Traffic server IP")
    parser.add_argument("--duration", type=int, default=3600,
                        help="Duration in seconds (default: 3600)")
    parser.add_argument("--latency_log", default="/tmp/latency_performance.csv")
    args = parser.parse_args()

    print("=" * 80)
    print("  PERFORMANCE SLICE TRAFFIC GENERATOR")
    print(f"  Server: {args.server} | Duration: {args.duration}s")
    print(f"  Apps: telemetry_nc, equip_ctl, asset_tel, pis, video_surv")
    print("=" * 80)

    app_defs = [
        ("telemetry_nc", telemetry_nc_thread, 7001),
        ("equip_ctl",    equip_ctl_thread,    7002),
        ("asset_tel",    asset_tel_thread,     7003),
        ("pis",          pis_thread,           7004),
        ("video_surv",   video_surv_thread,    7005),
    ]

    apps = []
    threads = []
    for name, func, port in app_defs:
        app = TrafficApp(name, port, args.server)
        apps.append(app)
        t = threading.Thread(target=func, args=(app,), daemon=True)
        threads.append(t)

    stats = threading.Thread(target=stats_reporter, args=(apps,), daemon=True)

    print("\n[START] Launching performance slice traffic...\n")
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

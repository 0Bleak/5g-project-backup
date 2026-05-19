#!/usr/bin/env python3
"""
Virtual-only CQI Injector. Connects to ZMQ gNB (8003),
replaces CQI with SNCF traces, serves on port 8004.
"""
import argparse, json, os, glob, random, time, threading, csv
import websocket
from websocket_server import WebsocketServer

class SNCFTrace:
    def __init__(self, csv_path):
        self.cqi_values = []
        self.index = 0
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            last_ts = None
            for row in reader:
                ts = row.get('Timestamp', '')
                cqi = int(row.get('CQI_wb', 15))
                if last_ts is None or ts[:19] != last_ts[:19]:
                    self.cqi_values.append(cqi)
                    last_ts = ts
        if not self.cqi_values:
            self.cqi_values = [15]

    def next_cqi(self):
        val = self.cqi_values[self.index]
        self.index = (self.index + 1) % len(self.cqi_values)
        return val

class TraceManager:
    def __init__(self, dataset_dir):
        self.files = sorted(glob.glob(os.path.join(dataset_dir, "train*_*.csv")))
        if not self.files:
            raise FileNotFoundError(f"No CSV files in {dataset_dir}")
        print(f"[INJECTOR] Found {len(self.files)} SNCF trace files")
        random.shuffle(self.files)
        self.ue_traces = {}
        self.file_idx = 0

    def get_cqi(self, rnti):
        if rnti not in self.ue_traces:
            f = self.files[self.file_idx % len(self.files)]
            self.file_idx += 1
            print(f"[INJECTOR] RNTI {rnti} -> {os.path.basename(f)}")
            self.ue_traces[rnti] = SNCFTrace(f)
        return self.ue_traces[rnti].next_cqi()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zmq_url", default="127.0.0.1:8003")
    p.add_argument("--proxy_port", type=int, default=8004)
    p.add_argument("--dataset_dir", required=True)
    args = p.parse_args()

    trace_mgr = TraceManager(args.dataset_dir)
    server = WebsocketServer(host="0.0.0.0", port=args.proxy_port)

    def on_new_client(client, srv):
        print(f"[INJECTOR] Client connected: {client['address']}")

    def on_message_received(client, srv, message):
        try:
            d = json.loads(message)
            if d.get("cmd") == "metrics_subscribe":
                srv.send_message(client, json.dumps({"cmd": "metrics_subscribe"}))
        except:
            pass

    server.set_fn_new_client(on_new_client)
    server.set_fn_message_received(on_message_received)
    threading.Thread(target=server.run_forever, daemon=True).start()
    print(f"[INJECTOR] Virtual CQI server on port {args.proxy_port}")

    def upstream_loop():
        while True:
            try:
                ws = websocket.create_connection(f"ws://{args.zmq_url}", timeout=5)
                ws.send(json.dumps({"cmd": "metrics_subscribe"}))
                print(f"[INJECTOR] Connected to ZMQ DU at {args.zmq_url}")
                while True:
                    msg = ws.recv()
                    try:
                        data = json.loads(msg)
                        if "cells" in data:
                            for cell in data["cells"]:
                                for ue in cell.get("ue_list", []):
                                    rnti = ue.get("rnti", 0)
                                    if rnti:
                                        ue["cqi"] = trace_mgr.get_cqi(rnti)
                        server.send_message_to_all(json.dumps(data))
                    except:
                        pass
            except Exception as e:
                print(f"[INJECTOR] Upstream error: {e}, reconnecting...")
                time.sleep(2)

    upstream_loop()

if __name__ == "__main__":
    main()

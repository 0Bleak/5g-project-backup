#!/usr/bin/env python3
"""
Hybrid CQI Injector - merges RF DU (8001) and ZMQ gNB (8003) streams.
Physical UEs: passed through unmodified from port 8001.
Virtual UEs: CQI replaced with SNCF traces, RNTI remapped to 0xF001+ range.
Serves merged stream on port 8002.
"""
import argparse, json, os, glob, random, time, threading, csv, copy
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
            print(f"[INJECTOR] Virtual RNTI {rnti} -> {os.path.basename(f)}")
            self.ue_traces[rnti] = SNCFTrace(f)
        return self.ue_traces[rnti].next_cqi()

# Virtual RNTI remapping: ZMQ RNTIs -> 0xF001, 0xF002, 0xF003
virtual_rnti_map = {}
virtual_rnti_counter = 0xF001

def remap_virtual_rnti(original_rnti):
    global virtual_rnti_counter
    if original_rnti not in virtual_rnti_map:
        virtual_rnti_map[original_rnti] = virtual_rnti_counter
        print(f"[INJECTOR] Remap virtual RNTI {original_rnti} -> {virtual_rnti_counter}")
        virtual_rnti_counter += 1
    return virtual_rnti_map[original_rnti]

# Slice assignment for virtual UEs by connection order
# ue1.conf=IMSI006=CRITICAL(SD:3), ue2.conf=IMSI007=PERFORMANCE(SD:1), ue3.conf=IMSI008=BUSINESS(SD:2)
virtual_slice_order = ["CRITICAL", "PERFORMANCE", "BUSINESS"]
virtual_rnti_to_slice = {}
virtual_rnti_order = []

def get_virtual_slice(remapped_rnti):
    if remapped_rnti not in virtual_rnti_to_slice:
        idx = len(virtual_rnti_order)
        if idx < len(virtual_slice_order):
            virtual_rnti_to_slice[remapped_rnti] = virtual_slice_order[idx]
        else:
            virtual_rnti_to_slice[remapped_rnti] = "BUSINESS"
        virtual_rnti_order.append(remapped_rnti)
    return virtual_rnti_to_slice[remapped_rnti]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rf_url", default="127.0.0.1:8001")
    p.add_argument("--zmq_url", default="127.0.0.1:8003")
    p.add_argument("--proxy_port", type=int, default=8002)
    p.add_argument("--dataset_dir", required=True)
    args = p.parse_args()

    trace_mgr = TraceManager(args.dataset_dir)
    latest_rf_data = {"msg": None, "lock": threading.Lock()}
    latest_zmq_data = {"msg": None, "lock": threading.Lock()}

    # Downstream server on port 8002
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
    print(f"[INJECTOR] Downstream server on port {args.proxy_port}")

    # RF DU upstream (port 8001) - pass through unmodified
    def rf_loop():
        while True:
            try:
                ws = websocket.create_connection(f"ws://{args.rf_url}", timeout=5)
                ws.send(json.dumps({"cmd": "metrics_subscribe"}))
                print(f"[INJECTOR] Connected to RF DU at {args.rf_url}")
                while True:
                    msg = ws.recv()
                    try:
                        data = json.loads(msg)
                        if "cells" in data:
                            with latest_rf_data["lock"]:
                                latest_rf_data["msg"] = data
                    except:
                        pass
            except Exception as e:
                print(f"[INJECTOR] RF upstream error: {e}, reconnecting...")
                time.sleep(2)

    # ZMQ gNB upstream (port 8003) - inject CQI, remap RNTIs
    def zmq_loop():
        while True:
            try:
                ws = websocket.create_connection(f"ws://{args.zmq_url}", timeout=5)
                ws.send(json.dumps({"cmd": "metrics_subscribe"}))
                print(f"[INJECTOR] Connected to ZMQ gNB at {args.zmq_url}")
                while True:
                    msg = ws.recv()
                    try:
                        data = json.loads(msg)
                        if "cells" in data:
                            for cell in data["cells"]:
                                for ue in cell.get("ue_list", []):
                                    orig_rnti = ue.get("rnti", 0)
                                    if orig_rnti:
                                        remapped = remap_virtual_rnti(orig_rnti)
                                        ue["rnti"] = remapped
                                        ue["cqi"] = trace_mgr.get_cqi(remapped)
                            with latest_zmq_data["lock"]:
                                latest_zmq_data["msg"] = data
                    except:
                        pass
            except Exception as e:
                print(f"[INJECTOR] ZMQ upstream error: {e}, reconnecting...")
                time.sleep(2)

    # Merge and broadcast at 1Hz
    def merge_loop():
        while True:
            time.sleep(1)
            merged_ues = []
            with latest_rf_data["lock"]:
                rf = latest_rf_data["msg"]
                if rf and "cells" in rf:
                    for cell in rf["cells"]:
                        merged_ues.extend(cell.get("ue_list", []))
            with latest_zmq_data["lock"]:
                zmq = latest_zmq_data["msg"]
                if zmq and "cells" in zmq:
                    for cell in zmq["cells"]:
                        merged_ues.extend(cell.get("ue_list", []))
            if merged_ues:
                merged_msg = {"cells": [{"ue_list": merged_ues}]}
                server.send_message_to_all(json.dumps(merged_msg))

    threading.Thread(target=rf_loop, daemon=True).start()
    threading.Thread(target=zmq_loop, daemon=True).start()
    threading.Thread(target=merge_loop, daemon=True).start()

    print("[INJECTOR] Merging RF (8001) + ZMQ (8003) -> port 8002")
    print("[INJECTOR] Physical UEs: passthrough | Virtual UEs: SNCF CQI + RNTI remap")

    try:
        while True:
            time.sleep(60)
            with latest_rf_data["lock"]:
                rf_count = sum(len(c.get("ue_list",[])) for c in latest_rf_data["msg"].get("cells",[])) if latest_rf_data["msg"] else 0
            with latest_zmq_data["lock"]:
                zmq_count = sum(len(c.get("ue_list",[])) for c in latest_zmq_data["msg"].get("cells",[])) if latest_zmq_data["msg"] else 0
            print(f"[INJECTOR] Status: {rf_count} physical + {zmq_count} virtual UEs")
    except KeyboardInterrupt:
        print("[INJECTOR] Stopped")

if __name__ == "__main__":
    main()

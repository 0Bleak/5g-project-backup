#!/usr/bin/env python3
import json, time, csv, os, threading
import websocket

CSV_FILE = "/tmp/ue_metrics_log.csv"
PRB_FILE = "/tmp/prb_decisions.json"
prb_decisions = {}

def load_prb():
    global prb_decisions
    while True:
        try:
            if os.path.exists(PRB_FILE):
                with open(PRB_FILE) as f:
                    prb_decisions = json.load(f)
        except: pass
        time.sleep(2)

with open(CSV_FILE, "w", newline="") as f:
    csv.writer(f).writerow([
        "timestamp","rnti","cqi","ri","dl_mcs","ul_mcs",
        "dl_brate_bps","ul_brate_bps","pusch_snr_db",
        "pusch_rsrp_db","phr","dl_nof_ok","dl_nof_nok",
        "prb_min","prb_max","slice_name","f1ap_id"])

def on_open(ws):
    ws.send(json.dumps({"cmd":"metrics_subscribe"}))
    print("[LOG v2] Subscribed")

def on_message(ws, message):
    try:
        data = json.loads(message)
        if "cells" not in data: return
        ts = time.time()
        for cell in data["cells"]:
            for ue in cell.get("ue_list",[]):
                rnti = ue.get("rnti",0)
                cqi = ue.get("cqi",0)
                if not cqi: continue
                p = prb_decisions.get(str(rnti),{})
                row = [round(ts,3), rnti, cqi, ue.get("ri",1),
                       ue.get("dl_mcs",0), ue.get("ul_mcs",0),
                       ue.get("dl_brate",0), ue.get("ul_brate",0),
                       round(ue.get("pusch_snr_db",0),1),
                       round(ue.get("pusch_rsrp_db",0),1),
                       ue.get("phr",0),
                       ue.get("dl_nof_ok",0), ue.get("dl_nof_nok",0),
                       p.get("prb_min",""), p.get("prb_max",""),
                       p.get("slice_name",""), p.get("f1ap_id","")]
                with open(CSV_FILE,"a",newline="") as f:
                    csv.writer(f).writerow(row)
    except: pass

threading.Thread(target=load_prb, daemon=True).start()
ws = websocket.WebSocketApp("ws://10.0.2.1:8001", on_open=on_open, on_message=on_message)
while ws.run_forever(): time.sleep(1)

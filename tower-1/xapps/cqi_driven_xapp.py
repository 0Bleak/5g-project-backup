#!/usr/bin/env python3
import argparse, signal, json, threading, time, math, datetime
from lib.xAppBase import xAppBase

TOTAL_PRBS = 52
N_RE_PRIME = 156
PRB_BPS_FACTOR = N_RE_PRIME * 1000
CQI_EFFICIENCY = {1:0.1523,2:0.2344,3:0.3770,4:0.6016,5:0.8770,
                  6:1.1758,7:1.4766,8:1.9141,9:2.4063,10:2.7305,
                  11:3.3223,12:3.9023,13:4.5234,14:5.1152,15:5.5547}

SLICE_PROFILES = {
    "critical":    {"sd":3,"min_prb_floor":0,"max_prb_ceiling":80,"priority":1,
                    "label":"CRITICAL","required_dl_bps":50_000},
    "performance": {"sd":1,"min_prb_floor":0,"max_prb_ceiling":50,"priority":2,
                    "label":"PERFORMANCE","required_dl_bps":300_000},
    "business":    {"sd":2,"min_prb_floor":0,"max_prb_ceiling":30,"priority":3,
                    "label":"BUSINESS","required_dl_bps":0}
}

def get_slice_profile(f1ap_id, ue_f1ap_to_slice):
    sd = ue_f1ap_to_slice.get(f1ap_id)
    for name, prof in SLICE_PROFILES.items():
        if prof["sd"] == sd:
            return name, prof
    return "unknown", {"min_prb_floor":10,"max_prb_ceiling":50,
                       "priority":99,"label":"UNKNOWN","required_dl_bps":0}

class CqiDrivenXapp(xAppBase):
    def __init__(self, config, http_server_port, rmr_port, ws_url, e2_node_id):
        super().__init__(config, http_server_port, rmr_port)
        self.ws_url = ws_url
        self.e2_node_id = e2_node_id
        self.ue_metrics = {}
        self.lock = threading.Lock()
        self.control_interval = 5
        self._start_ws_listener()

    def _start_ws_listener(self):
        import websocket
        def on_open(ws):
            ws.send(json.dumps({"cmd": "metrics_subscribe"}))
            print("[WS] Subscribed")
        def on_message(ws, message):
            try:
                data = json.loads(message)
                if "cells" in data:
                    for cell in data["cells"]:
                        for ue in cell.get("ue_list", []):
                            rnti = ue.get("rnti")
                            cqi = ue.get("cqi")
                            if cqi is not None:
                                with self.lock:
                                    self.ue_metrics[rnti] = {
                                        "cqi": cqi,
                                        "pusch_snr": ue.get("pusch_snr_db",0),
                                        "rsrp": ue.get("pusch_rsrp_db",0),
                                        "dl_mcs": ue.get("dl_mcs",0),
                                        "ul_mcs": ue.get("ul_mcs",0),
                                        "dl_brate": ue.get("dl_brate",0),
                                        "ul_brate": ue.get("ul_brate",0),
                                        "ri": ue.get("ri",1),
                                        "phr": ue.get("phr",0),
                                        "timestamp": time.time()
                                    }
            except: pass
        def on_error(ws, error): pass
        def ws_thread():
            ws = websocket.WebSocketApp("ws://"+self.ws_url,
                                        on_open=on_open, on_message=on_message,
                                        on_error=on_error)
            while ws.run_forever(): time.sleep(1)
        threading.Thread(target=ws_thread, daemon=True).start()

    def _required_prb_pct(self, required_bps, cqi):
        if required_bps <= 0: return 0
        eff = CQI_EFFICIENCY.get(cqi, 1.0)
        prb_bps = eff * PRB_BPS_FACTOR
        needed_prbs = math.ceil(required_bps / prb_bps)
        needed_prbs = min(needed_prbs, TOTAL_PRBS)
        return math.ceil(needed_prbs / TOTAL_PRBS * 100)

    def compute_sla_allocation(self, ue_data, ue_f1ap_to_slice):
        if not ue_data: return {}
        min_req = {}
        for f1ap, metrics in ue_data.items():
            _, prof = get_slice_profile(f1ap, ue_f1ap_to_slice)
            req_pct = self._required_prb_pct(prof["required_dl_bps"], metrics["cqi"])
            min_req[f1ap] = min(req_pct, prof["max_prb_ceiling"])
        total_req = sum(min_req.values())
        if total_req > 100:
            scale = 100 / total_req
            for f1ap in min_req:
                min_req[f1ap] = max(0, math.floor(min_req[f1ap] * scale))
        leftover = max(0, 100 - sum(min_req.values()))
        cqi_sum = sum(ue_data[f]["cqi"] for f in ue_data if ue_data[f]["cqi"]>0)
        bonuses = {}
        if cqi_sum > 0 and leftover > 0:
            for f1ap, metrics in ue_data.items():
                _, prof = get_slice_profile(f1ap, ue_f1ap_to_slice)
                share = metrics["cqi"] / cqi_sum
                bonus = int(leftover * share)
                space = prof["max_prb_ceiling"] - min_req[f1ap]
                bonuses[f1ap] = max(0, min(bonus, space))
        else:
            bonuses = {f:0 for f in ue_data}
        result = {}
        for f1ap in ue_data:
            _, prof = get_slice_profile(f1ap, ue_f1ap_to_slice)
            final_min = min_req.get(f1ap, prof["min_prb_floor"])
            final_max = final_min + bonuses.get(f1ap,0)
            final_min = max(0, min(final_min, 100))
            final_max = max(final_min, min(final_max, 100))
            result[f1ap] = {"min_prb":final_min, "max_prb":final_max,
                            "slice_name":prof["label"], "cqi":ue_data[f1ap]["cqi"]}
        return result

    def _control_loop(self, ue_f1ap_ids, ue_f1ap_to_slice):
        rnti_to_f1ap = {}
        print("[CTRL] Dynamic SLA control")
        print("[CTRL] ID mapping:", ue_f1ap_to_slice)
        while self.running:
            time.sleep(self.control_interval)
            with self.lock:
                active = {k:v for k,v in self.ue_metrics.items()
                          if time.time()-v["timestamp"]<10}
            if len(active) < len(ue_f1ap_ids):
                print(f"[CTRL] Waiting for {len(ue_f1ap_ids)} UEs, got {len(active)}")
                continue
            sorted_rntis = sorted(active.keys())
            for i, rnti in enumerate(sorted_rntis):
                if i < len(ue_f1ap_ids):
                    rnti_to_f1ap[rnti] = ue_f1ap_ids[i]
            ue_data = {}
            for rnti, f1ap_id in rnti_to_f1ap.items():
                if rnti in active:
                    ue_data[f1ap_id] = active[rnti]
            allocs = self.compute_sla_allocation(ue_data, ue_f1ap_to_slice)
            prb_out = {}
            for rnti, f1ap_id in rnti_to_f1ap.items():
                if f1ap_id in allocs:
                    alloc = allocs[f1ap_id]
                    prb_out[str(rnti)] = {"prb_min":alloc["min_prb"],
                                          "prb_max":alloc["max_prb"],
                                          "slice_name":alloc["slice_name"],
                                          "f1ap_id":f1ap_id}
            try:
                with open("/tmp/prb_decisions.json","w") as f:
                    json.dump(prb_out, f)
            except: pass
            t = datetime.datetime.now().strftime("%H:%M:%S")
            t = datetime.datetime.now().strftime("%H:%M:%S")
            print("\n" + t + " [CTRL] === SLA PRB Allocation ===")
            for fid in sorted(allocs.keys()):
                a = allocs[fid]
                rl = [r for r,f in rnti_to_f1ap.items() if f==fid]
                rv = rl[0] if rl else "?"
                dv = ue_data.get(fid,{}).get("dl_brate",0) / 1e6
                print("  [%11s] F1AP=%s RNTI=%s CQI=%2d DL=%.2fMbps -> PRB %d-%d%%" % (a["slice_name"], fid, rv, a["cqi"], dv, a["min_prb"], a["max_prb"]))
            for fid, alloc in allocs.items():
                try:
                    self.e2sm_rc.control_slice_level_prb_quota(
                        self.e2_node_id, fid, alloc["min_prb"], alloc["max_prb"],
                        dedicated_prb_ratio=100, ack_request=1)
                except Exception as e:
                    print(f"  -> FAILED F1AP={fid}: {e}")

    @xAppBase.start_function
    def start(self, ue_f1ap_ids, ue_f1ap_to_slice):
        threading.Thread(target=self._control_loop,
                         args=(ue_f1ap_ids, ue_f1ap_to_slice), daemon=True).start()

if __name__=="__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=str, default="")
    p.add_argument("--http_server_port", type=int, default=8094)
    p.add_argument("--rmr_port", type=int, default=4564)
    p.add_argument("--e2_node_id", default="gnbd_001_001_00019b_0")
    p.add_argument("--ws_url", default="10.0.2.1:8001")
    p.add_argument("--ue_ids", type=str, default="0,1,2")
    p.add_argument("--ue_slices", type=str, default="3,1,2")
    args = p.parse_args()
    ids = [int(x) for x in args.ue_ids.split(",")]
    sds = [int(x) for x in args.ue_slices.split(",")]
    xapp = CqiDrivenXapp("", args.http_server_port, args.rmr_port,
                          args.ws_url, args.e2_node_id)
    xapp.e2sm_rc.set_ran_func_id(3)
    signal.signal(signal.SIGQUIT, xapp.signal_handler)
    signal.signal(signal.SIGTERM, xapp.signal_handler)
    signal.signal(signal.SIGINT, xapp.signal_handler)
    xapp.start(ids, dict(zip(ids, sds)))

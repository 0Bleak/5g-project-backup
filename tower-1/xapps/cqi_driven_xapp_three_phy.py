#!/usr/bin/env python3
"""
cqi_driven_xapp_three_phy.py
Scenario A — 3 physical UEs only (RF DU, RIC 1)
Slice mapping: F1AP-ID 0=CRITICAL(sd:3), 1=PERFORMANCE(sd:1), 2=BUSINESS(sd:2)
"""
import argparse, signal, json, threading, time, math, datetime
from lib.xAppBase import xAppBase

TOTAL_PRBS    = 25
N_RE_PRIME    = 156
PRB_BPS_FACTOR = N_RE_PRIME * 1000

CQI_EFFICIENCY = {
    1:0.1523, 2:0.2344, 3:0.3770, 4:0.6016, 5:0.8770,
    6:1.1758, 7:1.4766, 8:1.9141, 9:2.4063, 10:2.7305,
    11:3.3223,12:3.9023,13:4.5234,14:5.1152,15:5.5547
}

# Hardcoded for scenario A — 3 physical UEs on RF DU
UE_F1AP_IDS     = [0, 1, 2]
UE_F1AP_TO_SLICE = {0: 3, 1: 1, 2: 2}   # sd: 3=CRITICAL, 1=PERFORMANCE, 2=BUSINESS
E2_NODE_ID      = "gnbd_001_001_00019b_0"
WS_URL          = "10.0.2.1:8001"

SLICE_PROFILES = {
    "critical":    {"sd":3, "min_prb_floor":0, "max_prb_ceiling":80,  "priority":1,
                    "label":"CRITICAL",    "required_dl_bps":50_000},
    "performance": {"sd":1, "min_prb_floor":0, "max_prb_ceiling":50,  "priority":2,
                    "label":"PERFORMANCE", "required_dl_bps":300_000},
    "business":    {"sd":2, "min_prb_floor":0, "max_prb_ceiling":30,  "priority":3,
                    "label":"BUSINESS",    "required_dl_bps":0},
}

def get_slice_profile(f1ap_id):
    sd = UE_F1AP_TO_SLICE.get(f1ap_id)
    for name, prof in SLICE_PROFILES.items():
        if prof["sd"] == sd:
            return name, prof
    return "unknown", {"min_prb_floor":10,"max_prb_ceiling":50,
                       "priority":99,"label":"UNKNOWN","required_dl_bps":0}

class CqiDrivenXappThreePhy(xAppBase):
    def __init__(self, config, http_server_port, rmr_port):
        super().__init__(config, http_server_port, rmr_port)
        self.ue_metrics  = {}
        self.lock        = threading.Lock()
        self.control_interval = 5
        self._start_ws_listener()

    def _start_ws_listener(self):
        import websocket
        def on_open(ws):
            ws.send(json.dumps({"cmd": "metrics_subscribe"}))
            print(f"[WS] Subscribed to {WS_URL}")
        def on_message(ws, message):
            try:
                data = json.loads(message)
                if "cells" not in data:
                    return
                for cell in data["cells"]:
                    for ue in cell.get("ue_list", []):
                        rnti = ue.get("rnti")
                        cqi  = ue.get("cqi")
                        if cqi is not None:
                            with self.lock:
                                self.ue_metrics[rnti] = {
                                    "cqi":          cqi,
                                    "pusch_snr":    ue.get("pusch_snr_db", 0),
                                    "rsrp":         ue.get("pusch_rsrp_db", 0),
                                    "dl_mcs":       ue.get("dl_mcs", 0),
                                    "ul_mcs":       ue.get("ul_mcs", 0),
                                    "dl_brate":     ue.get("dl_brate", 0),
                                    "ul_brate":     ue.get("ul_brate", 0),
                                    "dl_latency":   ue.get("dl_latency", 0),
                                    "ul_latency":   ue.get("ul_latency", 0),
                                    "ri":           ue.get("ri", 1),
                                    "phr":          ue.get("phr", 0),
                                    "timestamp":    time.time(),
                                }
            except:
                pass
        def on_error(ws, error):
            print(f"[WS] Error: {error}")
        def ws_thread():
            ws = websocket.WebSocketApp(
                "ws://" + WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error)
            while ws.run_forever():
                time.sleep(1)
        threading.Thread(target=ws_thread, daemon=True).start()

    def _required_prb_pct(self, required_bps, cqi):
        if required_bps <= 0:
            return 0
        eff        = CQI_EFFICIENCY.get(cqi, 1.0)
        prb_bps    = eff * PRB_BPS_FACTOR
        needed_prb = math.ceil(required_bps / prb_bps)
        needed_prb = min(needed_prb, TOTAL_PRBS)
        return math.ceil(needed_prb / TOTAL_PRBS * 100)

    def compute_sla_allocation(self, ue_data):
        if not ue_data:
            return {}
        # Step 1: compute minimum PRB % per UE based on CQI + SLA requirement
        min_req = {}
        for f1ap, metrics in ue_data.items():
            _, prof   = get_slice_profile(f1ap)
            req_pct   = self._required_prb_pct(prof["required_dl_bps"], metrics["cqi"])
            min_req[f1ap] = min(req_pct, prof["max_prb_ceiling"])
        # Step 2: scale down if total exceeds 100%
        total_req = sum(min_req.values())
        if total_req > 100:
            scale = 100 / total_req
            for f1ap in min_req:
                min_req[f1ap] = max(0, math.floor(min_req[f1ap] * scale))
        # Step 3: distribute leftover PRBs proportional to CQI
        leftover = max(0, 100 - sum(min_req.values()))
        cqi_sum  = sum(ue_data[f]["cqi"] for f in ue_data if ue_data[f]["cqi"] > 0)
        bonuses  = {}
        if cqi_sum > 0 and leftover > 0:
            for f1ap, metrics in ue_data.items():
                _, prof  = get_slice_profile(f1ap)
                share    = metrics["cqi"] / cqi_sum
                bonus    = int(leftover * share)
                space    = prof["max_prb_ceiling"] - min_req[f1ap]
                bonuses[f1ap] = max(0, min(bonus, space))
        else:
            bonuses = {f: 0 for f in ue_data}
        # Step 4: build final allocation
        result = {}
        for f1ap in ue_data:
            _, prof    = get_slice_profile(f1ap)
            final_min  = min_req.get(f1ap, prof["min_prb_floor"])
            final_max  = final_min + bonuses.get(f1ap, 0)
            final_min  = max(0, min(final_min, 100))
            final_max  = max(final_min, min(final_max, 100))
            result[f1ap] = {
                "min_prb":    final_min,
                "max_prb":    final_max,
                "slice_name": prof["label"],
                "cqi":        ue_data[f1ap]["cqi"],
            }
        return result

    def _control_loop(self):
        rnti_to_f1ap = {}
        print("[CTRL] Scenario A — 3 physical UEs")
        print(f"[CTRL] F1AP->slice mapping: {UE_F1AP_TO_SLICE}")
        print(f"[CTRL] E2 node: {E2_NODE_ID}")
        print(f"[CTRL] Control interval: {self.control_interval}s")

        while self.running:
            time.sleep(self.control_interval)
            with self.lock:
                active = {k: v for k, v in self.ue_metrics.items()
                          if time.time() - v["timestamp"] < 10}

            if len(active) < len(UE_F1AP_IDS):
                print(f"[CTRL] Waiting for {len(UE_F1AP_IDS)} UEs — "
                      f"currently {len(active)} active")
                continue

            # Map RNTIs to F1AP-IDs by sorted order (connection order = registration order)
            for i, rnti in enumerate(sorted(active.keys())):
                if i < len(UE_F1AP_IDS):
                    rnti_to_f1ap[rnti] = UE_F1AP_IDS[i]

            ue_data = {}
            for rnti, f1ap_id in rnti_to_f1ap.items():
                if rnti in active:
                    ue_data[f1ap_id] = active[rnti]

            allocs = self.compute_sla_allocation(ue_data)

            # Write PRB decisions for logger
            prb_out = {}
            for rnti, f1ap_id in rnti_to_f1ap.items():
                if f1ap_id in allocs:
                    alloc = allocs[f1ap_id]
                    prb_out[str(rnti)] = {
                        "prb_min":    alloc["min_prb"],
                        "prb_max":    alloc["max_prb"],
                        "slice_name": alloc["slice_name"],
                        "f1ap_id":    f1ap_id,
                    }
            try:
                with open("/tmp/prb_decisions.json", "w") as f:
                    json.dump(prb_out, f)
            except:
                pass

            # Print allocation table
            t = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"\n{t} [CTRL] === Scenario A — SLA PRB Allocation ===")
            print(f"  {'Slice':>11}  F1AP  RNTI    CQI  "
                  f"DL_lat_us  UL_lat_us  DL_Mbps  PRB_min  PRB_max")
            print(f"  {'-'*75}")
            for fid in sorted(allocs.keys()):
                a    = allocs[fid]
                rl   = [r for r, f in rnti_to_f1ap.items() if f == fid]
                rnti = rl[0] if rl else "?"
                m    = ue_data.get(fid, {})
                dl   = m.get("dl_brate", 0) / 1e6
                dl_l = m.get("dl_latency", 0)
                ul_l = m.get("ul_latency", 0)
                print(f"  {a['slice_name']:>11}     {fid}  "
                      f"{rnti:<6}  {a['cqi']:>3}  "
                      f"{dl_l:>9}  {ul_l:>9}  "
                      f"{dl:>7.2f}  {a['min_prb']:>7}  {a['max_prb']:>7}")

            # Send E2SM-RC control per UE
            for fid, alloc in allocs.items():
                try:
                    self.e2sm_rc.control_slice_level_prb_quota(
                        E2_NODE_ID, fid,
                        alloc["min_prb"], alloc["max_prb"],
                        dedicated_prb_ratio=100, ack_request=1)
                except Exception as e:
                    print(f"  [E2] FAILED F1AP={fid}: {e}")

    @xAppBase.start_function
    def start(self):
        threading.Thread(
            target=self._control_loop, daemon=True).start()


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Scenario A xApp — 3 physical UEs, RF DU, RIC 1")
    p.add_argument("--config",           type=str, default="")
    p.add_argument("--http_server_port", type=int, default=8094)
    p.add_argument("--rmr_port",         type=int, default=4564)
    args = p.parse_args()

    xapp = CqiDrivenXappThreePhy(
        args.config, args.http_server_port, args.rmr_port)
    xapp.e2sm_rc.set_ran_func_id(3)

    signal.signal(signal.SIGQUIT, xapp.signal_handler)
    signal.signal(signal.SIGTERM, xapp.signal_handler)
    signal.signal(signal.SIGINT,  xapp.signal_handler)

    xapp.start()

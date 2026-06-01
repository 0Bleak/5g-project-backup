#!/usr/bin/env python3
"""
cqi_driven_xapp_six_ue.py
Scenario B — 3 physical UEs (RF DU) + 3 virtual UEs (ZMQ DU)
Single RIC managing both DUs simultaneously
Physical DU E2 node: gnbd_001_001_00000213_0
Virtual DU E2 node:  gnbd_001_001_00000213_1
"""
import argparse, signal, json, threading, time, math, datetime
from lib.xAppBase import xAppBase

TOTAL_PRBS_RF  = 52
TOTAL_PRBS_ZMQ = 52
N_RE_PRIME     = 156
PRB_BPS_FACTOR = N_RE_PRIME * 1000

CQI_EFFICIENCY = {
    1:0.1523, 2:0.2344, 3:0.3770, 4:0.6016, 5:0.8770,
    6:1.1758, 7:1.4766, 8:1.9141, 9:2.4063, 10:2.7305,
    11:3.3223,12:3.9023,13:4.5234,14:5.1152,15:5.5547
}

E2_NODE_RF  = "gnbd_001_001_00000213_0"
E2_NODE_ZMQ = "gnbd_001_001_00000213_1"
WS_RF       = "10.0.2.1:8001"
WS_ZMQ      = "10.0.2.1:8002"

SLICE_PROFILES = {
    3: {"label":"CRITICAL",    "max_prb_ceiling":80,  "priority":1, "required_dl_bps":50_000},
    1: {"label":"PERFORMANCE", "max_prb_ceiling":50,  "priority":2, "required_dl_bps":300_000},
    2: {"label":"BUSINESS",    "max_prb_ceiling":30,  "priority":3, "required_dl_bps":0},
}

PHY_F1AP_TO_SLICE = {0: 3, 1: 1, 2: 2}
VIRT_SLICE_ORDER  = [3, 1, 2]

class CqiDrivenXappSixUE(xAppBase):
    def __init__(self, config, http_server_port, rmr_port):
        super().__init__(config, http_server_port, rmr_port)
        self.ue_metrics  = {}
        self.lock        = threading.Lock()
        self.control_interval = 5
        self._start_ws_listener(WS_RF,  "RF")
        self._start_ws_listener(WS_ZMQ, "ZMQ")

    def _start_ws_listener(self, url, label):
        import websocket
        def on_open(ws):
            ws.send(json.dumps({"cmd": "metrics_subscribe"}))
            print(f"[WS] Subscribed to {label} at {url}")
        def on_message(ws, message):
            try:
                data = json.loads(message)
                if "cells" not in data:
                    return
                for cell in data["cells"]:
                    for ue in cell.get("ue_list", []):
                        rnti = ue.get("rnti")
                        cqi  = ue.get("cqi")
                        if cqi:
                            with self.lock:
                                self.ue_metrics[rnti] = {
                                    "cqi":        cqi,
                                    "dl_brate":   ue.get("dl_brate", 0),
                                    "ul_brate":   ue.get("ul_brate", 0),
                                    "dl_latency": ue.get("dl_latency", 0),
                                    "ul_latency": ue.get("ul_latency", 0),
                                    "dl_mcs":     ue.get("dl_mcs", 0),
                                    "ul_mcs":     ue.get("ul_mcs", 0),
                                    "pusch_snr":  ue.get("pusch_snr_db", 0),
                                    "phr":        ue.get("phr", 0),
                                    "timestamp":  time.time(),
                                    "source":     label,
                                }
            except:
                pass
        def ws_thread():
            ws = websocket.WebSocketApp("ws://"+url,
                on_open=on_open, on_message=on_message)
            while ws.run_forever():
                time.sleep(1)
        threading.Thread(target=ws_thread, daemon=True).start()

    def _required_prb_pct(self, required_bps, cqi):
        if required_bps <= 0:
            return 0
        eff     = CQI_EFFICIENCY.get(cqi, 1.0)
        prb_bps = eff * PRB_BPS_FACTOR
        needed  = math.ceil(required_bps / prb_bps)
        needed  = min(needed, TOTAL_PRBS_RF)
        return math.ceil(needed / TOTAL_PRBS_RF * 100)

    def compute_sla_allocation(self, ue_data, f1ap_to_slice):
        if not ue_data:
            return {}
        min_req = {}
        for f1ap, metrics in ue_data.items():
            sd   = f1ap_to_slice.get(f1ap, 2)
            prof = SLICE_PROFILES[sd]
            pct  = self._required_prb_pct(prof["required_dl_bps"], metrics["cqi"])
            min_req[f1ap] = min(pct, prof["max_prb_ceiling"])
        total = sum(min_req.values())
        if total > 100:
            scale = 100 / total
            for f in min_req:
                min_req[f] = max(0, math.floor(min_req[f] * scale))
        leftover = max(0, 100 - sum(min_req.values()))
        cqi_sum  = sum(ue_data[f]["cqi"] for f in ue_data if ue_data[f]["cqi"] > 0)
        result   = {}
        for f1ap, metrics in ue_data.items():
            sd   = f1ap_to_slice.get(f1ap, 2)
            prof = SLICE_PROFILES[sd]
            bonus = 0
            if cqi_sum > 0 and leftover > 0:
                share = metrics["cqi"] / cqi_sum
                bonus = min(int(leftover * share),
                            prof["max_prb_ceiling"] - min_req[f1ap])
                bonus = max(0, bonus)
            final_min = min_req[f1ap]
            final_max = min(final_min + bonus, 100)
            result[f1ap] = {
                "min_prb":    final_min,
                "max_prb":    final_max,
                "slice_name": prof["label"],
                "cqi":        metrics["cqi"],
            }
        return result

    def _control_loop(self):
        rnti_to_f1ap_phy  = {}
        rnti_to_f1ap_virt = {}
        virt_rnti_slice   = {}
        print(f"[CTRL] Scenario B — 3 physical + 3 virtual UEs")
        print(f"[CTRL] RF  E2 node: {E2_NODE_RF}")
        print(f"[CTRL] ZMQ E2 node: {E2_NODE_ZMQ}")

        while self.running:
            time.sleep(self.control_interval)
            with self.lock:
                active = {k:v for k,v in self.ue_metrics.items()
                          if time.time()-v["timestamp"] < 10}

            phy_rntis  = sorted([r for r in active if r < 0xF001])
            virt_rntis = sorted([r for r in active if r >= 0xF001])

            for i, r in enumerate(phy_rntis[:3]):
                rnti_to_f1ap_phy[r] = i
            for i, r in enumerate(virt_rntis[:3]):
                rnti_to_f1ap_virt[r] = i
                if r not in virt_rnti_slice:
                    virt_rnti_slice[r] = VIRT_SLICE_ORDER[i % 3]

            phy_data  = {rnti_to_f1ap_phy[r]:  active[r]
                         for r in phy_rntis[:3]  if r in rnti_to_f1ap_phy}
            virt_data = {rnti_to_f1ap_virt[r]: active[r]
                         for r in virt_rntis[:3] if r in rnti_to_f1ap_virt}
            virt_f1ap_to_slice = {rnti_to_f1ap_virt[r]: virt_rnti_slice[r]
                                  for r in virt_rntis[:3] if r in rnti_to_f1ap_virt}

            phy_allocs  = self.compute_sla_allocation(phy_data,  PHY_F1AP_TO_SLICE)
            virt_allocs = self.compute_sla_allocation(virt_data, virt_f1ap_to_slice)

            t = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"\n{t} [CTRL] === Scenario B SLA PRB Allocation ===")
            print(f"  {'DU':>4} {'Slice':>11}  F1AP  RNTI    CQI  DL_Mbps  PRB_min  PRB_max")
            print(f"  {'-'*70}")

            for fid, alloc in phy_allocs.items():
                rl   = [r for r,f in rnti_to_f1ap_phy.items() if f==fid]
                rnti = rl[0] if rl else "?"
                m    = phy_data.get(fid, {})
                dl   = m.get("dl_brate", 0)/1e6
                print(f"  {'RF':>4} {alloc['slice_name']:>11}     {fid}  "
                      f"{rnti:<6}  {alloc['cqi']:>3}  {dl:>7.2f}  "
                      f"{alloc['min_prb']:>7}  {alloc['max_prb']:>7}")
                try:
                    self.e2sm_rc.control_slice_level_prb_quota(
                        E2_NODE_RF, fid,
                        alloc["min_prb"], alloc["max_prb"],
                        dedicated_prb_ratio=100, ack_request=1)
                except Exception as e:
                    print(f"  [E2] RF F1AP={fid} FAILED: {e}")

            for fid, alloc in virt_allocs.items():
                rl   = [r for r,f in rnti_to_f1ap_virt.items() if f==fid]
                rnti = rl[0] if rl else "?"
                m    = virt_data.get(fid, {})
                dl   = m.get("dl_brate", 0)/1e6
                print(f"  {'ZMQ':>4} {alloc['slice_name']:>11}     {fid}  "
                      f"{rnti:<6}  {alloc['cqi']:>3}  {dl:>7.2f}  "
                      f"{alloc['min_prb']:>7}  {alloc['max_prb']:>7}")
                try:
                    self.e2sm_rc.control_slice_level_prb_quota(
                        E2_NODE_ZMQ, fid,
                        alloc["min_prb"], alloc["max_prb"],
                        dedicated_prb_ratio=100, ack_request=1)
                except Exception as e:
                    print(f"  [E2] ZMQ F1AP={fid} FAILED: {e}")

            prb_out = {}
            for r, fid in rnti_to_f1ap_phy.items():
                if fid in phy_allocs:
                    a = phy_allocs[fid]
                    prb_out[str(r)] = {"prb_min": a["min_prb"], "prb_max": a["max_prb"],
                                       "slice_name": a["slice_name"], "f1ap_id": fid}
            for r, fid in rnti_to_f1ap_virt.items():
                if fid in virt_allocs:
                    a = virt_allocs[fid]
                    prb_out[str(r)] = {"prb_min": a["min_prb"], "prb_max": a["max_prb"],
                                       "slice_name": a["slice_name"], "f1ap_id": fid}
            try:
                with open("/tmp/prb_decisions.json", "w") as f:
                    json.dump(prb_out, f)
            except:
                pass

    @xAppBase.start_function
    def start(self):
        threading.Thread(target=self._control_loop, daemon=True).start()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Scenario B xApp — 3 physical + 3 virtual UEs")
    p.add_argument("--config",           type=str, default="")
    p.add_argument("--http_server_port", type=int, default=8094)
    p.add_argument("--rmr_port",         type=int, default=4564)
    args = p.parse_args()

    xapp = CqiDrivenXappSixUE(args.config, args.http_server_port, args.rmr_port)
    xapp.e2sm_rc.set_ran_func_id(3)

    signal.signal(signal.SIGQUIT, xapp.signal_handler)
    signal.signal(signal.SIGTERM, xapp.signal_handler)
    signal.signal(signal.SIGINT,  xapp.signal_handler)

    xapp.start()

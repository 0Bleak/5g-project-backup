# PVTR  A Physical–Virtual O-RAN Testbed for FRMCS Slicing

PVTR is a hybrid physical–virtual O-RAN testbed for evaluating dynamic, slice-aware radio resource control for the Future Railway Mobile Communication System (FRMCS). The same 5G core, CU/DU, near-RT RIC, slice configuration, and xApp run unmodified across two execution modes:

- **Physical mode** — closes the control loop over a real USRP-based 5G radio and physical UEs.
- **Virtual mode** — replaces the over-the-air path with a ZeroMQ (ZMQ) transport driven by CQI traces collected on an operational train, for repeatable, high-speed railway-channel evaluation.

As a flagship use case, the **RSlice** xApp maps per-slice service state and channel quality to E2SM-RC PRB allocations, with a rule-based safety mask protecting critical traffic. This repository contains the full configuration, xApp implementations, and evaluation datasets needed to reproduce the testbed.

Full design rationale, architecture, and demo results are described in the accompanying paper: `_MSWim26_Demo__PVTR_FRMCS_testbed.pdf` (included in this repo).

---

## Architecture Overview

Two workstations run a 5G SA private network: one hosts the RAN (CU/DU) and near-RT RIC, the other hosts the 5G core. A CU connects to one RF DU serving physical UEs over a USRP X310, or to a ZMQ-connected set of software UEs replaying railway CQI traces. A single near-RT RIC instance hosts the slicing xApp, which performs SLA-driven, per-slice PRB allocation across all UEs over the standardized E2 interface (E2SM-RC).

Three railway service slices are modeled end-to-end, from core subscriber profiles down to per-slice radio scheduling:

| Slice       | Represents                                   | Priority |
| ----------- | --------------------------------------------- | -------- |
| CRITICAL    | ETCS / ATO / emergency voice (train control)  | 1        |
| PERFORMANCE | CCTV / video surveillance                     | 2        |
| BUSINESS    | Passenger Wi-Fi / best-effort traffic         | 3        |

---

## Repository Layout

| Path                    | Contents                                                             |
| ------------------------ | --------------------------------------------------------------------- |
| `open5gs/`               | Open5GS 5G core NF configs (AMF, SMF, UPF, NRF, UDM, UDR, etc.)      |
| `tower-1/configs/`        | srsRAN CU and DU configs — `du_x310.yml` (physical) / `du_zmq.yml` (virtual) |
| `ue/`                     | srsUE configs for virtual-mode (ZMQ) UEs — credentials are placeholders, see [SIM Provisioning](#sim-provisioning) |
| `xapps/`                  | RIC xApps: CQI-driven baseline, KBL, PPO, A2C, DQN, dynamic-PPO (RSlice variants), metrics logger |
| `scripts_robots_UGV/`     | Setup script for the Quectel RM530N-GL modem on the UGV UEs          |
| `traces/sncf_traces/`     | Railway CQI/traffic traces used to drive virtual-mode UEs            |
| `Physical_eval/` `virtual_eval/` | Logged evaluation data (SLA, throughput, PRB decisions) per scheduler, per mode |
| `figures/`                | Plots used in the paper                                               |

---

## Hardware

| Component   | Details                                                                |
| ----------- | ------------------------------------------------------------------------ |
| **Tower-1** | Dell Precision 5820 (or equivalent), Ubuntu 22.04 — runs CU/DU, near-RT RIC, xApp |
| **Tower-2** | Dell Precision 5820 (or equivalent), Ubuntu 22.04 — runs Open5GS core, traffic generator |
| **Radio**   | USRP X310 (2x UBX-160), connected to Tower-1 via 10GbE                |
| **UE 1**    | Jetson Orin Nano + Quectel RM530N-GL modem — CRITICAL slice           |
| **UE 2**    | Jetson Orin Nano + Quectel RM530N-GL modem — PERFORMANCE slice        |
| **UE 3**    | Any 5G SA capable phone — BUSINESS slice                              |

Virtual mode requires no radio hardware: the USRP and physical UEs are replaced by `srsUE` instances driven by ZMQ and the traces in `traces/sncf_traces/`.

---

## Software Versions

| Component   | Software       | Version                       |
| ----------- | -------------- | ------------------------------ |
| gNB CU/DU   | [srsRAN Project](https://github.com/srsran/srsRAN_Project) | release_25_10-192-g4bf1543936 |
| 5G Core     | [Open5GS](https://github.com/open5gs/open5gs)        | 2.7.6                          |
| Near-RT RIC | [O-RAN SC RIC](https://wiki.o-ran-sc.org/) | i-release (Docker Compose)     |
| Database    | MongoDB        | 8.0                            |

---

## Network Parameters

| Parameter  | Value                   |
| ---------- | ----------------------- |
| PLMN       | 00101 (MCC=001, MNC=01) |
| Band       | 3 (FDD)                 |
| DL ARFCN   | 368500 (1842.5 MHz)     |
| Bandwidth  | 10 MHz (5–20 MHz configurable) |
| SCS        | 15 kHz                  |
| PRBs       | 25                       |
| TAC        | 7                        |
| DNN/APN    | srsapn                  |
| UE IP Pool | 10.45.0.0/16             |

### Network Slices (S-NSSAI)

| Slice       | SST | SD     | Priority |
| ----------- | --- | ------ | -------- |
| CRITICAL    | 1   | 000003 | 1        |
| PERFORMANCE | 1   | 000001 | 2        |
| BUSINESS    | 1   | 000002 | 3        |

---

## Reproducing the Testbed

### 1. Build/install the core components

1. Build **srsRAN Project** on Tower-1 (CU/DU host), following the [srsRAN build guide](https://docs.srsran.com/projects/project/en/latest/). Use the CU/DU configs in `tower-1/configs/` as a starting point — `cu.yml` + `du_x310.yml` for physical mode, `cu.yml` + `du_zmq.yml` for virtual mode.
2. Install **Open5GS** on Tower-2 and copy the NF configs from `open5gs/` into `/etc/open5gs/`. Adjust `amf`, `cu_cp.amf.addr`, and NF `sbi`/`ngap` addresses in both the Open5GS and CU configs to match your two-host network layout.
3. Deploy the **O-RAN SC near-RT RIC** (i-release) via Docker Compose on Tower-1, per the [O-RAN SC RIC deployment guide](https://wiki.o-ran-sc.org/display/RICP).

### 2. SIM Provisioning

This repo does **not** ship real SIM/USIM credentials. Before attaching any UE (physical or virtual):

1. Get sims & their credentials .
2. Register each subscriber in the Open5GS WebUI/subscriber DB with a unique IMSI under PLMN `00101`, mapped to the S-NSSAI of its intended slice (see table above).
3. Program those same `K`/`OPc`/IMSI values into (from your sim vendor):
   - The physical SIM cards (via a programmable SIM card + a SIM writer, or your MNO/test-SIM provider), for `UE 1`–`UE 3`.
   - The `[usim]` section of `ue/ue_01.conf`, `ue_02.conf`, `ue_03.conf` for virtual-mode `srsUE` instances (each currently contains placeholder values).

Never commit real K/OPc/IMSI values to version control.

### 3. Bring up the RAN and core

1. Start the Open5GS NFs on Tower-2 (`open5gs-nrfd`, `amfd`, `smfd`, `upfd`, etc.).
2. Start the CU/DU on Tower-1:
   - Physical mode: connect the USRP X310 over 10GbE, then launch `gnb` with `cu.yml` + `du_x310.yml`.
   - Virtual mode: launch `gnb` with `cu.yml` + `du_zmq.yml`, then start one `srsUE` per UE config in `ue/`, each pointed at a ZMQ port pair matching the DU.
3. Attach UEs — physical UEs over the air, or `srsUE` instances in virtual mode — and confirm each registers into its intended slice (`open5gs-dbctl` / AMF logs).

### 4. Run the RIC and an xApp

1. Bring up the near-RT RIC (Docker Compose stack).
2. Onboard and launch one of the xApps in `xapps/` (channel-aware baseline, KBL, or an RSlice RL agent — PPO/A2C/DQN/dynamic-PPO). Each xApp subscribes to per-UE CQI/throughput over the platform's metrics interface, computes a per-slice PRB allocation, and pushes it to the DU scheduler via E2SM-RC, closing the observe-decide-enforce loop described in the paper.
3. `xapps/metrics_logger.py` records live telemetry (CQI, delivered rate, PRB decisions, SLA indicators) for offline analysis.

### 5. Switching to virtual mode

Virtual mode swaps the USRP/physical-UE path for `srsUE` instances over ZMQ, replaying the railway CQI/traffic traces in `traces/sncf_traces/` — no radio hardware required. The RIC, xApp, and core are otherwise untouched, so the same control loop runs against live over-the-air conditions or repeatable train-collected channel dynamics.

The RSlice agents shipped in `xapps/` were trained online on real CQI data collected from SNCF trains (up to 350 km/h) rather than on synthetic channels — this platform is the substrate they run and were evaluated on, not the training pipeline. For the training methodology and the full labeled dataset, see the paper and the companion IEEE DataPort release referenced below. `Physical_eval/` and `virtual_eval/` contain the logged runs behind the paper's results, kept here for reference rather than as a how-to.

---

## Physical UE Networking (UGV modems)

`scripts_robots_UGV/connect5g.sh` installs a helper script on each Jetson-based UGV that rebinds the Quectel RM530N-GL modem to `cdc_ether`, brings up its `usb2` interface via DHCP, and routes the UE IP pool (`10.45.0.0/16`) over it. Run it after registering the modem's SIM as described above.

---

## Citation

If you use PVTR, please cite:

> M. Tamimi, D. Kule Mukuhi, L. Mendiboure, S. Cherrier, R. Langar, M. Berbineau, "Demo: PVTR, a Physical–Virtual O-RAN Testbed for FRMCS Slicing," 2026.

Related work:

- D. K. Mukuhi, L. Mendiboure, R. Langar, R. Fargeon, S. Cherrier, M. Berbineau, P.-Y. Petton, "Application-aware slicing for FRMCS: A deep reinforcement learning approach," *IEEE Transactions on Network and Service Management*, 2026.
- D. Kule Mukuhi et al., "Spatio-temporal dataset of FRMCS (5G) traffic from railway network," IEEE DataPort, Apr. 2026. [Link](https://ieee-dataport.org/documents/spatio-temporal-dataset-frmcs-5g-traffic-railway-network)

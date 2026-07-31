# 5G SA Private Network 
---

## Architecture Overview

Two Dell Precision 5820 workstations running a 5G SA private network with one CU connecting one RF DU serving three physical UEs via USRP X310. A single OSC Near-RT RIC instance hosts a CQI-driven xApp performing SLA-driven PRB allocation across all UEs.

---

## Hardware

| Component   | Details                                                                        |
| ----------- | ------------------------------------------------------------------------------ |
| **Tower-1** | Dell Precision 5820, Ubuntu 22.04, hostname: ligm-Precision-5820-Tower-1       |
| **Tower-2** | Dell Precision 5820, Ubuntu 22.04, hostname: ligm-Precision-5820-Tower-2       |
| **Radio**   | USRP X310 (2x UBX-160), connected to Tower-1 via 10GbE at 192.168.40.2         |
| **UE 1**    | Waveshare UGV Robot (Jetson Orin Nano) + Quectel RM530N-GL — CRITICAL slice    |
| **UE 2**    | Waveshare UGV Robot (Jetson Orin Nano) + Quectel RM530N-GL — PERFORMANCE slice |
| **UE 3**    | Google Pixel (GrapheneOS) — BUSINESS slice                                     |

---

## Network Parameters

| Parameter  | Value                   |
| ---------- | ----------------------- |
| PLMN       | 00101 (MCC=001, MNC=01) |
| Band       | 3 (FDD)                 |
| DL ARFCN   | 368500 (1842.5 MHz)     |
| Bandwidth  | 5 MHz                   |
| SCS        | 15 kHz                  |
| PRBs       | 25                      |
| TAC        | 7                       |
| DNN/APN    | srsapn                  |
| UE IP Pool | 10.45.0.0/16            |

### Network Slices

| Slice       | SD     | Priority | Physical UE | IMSI            |
| ----------- | ------ | -------- | ----------- | --------------- |
| CRITICAL    | 000003 | 1        | Robot 1     | 001010000000005 |
| PERFORMANCE | 000001 | 2        | Robot 2     | 001010000000004 |
| BUSINESS    | 000002 | 3        | Pixel       | 001010000000003 |

### SIM Credentials (all UEs share same K/OPc)

| Field | Value                            |
| ----- | -------------------------------- |
| K     | 0c0a34601d4f07677303652c0462535b |
| OPc   | 63bfa50ee6523365ff14c1f45f88737d |
| AMF   | 8000                             |

---

## Software Versions

| Component   | Software       | Version                       |
| ----------- | -------------- | ----------------------------- |
| gNB CU/DU   | srsRAN Project | release_25_10-192-g4bf1543936 |
| 5G Core     | Open5GS        | 2.7.6                         |
| Near-RT RIC | O-RAN SC RIC   | i-release (Docker Compose)    |
| Database    | MongoDB        | 8.0                           |

---

## Virtual Mode Extension

The same testbed supports a **virtual mode** where the physical USRP radio is replaced by a ZeroMQ (ZMQ) transport while the core network, controller, and slice logic remain unchanged. This enables direct comparison between physical and virtualized behavior:

- **Physical mode**: DU drives USRP X310 with real UEs over the air
- **Virtual mode**: DU uses ZMQ transport with software-based UEs running in network namespaces
- The same xApp and core configuration run in both modes

This hybrid physical/virtual capability is crucial because virtual-only evaluation can misestimate what a slice controller does on real hardware — the two modes yield different service outcomes, illustrating why physical experimentation matters for railway slice control.

### Virtual Mode Configuration

| Aspect     | Physical                | Virtual                     |
| ------------| -------------------------| -----------------------------|
| Radio      | USRP X310               | ZMQ transport               |
| UEs        | Real devices            | srsUE in network namespaces |
| CQI Source | Live RF measurements    | Injected from trace files   |
| Bandwidth  | 5-20 MHz (configurable) | Matches physical            |
| Controller | Same xApp               | Same xApp                   |
| Core       | Same Open5GS            | Same Open5GS                |
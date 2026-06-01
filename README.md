# 5G SA Private Network — Hybrid Physical + Virtual Testbed
# Full Replication Guide

## Architecture Overview

Two Dell Precision 5820 workstations running a 5G SA private network with one shared CU connecting two DUs — one RF DU serving physical UEs via USRP X310 and one ZMQ DU serving virtual UEs over GNU Radio ZMQ. Both DUs register simultaneously on a single OSC Near-RT RIC instance. A CQI injection proxy replaces virtual UE CQI with real SNCF train measurement traces. A single xApp performs SLA-driven PRB allocation across all UEs on both DUs.

## Measurement Scenarios

| Scenario | Physical UEs | Virtual UEs | Total UEs | Bandwidth | Traffic |
|----------|-------------|-------------|-----------|-----------|---------|
| A — Low Density | 3 robots | 0 | 3 | 5 MHz | Nominal UIC spec |
| B — Medium Density | 3 robots | 3 | 6 | 10 MHz | Overloaded |
| C — Very High Density | 3 robots | 7 | 10 | 10 MHz | Overloaded |

Scenario A is complete. Scenario B is complete. Scenario C is the active measurement campaign.

## ZMQ Scalability Limitation (Scenario C)

Simultaneous attachment of more than 3 virtual UEs over ZeroMQ causes channel saturation due to the synchronous nature of the GNU Radio add_cc combiner which blocks the entire pipeline waiting for samples from all UEs simultaneously. This is a documented architectural limit of srsRAN + ZeroMQ. Barker et al. (arXiv:2502.00715, Clemson University, 2025) report the same ceiling at 3 concurrent ZMQ UEs with approximately 28 Mbps total unsaturated throughput on an identical testbed (OSC RIC + srsRAN + GNU Radio slicing). Their validated solution for 12 UEs is batching in groups of 3. Scenario C adopts the same strategy: 7 virtual UEs run in rotating groups of 3, with at most 3 transmitting simultaneously at any given time.

## Hardware

| Component | Details |
|-----------|---------|
| Tower-1 | Dell Precision 5820, Ubuntu 22.04, hostname: ligm-Precision-5820-Tower-1 |
| Tower-2 | Dell Precision 5820, Ubuntu 22.04, hostname: ligm-Precision-5820-Tower-2 |
| Radio | USRP X310 (2x UBX-160), connected to Tower-1 via 10GbE at 192.168.40.2 |
| UE 1 | Waveshare UGV Robot (Jetson Orin Nano) + Quectel RM530N-GL — CRITICAL slice |
| UE 2 | Waveshare UGV Robot (Jetson Orin Nano) + Quectel RM530N-GL — PERFORMANCE slice |
| UE 3 | Google Pixel (GrapheneOS) — BUSINESS slice |

## Network Parameters

| Parameter | Value |
|-----------|-------|
| PLMN | 00101 (MCC=001, MNC=01) |
| Band | 3 (FDD) |
| DL ARFCN | 368500 (1842.5 MHz) |
| Bandwidth | 5 MHz (Scenario A) / 10 MHz (Scenarios B and C) |
| SCS | 15 kHz |
| PRBs | 25 (5 MHz) / 52 (10 MHz) |
| TAC | 7 |
| DNN/APN | srsapn |
| UE IP Pool | 10.45.0.0/16 |

## Network Slices

| Slice | SD | Priority | Physical UE | IMSI Physical | Virtual UE | IMSI Virtual |
|-------|----|----------|-------------|---------------|------------|--------------|
| CRITICAL | 000003 | 1 | Robot 1 | 001010000000005 | vUE1 | 001010000000006 |
| PERFORMANCE | 000001 | 2 | Robot 2 | 001010000000004 | vUE2 | 001010000000007 |
| BUSINESS | 000002 | 3 | Pixel | 001010000000003 | vUE3 | 001010000000008 |

Additional virtual UEs for Scenario C:

| Slice | SD | Virtual UE | IMSI Virtual |
|-------|----|------------|--------------|
| CRITICAL | 000003 | vUE4 | 001010000000009 |
| PERFORMANCE | 000001 | vUE5 | 001010000000010 |
| BUSINESS | 000002 | vUE6 | 001010000000011 |

## SIM Credentials (all UEs share same K/OPc)

| Field | Value |
|-------|-------|
| K | 0c0a34601d4f07677303652c0462535b |
| OPc | 63bfa50ee6523365ff14c1f45f88737d |
| AMF | 8000 |

## Software Versions

| Component | Software | Version |
|-----------|----------|---------|
| gNB CU/DU | srsRAN Project | release_25_10-192-g4bf1543936 |
| srsUE | srsRAN 4G | 25.10.0 (commit 6bcbd9e5b) |
| 5G Core | Open5GS | 2.7.6 |
| Near-RT RIC | O-RAN SC RIC | i-release (Docker Compose) |
| Database | MongoDB | 8.0 |
| GNU Radio | GNU Radio | 3.10.x (system package) |

## Why Single RIC Works for Both DUs

The OSC RIC e2mgr stores E2 node registrations in Redis using ranName as the unique key, derived from PLMN + gnb_id + gnb_du_id. Previously both DUs used gnb_id 411 (hex 00019b), so the second DU overwrote the first in Redis. The fix assigns distinct gnb_id values: RF DU uses gnb_id 531 (hex 00000213) producing ranName gnbd_001_001_00000213_0, and ZMQ DU uses gnb_id 532 producing ranName gnbd_001_001_00000213_1. Both coexist in a single RIC instance. The second RIC instance (oran-sc-ric-2) is no longer needed and has been removed.

The ZMQ DU E2 bind address is 10.0.2.2 — a secondary IP manually added to the RIC Docker bridge on every reboot (see Phase 4).

## File Locations

### Tower-1

| File | Path |
|------|------|
| CU config | ~/srsRAN_Project_clean/configs/ligm/cu.yml |
| RF DU config | ~/srsRAN_Project_clean/configs/ligm/du_x310.yml |
| ZMQ DU config | ~/5g-virtual/du_zmq.yml |
| CU binary | ~/srsRAN_Project_clean/build/apps/cu/srscu |
| DU binary | ~/srsRAN_Project_clean/build/apps/du/srsdu |
| srsUE binary | /usr/local/bin/srsue |
| srsUE lib fix | /etc/ld.so.conf.d/srsran.conf |
| xApp Scenario A | ~/oran-sc-ric/xApps/python/cqi_driven_xapp_three_phy.py |
| xApp Scenario B/C | ~/oran-sc-ric/xApps/python/cqi_driven_xapp_six_ue.py |
| Logger v2 (Scenario A, port 8001) | ~/oran-sc-ric/xApps/python/metrics_logger_v2.py |
| Logger v3 (Scenario B/C, port 8002) | ~/oran-sc-ric/xApps/python/metrics_logger_v3.py |
| Virtual UE configs | ~/5g-virtual/ue1.conf to ue7.conf |
| ZMQ broker 3 UEs (Scenario B) | ~/5g-virtual/zmq_broker_3ue.py |
| ZMQ broker 6 UEs (Scenario C) | ~/5g-virtual/zmq_broker_6ue.py |
| CQI injector merged | ~/5g-virtual/cqi_injector.py |
| CQI injector virtual only | ~/5g-virtual/cqi_injector_virtual.py |
| Virtual UE traffic generator | ~/5g-virtual/virtual_ue_traffic.py |
| SNCF traces (183 files) | ~/5g-virtual/sncf_traces/ |
| RIC docker compose | ~/oran-sc-ric/docker-compose.yml |
| RIC .env | ~/oran-sc-ric/.env |
| srsRAN performance script | ~/srsRAN_Project_clean/scripts/srsran_performance |
| Datasets | ~/datasets/ |

### Tower-2

| File | Path |
|------|------|
| AMF config | /etc/open5gs/amf.yaml |
| SMF config | /etc/open5gs/smf.yaml |
| UPF config | /etc/open5gs/upf.yaml |
| NRF config | /etc/open5gs/nrf.yaml |
| Traffic server | ~/traffic_server.py |
| Subscriber dump | ~/5g-project-backup/tower-2/subscribers_dump.json |

### Robots (Jetson Orin Nano)

| File | Path |
|------|------|
| connect5g script | /usr/local/bin/connect-5g.sh |
| dhclient hook | /etc/dhcp/dhclient-exit-hooks.d/no-default-route |
| dhclient config | /etc/dhcp/dhclient-usb2.conf |
| Critical traffic | ~/critical_traffic.py |
| Performance traffic | ~/performance_traffic.py |

## Full Startup Procedure

### Phase 1: Tower-2 — Core Network

```bash
sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -C POSTROUTING -s 10.45.0.0/16 ! -o ogstun -j MASQUERADE 2>/dev/null \
  || sudo iptables -t nat -A POSTROUTING -s 10.45.0.0/16 ! -o ogstun -j MASQUERADE
sudo iptables -C FORWARD -i ogstun -o eno1 -j ACCEPT 2>/dev/null \
  || sudo iptables -I FORWARD 1 -i ogstun -o eno1 -j ACCEPT
sudo iptables -C FORWARD -i eno1 -o ogstun -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null \
  || sudo iptables -I FORWARD 2 -i eno1 -o ogstun -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo ufw disable
sudo systemctl restart open5gs-nrfd
sleep 2
sudo systemctl restart open5gs-scpd open5gs-ausfd open5gs-udmd \
  open5gs-udrd open5gs-pcfd open5gs-bsfd open5gs-smfd open5gs-upfd open5gs-amfd
sudo ss -lnp | grep 38412
```

### Phase 2: Tower-1 — System Prerequisites (after every reboot)

```bash
cd ~/srsRAN_Project_clean
sudo bash scripts/srsran_performance
sudo ip link set enp9s0 mtu 9000
sudo sysctl -w net.core.wmem_max=24912805
sudo ip netns add vue1 2>/dev/null || true
sudo ip netns add vue2 2>/dev/null || true
sudo ip netns add vue3 2>/dev/null || true
sudo ip netns add vue4 2>/dev/null || true
sudo ip netns add vue5 2>/dev/null || true
sudo ip netns add vue6 2>/dev/null || true
sudo ip netns add vue7 2>/dev/null || true
```

### Phase 3: Tower-1 — Start RIC

```bash
cd ~/oran-sc-ric
docker compose up -d
sleep 20
docker logs ric_submgr 2>&1 | tail -3
# Must show: RMR is ready now ...
```

### Phase 4: Tower-1 — Add ZMQ DU E2 bind address (after every reboot)

```bash
BRIDGE=$(ip link | grep br- | head -1 | awk '{print $2}' | tr -d ':')
sudo ip addr add 10.0.2.2/24 dev $BRIDGE
```

### Phase 5: Tower-1 — Deploy xApps to RIC container

```bash
cd ~/oran-sc-ric
docker compose exec python_xapp_runner pip3 install websocket-client

# Scenario A
docker cp ~/oran-sc-ric/xApps/python/cqi_driven_xapp_three_phy.py python_xapp_runner:/opt/xApps/
docker cp ~/oran-sc-ric/xApps/python/metrics_logger_v2.py python_xapp_runner:/opt/xApps/

# Scenario B and C
docker cp ~/oran-sc-ric/xApps/python/cqi_driven_xapp_six_ue.py python_xapp_runner:/opt/xApps/
docker cp ~/oran-sc-ric/xApps/python/metrics_logger_v3.py python_xapp_runner:/opt/xApps/

docker exec python_xapp_runner chmod +x \
  /opt/xApps/cqi_driven_xapp_three_phy.py \
  /opt/xApps/cqi_driven_xapp_six_ue.py \
  /opt/xApps/metrics_logger_v2.py \
  /opt/xApps/metrics_logger_v3.py
```

### Phase 6: Tower-1 — Start CU

```bash
cd ~/srsRAN_Project_clean/build/apps/cu
sudo ./srscu -c ~/srsRAN_Project_clean/configs/ligm/cu.yml
# Wait for: N2: Connection to AMF on 192.168.0.3:38412 completed
```

### Phase 7: Tower-1 — Start RF DU

```bash
cd ~/srsRAN_Project_clean/build/apps/du
sudo ./srsdu -c ~/srsRAN_Project_clean/configs/ligm/du_x310.yml
# Wait for: E2AP: Connection to Near-RT-RIC on 10.0.2.10:36421 completed
# Wait for: Remote control server listening on 0.0.0.0:8001
```

### Phase 8: Tower-1 — Start Virtual UEs

```bash
# Scenario B — 3 virtual UEs simultaneously
sudo -b srsue ~/5g-virtual/ue1.conf
sudo -b srsue ~/5g-virtual/ue2.conf
sudo -b srsue ~/5g-virtual/ue3.conf

# Scenario C — start first batch of 3 simultaneously
sudo -b srsue ~/5g-virtual/ue1.conf
sudo -b srsue ~/5g-virtual/ue2.conf
sudo -b srsue ~/5g-virtual/ue3.conf
# After first batch connected, kill and start second batch:
# sudo pkill -9 -f srsue
# sudo -b srsue ~/5g-virtual/ue4.conf
# sudo -b srsue ~/5g-virtual/ue5.conf
# sudo -b srsue ~/5g-virtual/ue6.conf
```

### Phase 9: Tower-1 — Start ZMQ Broker

```bash
# Scenario B
python3 ~/5g-virtual/zmq_broker_3ue.py

# Scenario C
python3 ~/5g-virtual/zmq_broker_6ue.py
```

### Phase 10: Tower-1 — Start ZMQ DU

```bash
cd ~/srsRAN_Project_clean/build/apps/du
sudo ./srsdu -c ~/5g-virtual/du_zmq.yml
# Wait for: E2AP: Connection to Near-RT-RIC on 10.0.2.10:36421 completed
# Wait for: Remote control server listening on 0.0.0.0:8003
# Virtual UEs should show: PDU Session Establishment successful
```

### Phase 11: Connect Physical UEs

Robot 1 first (CRITICAL), Robot 2 second (PERFORMANCE), Pixel last (BUSINESS). On each robot:

```bash
sudo connect-5g.sh
# Expected: SUCCESS: 5G connected
```

For Pixel: toggle airplane mode off.

### Phase 12: Verify Both DUs on Single RIC

```bash
docker exec ric_dbaas redis-cli KEYS '*RAN*'
# Must show:
# {e2Manager},RAN:gnbd_001_001_00000213_0
# {e2Manager},RAN:gnbd_001_001_00000213_1
```

### Phase 13: Start CQI Injector

```bash
python3 ~/5g-virtual/cqi_injector.py --dataset_dir ~/5g-virtual/sncf_traces/
# Wait for: Status: 3 physical + 3 virtual UEs
```

### Phase 14: Start Robot Traffic (on each robot via SSH)

```bash
# Robot 1 (CRITICAL)
python3 ~/critical_traffic.py --server 10.45.0.1 --duration 999999

# Robot 2 (PERFORMANCE)
python3 ~/performance_traffic.py --server 10.45.0.1 --duration 999999

# Pixel: open YouTube or any streaming app
```

### Phase 15: Start Virtual UE Traffic

```bash
python3 ~/5g-virtual/virtual_ue_traffic.py
```

### Phase 16: Start Traffic Server on Tower-2

```bash
python3 ~/traffic_server.py
```

### Phase 17: Start xApp

```bash
cd ~/oran-sc-ric

# Scenario A
docker compose exec python_xapp_runner python3 /opt/xApps/cqi_driven_xapp_three_phy.py

# Scenario B and C
docker compose exec python_xapp_runner python3 /opt/xApps/cqi_driven_xapp_six_ue.py
```

### Phase 18: Start Logger and Collect Dataset

```bash
cd ~/oran-sc-ric
docker exec python_xapp_runner bash -c 'rm -f /tmp/ue_metrics_log.csv /tmp/prb_decisions.json'

# Scenario A
docker compose exec python_xapp_runner python3 /opt/xApps/metrics_logger_v2.py

# Scenario B and C
docker compose exec python_xapp_runner python3 /opt/xApps/metrics_logger_v3.py
```

Monitor in real time:

```bash
docker exec python_xapp_runner bash -c 'tail -f /tmp/ue_metrics_log.csv'
```

Collect when done:

```bash
docker cp python_xapp_runner:/tmp/ue_metrics_log.csv \
  ~/datasets/scen_X_$(date +%Y%m%d_%H%M).csv
```

## Terminal Layout (Tower-1)

| Terminal | Process |
|----------|---------|
| 1 | CU (srscu) |
| 2 | RF DU (du_x310.yml) |
| 3 | ZMQ DU (du_zmq.yml) |
| 4 | Virtual UEs (srsue background) |
| 5 | ZMQ Broker |
| 6 | CQI Injector |
| 7 | Virtual UE Traffic |
| 8 | xApp |
| 9 | Logger |
| 10 | General commands |

## Key Implementation Notes

- **Single RIC for both DUs.** gnb_id 531 on RF DU and gnb_id 532 on ZMQ DU produce distinct ranNames. No second RIC instance needed.
- **10.0.2.2 must be added after every reboot.** It is the E2 bind address for the ZMQ DU on the RIC Docker bridge. See Phase 4.
- **ZMQ startup order is critical.** Start UEs simultaneously, then broker, then ZMQ DU. The GNU Radio add_cc block requires all UE streams active before the DU connects. Do not stagger UE launches.
- **Scenario C uses batching of 3 virtual UEs at a time.** ZeroMQ saturation limit documented by Barker et al. arXiv:2502.00715.
- **Virtual UE RNTIs are remapped to 0xF001+ range** by the CQI injector to avoid RNTI collision with physical UEs.
- **F1AP-ID to slice mapping resets on CU/DU restart.** Always reconnect Robot 1 (CRITICAL) first, Robot 2 (PERFORMANCE) second, Pixel (BUSINESS) third.
- **Pixel CQI is always 5.** This is a known characteristic of the Quectel/Pixel modem combination in this RF environment. Use it as a ground truth anchor for RNTI identification in post-processing.
- **Slice assignment is server-side only.** COTS UEs send SD:0xffffff (wildcard). AMF resolves from MongoDB.
- **CQI is not available via E2SM-KPM.** It comes from the DU websocket port 8001 (RF DU) and 8003 (ZMQ DU), merged and injected on port 8002.
- **NAT rules lost on Tower-2 reboot.** Must reapply Phase 1.
- **srsUE library path.** /etc/ld.so.conf.d/srsran.conf must contain /usr/local/lib, run ldconfig after any srsRAN 4G install.

## Dataset Post-Processing

After collection, run the cleaning script to fix any slice mislabeling caused by reconnection events:

The RNTI-to-slice ground truth is:

| RNTI range | DU | Identity |
|------------|-----|---------|
| < 0xF001 and high UL brate ~4-5 Mbps | RF | CRITICAL Robot 1 IMSI 005 |
| < 0xF001 and UL brate ~0.24 Mbps | RF | PERFORMANCE Robot 2 IMSI 004 |
| < 0xF001 and CQI always 5 | RF | BUSINESS Pixel IMSI 003 |
| >= 0xF001 first remapped | ZMQ | CRITICAL vUE1 IMSI 006 |
| >= 0xF001 second remapped | ZMQ | PERFORMANCE vUE2 IMSI 007 |
| >= 0xF001 third remapped | ZMQ | BUSINESS vUE3 IMSI 008 |

## Troubleshooting

**ZMQ DU segfaults on E2 connection:** 10.0.2.2 not added to RIC bridge. Run Phase 4.

**CU rejects ZMQ DU with Duplicate served cell CGI:** Ensure du_zmq.yml has sector_id: 1 under cell_cfg.

**CU rejects ZMQ DU with Duplicate DU ID:** Ensure du_zmq.yml has gnb_du_id: 1 as top-level parameter.

**Only one DU in Redis after both connect:** gnb_id collision. Verify RF DU has gnb_id: 531 and ZMQ DU has gnb_id: 532.

**Virtual UEs stuck at Attaching with no PRACH:** Wrong startup order. Kill all, restart: UEs simultaneously first, then broker, then ZMQ DU.

**Virtual UEs all show preamble_index=0 and never complete RA with 6+ UEs:** Known srsUE 25.10 limit. Use batching of 3.

**xApp shows constant CQI=15 for virtual UEs:** xApp connecting to raw DU port 8003 instead of injector port 8002.

**Logger writes only 1 row:** websocket-client not installed in container. Run pip3 install websocket-client inside the container.

**Physical UE no IP after connect5g.sh:** Check AMF log on Tower-2: sudo tail -50 /var/log/open5gs/amf.log

**No traffic despite UE has IP:** NAT FORWARD rules missing on Tower-2. Reapply Phase 1.

## Subscriber Registration (if DB needs reset)

Run on Tower-2:

```bash
mongosh open5gs --eval '
db.subscribers.insertMany([
  {
    "imsi": "001010000000003",
    "security": {"k": "0c0a34601d4f07677303652c0462535b", "opc": "63bfa50ee6523365ff14c1f45f88737d", "amf": "8000"},
    "schema_version": 1, "access_restriction_data": 32, "subscriber_status": 0, "network_access_mode": 0,
    "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}},
    "slice": [{"sst": 1, "sd": "000002", "default_indicator": true,
      "session": [{"name": "srsapn", "type": 3,
        "qos": {"index": 9, "arp": {"priority_level": 8, "pre_emption_capability": 1, "pre_emption_vulnerability": 1}},
        "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}}}]}]
  },
  {
    "imsi": "001010000000004",
    "security": {"k": "0c0a34601d4f07677303652c0462535b", "opc": "63bfa50ee6523365ff14c1f45f88737d", "amf": "8000"},
    "schema_version": 1, "access_restriction_data": 32, "subscriber_status": 0, "network_access_mode": 0,
    "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}},
    "slice": [{"sst": 1, "sd": "000001", "default_indicator": true,
      "session": [{"name": "srsapn", "type": 3,
        "qos": {"index": 9, "arp": {"priority_level": 8, "pre_emption_capability": 1, "pre_emption_vulnerability": 1}},
        "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}}}]}]
  },
  {
    "imsi": "001010000000005",
    "security": {"k": "0c0a34601d4f07677303652c0462535b", "opc": "63bfa50ee6523365ff14c1f45f88737d", "amf": "8000"},
    "schema_version": 1, "access_restriction_data": 32, "subscriber_status": 0, "network_access_mode": 0,
    "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}},
    "slice": [{"sst": 1, "sd": "000003", "default_indicator": true,
      "session": [{"name": "srsapn", "type": 3,
        "qos": {"index": 9, "arp": {"priority_level": 8, "pre_emption_capability": 1, "pre_emption_vulnerability": 1}},
        "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}}}]}]
  },
  {
    "imsi": "001010000000006",
    "security": {"k": "0c0a34601d4f07677303652c0462535b", "opc": "63bfa50ee6523365ff14c1f45f88737d", "amf": "8000"},
    "schema_version": 1, "access_restriction_data": 32, "subscriber_status": 0, "network_access_mode": 0,
    "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}},
    "slice": [{"sst": 1, "sd": "000003", "default_indicator": true,
      "session": [{"name": "srsapn", "type": 3,
        "qos": {"index": 9, "arp": {"priority_level": 8, "pre_emption_capability": 1, "pre_emption_vulnerability": 1}},
        "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}}}]}]
  },
  {
    "imsi": "001010000000007",
    "security": {"k": "0c0a34601d4f07677303652c0462535b", "opc": "63bfa50ee6523365ff14c1f45f88737d", "amf": "8000"},
    "schema_version": 1, "access_restriction_data": 32, "subscriber_status": 0, "network_access_mode": 0,
    "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}},
    "slice": [{"sst": 1, "sd": "000001", "default_indicator": true,
      "session": [{"name": "srsapn", "type": 3,
        "qos": {"index": 9, "arp": {"priority_level": 8, "pre_emption_capability": 1, "pre_emption_vulnerability": 1}},
        "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}}}]}]
  },
  {
    "imsi": "001010000000008",
    "security": {"k": "0c0a34601d4f07677303652c0462535b", "opc": "63bfa50ee6523365ff14c1f45f88737d", "amf": "8000"},
    "schema_version": 1, "access_restriction_data": 32, "subscriber_status": 0, "network_access_mode": 0,
    "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}},
    "slice": [{"sst": 1, "sd": "000002", "default_indicator": true,
      "session": [{"name": "srsapn", "type": 3,
        "qos": {"index": 9, "arp": {"priority_level": 8, "pre_emption_capability": 1, "pre_emption_vulnerability": 1}},
        "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}}}]}]
  },
  {
    "imsi": "001010000000009",
    "security": {"k": "0c0a34601d4f07677303652c0462535b", "opc": "63bfa50ee6523365ff14c1f45f88737d", "amf": "8000"},
    "schema_version": 1, "access_restriction_data": 32, "subscriber_status": 0, "network_access_mode": 0,
    "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}},
    "slice": [{"sst": 1, "sd": "000003", "default_indicator": true,
      "session": [{"name": "srsapn", "type": 3,
        "qos": {"index": 9, "arp": {"priority_level": 8, "pre_emption_capability": 1, "pre_emption_vulnerability": 1}},
        "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}}}]}]
  },
  {
    "imsi": "001010000000010",
    "security": {"k": "0c0a34601d4f07677303652c0462535b", "opc": "63bfa50ee6523365ff14c1f45f88737d", "amf": "8000"},
    "schema_version": 1, "access_restriction_data": 32, "subscriber_status": 0, "network_access_mode": 0,
    "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}},
    "slice": [{"sst": 1, "sd": "000001", "default_indicator": true,
      "session": [{"name": "srsapn", "type": 3,
        "qos": {"index": 9, "arp": {"priority_level": 8, "pre_emption_capability": 1, "pre_emption_vulnerability": 1}},
        "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}}}]}]
  },
  {
    "imsi": "001010000000011",
    "security": {"k": "0c0a34601d4f07677303652c0462535b", "opc": "63bfa50ee6523365ff14c1f45f88737d", "amf": "8000"},
    "schema_version": 1, "access_restriction_data": 32, "subscriber_status": 0, "network_access_mode": 0,
    "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}},
    "slice": [{"sst": 1, "sd": "000002", "default_indicator": true,
      "session": [{"name": "srsapn", "type": 3,
        "qos": {"index": 9, "arp": {"priority_level": 8, "pre_emption_capability": 1, "pre_emption_vulnerability": 1}},
        "ambr": {"downlink": {"value": 1, "unit": 3}, "uplink": {"value": 1, "unit": 3}}}]}]
  }
])'
```

## Clean Shutdown

```bash
# Tower-1
sudo pkill -9 -f srsue
sudo pkill -f zmq_broker
sudo pkill -f cqi_injector
sudo pkill -f virtual_ue_traffic
sudo pkill -9 -f srsdu
sudo pkill -9 -f srscu
cd ~/oran-sc-ric && docker compose down
sudo ip netns del vue1 2>/dev/null
sudo ip netns del vue2 2>/dev/null
sudo ip netns del vue3 2>/dev/null
sudo ip netns del vue4 2>/dev/null
sudo ip netns del vue5 2>/dev/null
sudo ip netns del vue6 2>/dev/null
sudo ip netns del vue7 2>/dev/null

# Tower-2
sudo systemctl stop open5gs-amfd open5gs-smfd open5gs-upfd open5gs-nrfd \
  open5gs-scpd open5gs-ausfd open5gs-udmd open5gs-udrd open5gs-pcfd open5gs-bsfd
```

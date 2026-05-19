# 5G SA Private Network — Hybrid Physical + Virtual Testbed
# Full Replication Guide

## Architecture Overview

Two Dell Precision 5820 workstations running a 5G SA private network with:
- 3 physical UEs (2 Waveshare robots + 1 Google Pixel) on RF DU via USRP X310
- 3 virtual UEs (srsUE over ZMQ) on ZMQ DU with SNCF railway CQI injection
- 1 shared CU connecting to both DUs
- 2 independent OSC Near-RT RIC instances (one per DU) for full E2SM-RC PRB enforcement
- CQI injection proxy replacing virtual UE CQI with real SNCF train measurement traces
- xApp performing SLA-driven PRB allocation on both RICs simultaneously

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
| Bandwidth | 10 MHz |
| SCS | 15 kHz |
| PRBs | 52 |
| TAC | 7 |
| DNN/APN | srsapn |
| UE IP Pool | 10.45.0.0/16 |

## Network Slices

| Slice | SD | Priority | Physical UE | Virtual UE | IMSI (Physical) | IMSI (Virtual) |
|-------|----|----------|-------------|------------|-----------------|----------------|
| CRITICAL | 000003 | 1 | Robot 1 | vUE1 | 001010000000005 | 001010000000006 |
| PERFORMANCE | 000001 | 2 | Robot 2 | vUE2 | 001010000000004 | 001010000000007 |
| BUSINESS | 000002 | 3 | Pixel | vUE3 | 001010000000003 | 001010000000008 |

## SIM Credentials (all UEs share same K/OPc)

| Field | Value |
|-------|-------|
| K | 0c0a34601d4f07677303652c0462535b |
| OPc | 63bfa50ee6523365ff14c1f45f88737d |
| AMF | 8000 |

## Software Versions

| Component | Software | Version/Commit |
|-----------|----------|----------------|
| gNB CU/DU | srsRAN Project | release_25_10-192-g4bf1543936 |
| srsUE | srsRAN 4G | 25.10.0 (commit 6bcbd9e5b) |
| 5G Core | Open5GS | 2.7.6 |
| Near-RT RIC | O-RAN SC RIC | i-release (Docker Compose) |
| Database | MongoDB | 8.0 |
| GNU Radio | GNU Radio | 3.10.x (system package) |

## Network Topology
Tower-1 (192.168.0.2)                    Tower-2 (192.168.0.3)
┌─────────────────────────┐              ┌──────────────────────┐
│ CU (srscu)              │──── NGAP ───>│ AMF (Open5GS)        │
│   F1-C: 127.0.10.1      │              │   NGAP: 192.168.0.3  │
│                         │              │                      │
│ RF DU (srsdu)           │              │ SMF, UPF, NRF, etc   │
│   F1-C: 127.0.10.2      │              │   UPF GTP-U: 192.168.0.3 │
│   E2: 10.0.2.1 -> RIC 1 │              │   ogstun: 10.45.0.1  │
│   WS: port 8001         │              │                      │
│   Radio: USRP X310      │              │ MongoDB              │
│                         │              │   6 subscribers       │
│ ZMQ DU (srsdu)          │              └──────────────────────┘
│   F1-C: 127.0.10.5      │
│   E2: 10.0.4.1 -> RIC 2 │
│   WS: port 8003         │
│   Radio: ZMQ loopback   │
│   sector_id: 1           │
│   gnb_du_id: 1           │
│                         │
│ RIC 1 (Docker)          │
│   Network: 10.0.2.0/24  │
│   E2 term: 10.0.2.10    │
│   SCTP: 36421            │
│   xApp container:        │
│     python_xapp_runner   │
│                         │
│ RIC 2 (Docker, project=ric2) │
│   Network: 10.0.4.0/24  │
│   E2 term: 10.0.4.10    │
│   SCTP: 36421            │
│   xApp container:        │
│     python_xapp_runner_2 │
│                         │
│ ZMQ Broker (GNU Radio)  │
│   DL: 3000->3010/3100/3200 │
│   UL: 3001/3101/3201->3009 │
│                         │
│ 3x srsUE (ZMQ)         │
│   vue1: netns=vue1       │
│   vue2: netns=vue2       │
│   vue3: netns=vue3       │
│                         │
│ CQI Injector            │
│   Reads: 8001+8003       │
│   Serves: 8002 (merged)  │
│   Injects SNCF CQI on   │
│   virtual UE RNTIs       │
└─────────────────────────┘

## File Locations

### Tower-1

| File | Path |
|------|------|
| CU config | ~/srsRAN_Project_clean/configs/ligm/cu.yml |
| RF DU config | ~/srsRAN_Project_clean/configs/ligm/du_x310.yml |
| ZMQ DU config | ~/5g-virtual/du_zmq.yml |
| CU binary | ~/srsRAN_Project_clean/build/apps/cu/srscu |
| DU binary | ~/srsRAN_Project_clean/build/apps/du/srsdu |
| Monolithic gNB binary | ~/srsRAN_Project_clean/build/apps/gnb/gnb |
| srsUE binary | /usr/local/bin/srsue |
| srsUE lib fix | /etc/ld.so.conf.d/srsran.conf (contains /usr/local/lib) |
| xApp: cqi_driven_xapp.py | ~/oran-sc-ric/xApps/python/cqi_driven_xapp.py |
| xApp: metrics_logger_v2.py | ~/oran-sc-ric/xApps/python/metrics_logger_v2.py |
| Virtual UE configs | ~/5g-virtual/ue1.conf, ue2.conf, ue3.conf |
| ZMQ broker | ~/5g-virtual/zmq_broker.py |
| CQI injector (merged) | ~/5g-virtual/cqi_injector.py |
| CQI injector (virtual only) | ~/5g-virtual/cqi_injector_virtual.py |
| SNCF traces (183 files) | ~/5g-virtual/sncf_traces/ |
| RIC 1 docker compose | ~/oran-sc-ric/docker-compose.yml |
| RIC 1 .env | ~/oran-sc-ric/.env |
| RIC 2 docker compose | ~/oran-sc-ric-2/docker-compose.yml |
| RIC 2 .env | ~/oran-sc-ric-2/.env |
| RIC 2 configs | ~/oran-sc-ric-2/ric/configs/ |
| srsRAN performance script | ~/srsRAN_Project_clean/scripts/srsran_performance |
| Backup of everything | ~/5g-project-backup/tower-1/ |

### Tower-2

| File | Path |
|------|------|
| AMF config | /etc/open5gs/amf.yaml |
| SMF config | /etc/open5gs/smf.yaml |
| UPF config | /etc/open5gs/upf.yaml |
| NRF config | /etc/open5gs/nrf.yaml |
| All Open5GS configs | /etc/open5gs/*.yaml |
| Subscriber dump | ~/5g-project-backup/tower-2/subscribers_dump.json |
| Backup of everything | ~/5g-project-backup/tower-2/ |

### Robots (Jetson Orin Nano)

| File | Path |
|------|------|
| connect5g script | /usr/local/bin/connect-5g.sh |
| dhclient hook | /etc/dhcp/dhclient-exit-hooks.d/no-default-route |
| dhclient config | /etc/dhcp/dhclient-usb2.conf |

## Why Two RIC Instances

The OSC RIC e2mgr uses `ranName` as the unique key in Redis for E2 node registration. Both the RF DU and ZMQ DU derive their ranName from the same CU identity (PLMN 00101 + gnb_id 411), producing `gnbd_001_001_00019b_X`. When both DUs connect to the same RIC, the second overwrites the first. This is an OSC RIC limitation — it was not designed for multi-DU registration from the same gNB.

The solution: run two independent RIC instances on separate Docker networks. RIC 1 (10.0.2.0/24) serves the RF DU. RIC 2 (10.0.4.0/24) serves the ZMQ DU. Each RIC has its own Redis, e2mgr, e2term, submgr, and xApp runner. Both RICs provide full E2SM-RC PRB enforcement independently.

The CU accepted both DUs after setting `sector_id: 1` and `gnb_du_id: 1` on the ZMQ DU config (resolves "Duplicate served cell CGI" F1 Setup rejection). The CU sees them as du_index=0 (RF) and du_index=1 (ZMQ).

## Full Startup Procedure

### Phase 1: Tower-2 — Core Network

```bash
# 1a. NAT and forwarding (after every reboot)
sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -C POSTROUTING -s 10.45.0.0/16 ! -o ogstun -j MASQUERADE 2>/dev/null \
  || sudo iptables -t nat -A POSTROUTING -s 10.45.0.0/16 ! -o ogstun -j MASQUERADE
sudo iptables -C FORWARD -i ogstun -o eno1 -j ACCEPT 2>/dev/null \
  || sudo iptables -I FORWARD 1 -i ogstun -o eno1 -j ACCEPT
sudo iptables -C FORWARD -i eno1 -o ogstun -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null \
  || sudo iptables -I FORWARD 2 -i eno1 -o ogstun -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo ufw disable

# 1b. Start Open5GS
sudo systemctl restart open5gs-nrfd
sleep 2
sudo systemctl restart open5gs-scpd open5gs-ausfd open5gs-udmd \
  open5gs-udrd open5gs-pcfd open5gs-bsfd open5gs-smfd open5gs-upfd open5gs-amfd

# 1c. Verify AMF listening
sudo ss -lnp | grep 38412

# 1d. Verify subscribers (first time or after DB reset)
mongosh open5gs --eval 'db.subscribers.find({},{imsi:1,"slice.0.sd":1,_id:0}).forEach(printjson)'
# Must show 6 subscribers with correct SD values:
# IMSI 003 -> sd:000002, IMSI 004 -> sd:000001, IMSI 005 -> sd:000003
# IMSI 006 -> sd:000003, IMSI 007 -> sd:000001, IMSI 008 -> sd:000002
```

### Phase 2: Tower-1 — System Prerequisites (after every reboot)

```bash
cd ~/srsRAN_Project_clean
sudo bash scripts/srsran_performance
sudo ip link set enp9s0 mtu 9000
sudo sysctl -w net.core.wmem_max=24912805

# Network namespaces for virtual UEs
sudo ip netns add vue1 2>/dev/null || true
sudo ip netns add vue2 2>/dev/null || true
sudo ip netns add vue3 2>/dev/null || true
```

### Phase 3: Tower-1 — Start Both RICs

```bash
# RIC 1 (physical DU)
cd ~/oran-sc-ric
docker compose up -d
sleep 15
docker logs ric_submgr 2>&1 | tail -3
# Must show: RMR is ready now ...

# RIC 2 (virtual DU)
cd ~/oran-sc-ric-2
docker compose -p ric2 up -d
sleep 15
docker logs ric2_submgr 2>&1 | tail -3
# Must show: RMR is ready now ...
```

### Phase 4: Tower-1 — Deploy xApps to Both Containers

```bash
# RIC 1 container
cd ~/oran-sc-ric
docker compose exec python_xapp_runner pip3 install websocket-client
docker cp ~/oran-sc-ric/xApps/python/cqi_driven_xapp.py python_xapp_runner:/opt/xApps/
docker cp ~/oran-sc-ric/xApps/python/metrics_logger_v2.py python_xapp_runner:/opt/xApps/
docker exec python_xapp_runner chmod +x /opt/xApps/cqi_driven_xapp.py /opt/xApps/metrics_logger_v2.py

# RIC 2 container
docker exec python_xapp_runner_2 pip3 install websocket-client
docker cp ~/oran-sc-ric/xApps/python/cqi_driven_xapp.py python_xapp_runner_2:/opt/xApps/
docker exec python_xapp_runner_2 chmod +x /opt/xApps/cqi_driven_xapp.py
```

### Phase 5: Tower-1 — Start CU (dedicated terminal)

```bash
cd ~/srsRAN_Project_clean/build/apps/cu
sudo ./srscu -c ~/srsRAN_Project_clean/configs/ligm/cu.yml
# Wait for: N2: Connection to AMF on 192.168.0.3:38412 completed
```

### Phase 6: Tower-1 — Start RF DU (dedicated terminal)

```bash
cd ~/srsRAN_Project_clean/build/apps/du
sudo ./srsdu -c ~/srsRAN_Project_clean/configs/ligm/du_x310.yml
# Wait for:
#   F1-C: Connection to CU-CP on 127.0.10.1:38472 completed
#   E2AP: Connection to Near-RT-RIC on 10.0.2.10:36421 completed
#   Remote control server listening on 0.0.0.0:8001
```

### Phase 7: Tower-1 — Start Virtual UEs (dedicated terminal)

```bash
# Start UEs first — they wait for PHY init until DU starts
sudo srsue ~/5g-virtual/ue1.conf &
sudo srsue ~/5g-virtual/ue2.conf &
sudo srsue ~/5g-virtual/ue3.conf &
sleep 3
```

### Phase 8: Tower-1 — Start ZMQ Broker (dedicated terminal)

```bash
python3 ~/5g-virtual/zmq_broker.py
# Wait for: [BROKER] 3-UE ZMQ broker starting
```

### Phase 9: Tower-1 — Start ZMQ DU (dedicated terminal)

```bash
cd ~/srsRAN_Project_clean/build/apps/du
sudo ./srsdu -c ~/5g-virtual/du_zmq.yml
# Wait for:
#   F1-C: Connection to CU-CP on 127.0.10.1:38472 completed
#   E2AP: Connection to Near-RT-RIC on 10.0.4.10:36421 completed
#   Remote control server listening on 0.0.0.0:8003
# Virtual UEs should then show: Random Access Complete, PDU Session Establishment successful
```

### Phase 10: Connect Physical UEs

Robot 1 first (CRITICAL), Robot 2 second (PERFORMANCE), Pixel last (BUSINESS).

On each robot, before first use:
```bash
# One-time setup on each robot
sudo bash -c 'cat > /etc/dhcp/dhclient-exit-hooks.d/no-default-route << "EOF"
#!/bin/bash
if [ "$interface" = "usb2" ]; then
    /sbin/ip route del default via 192.168.225.1 2>/dev/null
    /sbin/ip route del default dev usb2 2>/dev/null
fi
EOF
chmod +x /etc/dhcp/dhclient-exit-hooks.d/no-default-route'

sudo bash -c 'cat > /etc/dhcp/dhclient-usb2.conf << "EOF"
interface "usb2" {
    request subnet-mask, broadcast-address;
}
EOF'
```

Then connect:
```bash
sudo connect-5g.sh
# Expected: SUCCESS: 5G connected
```

For Pixel: toggle airplane mode off.

### Phase 11: Verify Both RICs Have E2 Nodes

```bash
echo "=== RIC 1 ===" && docker exec ric_dbaas redis-cli KEYS '*RAN*'
echo "=== RIC 2 ===" && docker exec ric2_dbaas redis-cli KEYS '*RAN*'
# RIC 1 must show: gnbd_001_001_00019b_0
# RIC 2 must show: gnbd_001_001_00019b_1
```

### Phase 12: Start CQI Injector (dedicated terminal)

```bash
# Merged injector — reads 8001 (RF DU) + 8003 (ZMQ DU), serves 8002
# Passes physical UE CQI through unmodified
# Replaces virtual UE CQI with SNCF traces
# Remaps virtual RNTIs to 0xF001+ range to avoid collision
python3 ~/5g-virtual/cqi_injector.py --dataset_dir ~/5g-virtual/sncf_traces/
# Wait for: Connected to RF DU, Connected to ZMQ gNB, RNTI remappings
```

### Phase 13: Start xApp on RIC 1 — Physical UEs (dedicated terminal)

```bash
cd ~/oran-sc-ric
docker compose exec python_xapp_runner /opt/xApps/cqi_driven_xapp.py \
  --ue_ids 0,1,2 --ue_slices 3,1,2 --ws_url 10.0.2.1:8001
# Slice mapping: F1AP 0=CRITICAL, 1=PERFORMANCE, 2=BUSINESS
# NOTE: verify RNTI-to-slice mapping matches connection order via AMF log on Tower-2:
# sudo grep 'Registration complete' /var/log/open5gs/amf.log | grep '00101000000000[345]' | tail -3
```

### Phase 14: Start xApp on RIC 2 — Virtual UEs (dedicated terminal)

```bash
# Virtual-only CQI injector for RIC 2 xApp
python3 ~/5g-virtual/cqi_injector_virtual.py --dataset_dir ~/5g-virtual/sncf_traces/ &
# Wait for: [INJECTOR] Virtual CQI server on port 8004

docker exec -it python_xapp_runner_2 /opt/xApps/cqi_driven_xapp.py \
  --ue_ids 0,1,2 --ue_slices 3,1,2 --ws_url 10.0.4.1:8004 --e2_node_id gnbd_001_001_00019b_1
# Should show varying CQI from SNCF traces
```

### Phase 15: Start Logger and Traffic

```bash
# Logger (connects to merged port 8002 for all 6 UEs)
cd ~/oran-sc-ric
docker exec python_xapp_runner bash -c 'rm -f /tmp/ue_metrics_log.csv /tmp/prb_decisions.json'
# Start logger pointing to port 8002 (see metrics_logger_v2.py, change ws URL to 10.0.2.1:8002)

# Traffic server on Tower-2
python3 traffic_server.py &

# Traffic generators on robots
# Robot 1 (Critical): python3 critical_traffic.py --server 10.45.0.1 --duration 3600
# Robot 2 (Performance): python3 performance_traffic.py --server 10.45.0.1 --duration 3600
# Pixel: open YouTube/Twitch in browser
```

### Phase 16: Collect Dataset

```bash
cd ~/oran-sc-ric
docker exec python_xapp_runner bash -c 'pkill -f metrics_logger 2>/dev/null' || true
docker cp python_xapp_runner:/tmp/ue_metrics_log.csv ~/datasets/ue_SESSION_NAME.csv
wc -l ~/datasets/ue_SESSION_NAME.csv
head -2 ~/datasets/ue_SESSION_NAME.csv
```

## Terminal Layout (Tower-1)

| Terminal | Process |
|----------|---------|
| 1 | CU (srscu) |
| 2 | RF DU (srsdu du_x310.yml) |
| 3 | ZMQ DU (srsdu du_zmq.yml) |
| 4 | Virtual UEs (3x srsue background) |
| 5 | ZMQ Broker |
| 6 | CQI Injector (merged, port 8002) |
| 7 | CQI Injector virtual-only (port 8004) |
| 8 | xApp RIC 1 (physical) |
| 9 | xApp RIC 2 (virtual) |
| 10 | Logger |
| 11 | General commands |

## Key Implementation Notes

- **Slice assignment is server-side only.** COTS UEs send SD:0xffffff (wildcard). AMF resolves from MongoDB.
- **CQI is not available via E2SM-KPM.** Comes from DU websocket port 8001/8003.
- **F1AP-ID mapping resets on CU/DU restart.** Reconnect Robot 1 first after restart.
- **AMF SD format is critical.** MongoDB SD must be 6-char hex: 000001, 000002, 000003.
- **NAT rules lost on Tower-2 reboot.** Must reapply.
- **sector_id: 1 on ZMQ DU** resolves "Duplicate served cell CGI" CU rejection.
- **gnb_du_id: 1 on ZMQ DU** ensures different E2 node identity (gnbd_..._1 vs _0).
- **Two RIC instances required** because OSC RIC e2mgr deduplicates by ranName.
- **RIC 2 uses project name `ric2`** — always use `docker compose -p ric2` commands.
- **srsUE library path** — /etc/ld.so.conf.d/srsran.conf must contain /usr/local/lib, run ldconfig.
- **ZMQ startup order for split DU** — broker first, then UEs, then DU (opposite of monolithic gnb).

## Troubleshooting

**CU rejects ZMQ DU with "Duplicate served cell CGI":**
Ensure du_zmq.yml has `sector_id: 1` under cell_cfg.

**CU rejects ZMQ DU with "Duplicate DU ID":**
Ensure du_zmq.yml has `gnb_du_id: 1` as top-level parameter.

**RIC 2 not registering ZMQ DU:**
Check all config files in ~/oran-sc-ric-2/ric/configs/ use 10.0.4.x addresses, not 10.0.2.x.

**ZMQ DU segfaults on E2 connection:**
E2 bind_addr doesn't exist. Ensure 10.0.4.1 exists (Docker bridge for ric2 network creates it).

**ZMQ DU "Failed to bind UDP socket":**
F1-U address conflict. Change bind_addr in f1ap and f1u sections to unused 127.0.10.x address.

**Virtual UEs stuck at "Attaching":**
ZMQ broker not running, or DU not started yet. Start broker first, then DU.

**Virtual UEs stuck at "Waiting PHY to initialize":**
Normal before broker/DU start. They will proceed once ZMQ DU starts.

**Physical UE no IP after connect5g.sh:**
Check AMF log: sudo tail -50 /var/log/open5gs/amf.log on Tower-2.

**No traffic despite UE has IP:**
NAT FORWARD rules missing on Tower-2. Reapply.

**xApp shows constant CQI=15 for virtual UEs:**
xApp connecting to raw DU port (8003) instead of injector port (8004 or 8002).

**Logger writes only 1 row:**
websocket-client not installed in container. Run pip3 install websocket-client.

**"Address already in use" when starting xApp:**
Old xApp process still running. Kill with: docker exec CONTAINER bash -c 'pkill -9 -f python'

**RIC 2 containers conflict with RIC 1:**
Container names must be different. docker-compose.yml should have ric2_ prefix on container_name fields.

**RIC 2 network creation fails "Pool overlaps":**
Subnet 10.0.4.0/24 must be set in both .env AND at bottom of docker-compose.yml.

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
  }
])'
```

## Clean Shutdown

```bash
# Tower-1: Kill in reverse order
# Ctrl+C: xApps, injectors, traffic generators
sudo pkill -9 -f srsue
sudo pkill -f zmq_broker
sudo pkill -9 -f srsdu
sudo pkill -9 -f srscu
cd ~/oran-sc-ric && docker compose down
cd ~/oran-sc-ric-2 && docker compose -p ric2 down
sudo ip netns del vue1 2>/dev/null
sudo ip netns del vue2 2>/dev/null
sudo ip netns del vue3 2>/dev/null

# Tower-2:
sudo systemctl stop open5gs-amfd open5gs-smfd open5gs-upfd open5gs-nrfd \
  open5gs-scpd open5gs-ausfd open5gs-udmd open5gs-udrd open5gs-pcfd open5gs-bsfd
```

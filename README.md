# 5G SA Private Network — Physical UE Testbed
# Scenario A Replication Guide

## Architecture Overview

Two Dell Precision 5820 workstations running a 5G SA private network with one CU connecting one RF DU serving three physical UEs via USRP X310. A single OSC Near-RT RIC instance hosts a CQI-driven xApp performing SLA-driven PRB allocation across all UEs.

## Measurement Scenario

| Scenario | Physical UEs | Virtual UEs | Total UEs | Bandwidth | Traffic |
|----------|-------------|-------------|-----------|-----------|---------|
| A — Low Density | 3 robots | 0 | 3 | 5 MHz | Nominal UIC spec |

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
| Bandwidth | 5 MHz |
| SCS | 15 kHz |
| PRBs | 25 |
| TAC | 7 |
| DNN/APN | srsapn |
| UE IP Pool | 10.45.0.0/16 |

## Network Slices

| Slice | SD | Priority | Physical UE | IMSI |
|-------|----|----------|-------------|------|
| CRITICAL | 000003 | 1 | Robot 1 | 001010000000005 |
| PERFORMANCE | 000001 | 2 | Robot 2 | 001010000000004 |
| BUSINESS | 000002 | 3 | Pixel | 001010000000003 |

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
| 5G Core | Open5GS | 2.7.6 |
| Near-RT RIC | O-RAN SC RIC | i-release (Docker Compose) |
| Database | MongoDB | 8.0 |

## File Locations

### Tower-1

| File | Path |
|------|------|
| CU config | ~/srsRAN_Project_clean/configs/ligm/cu.yml |
| RF DU config | ~/srsRAN_Project_clean/configs/ligm/du_x310.yml |
| CU binary | ~/srsRAN_Project_clean/build/apps/cu/srscu |
| DU binary | ~/srsRAN_Project_clean/build/apps/du/srsdu |
| xApp | ~/oran-sc-ric/xApps/python/cqi_driven_xapp_three_phy.py |
| Logger | ~/oran-sc-ric/xApps/python/metrics_logger_v2.py |
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
```

### Phase 3: Tower-1 — Start RIC

```bash
cd ~/oran-sc-ric
docker compose up -d
sleep 20
docker logs ric_submgr 2>&1 | tail -3
# Must show: RMR is ready now ...
```

### Phase 4: Tower-1 — Deploy xApp to RIC container

```bash
cd ~/oran-sc-ric
docker compose exec python_xapp_runner pip3 install websocket-client
docker cp ~/oran-sc-ric/xApps/python/cqi_driven_xapp_three_phy.py python_xapp_runner:/opt/xApps/
docker cp ~/oran-sc-ric/xApps/python/metrics_logger_v2.py python_xapp_runner:/opt/xApps/
docker exec python_xapp_runner chmod +x \
  /opt/xApps/cqi_driven_xapp_three_phy.py \
  /opt/xApps/metrics_logger_v2.py
```

### Phase 5: Tower-1 — Start CU

```bash
cd ~/srsRAN_Project_clean/build/apps/cu
sudo ./srscu -c ~/srsRAN_Project_clean/configs/ligm/cu.yml
# Wait for: N2: Connection to AMF on 192.168.0.3:38412 completed
```

### Phase 6: Tower-1 — Start RF DU

```bash
cd ~/srsRAN_Project_clean/build/apps/du
sudo ./srsdu -c ~/srsRAN_Project_clean/configs/ligm/du_x310.yml
# Wait for: E2AP: Connection to Near-RT-RIC on 10.0.2.10:36421 completed
# Wait for: Remote control server listening on 0.0.0.0:8001
```

### Phase 7: Connect Physical UEs

Robot 1 first (CRITICAL), Robot 2 second (PERFORMANCE), Pixel last (BUSINESS). On each robot:

```bash
sudo connect-5g.sh
# Expected: SUCCESS: 5G connected
```

For Pixel: toggle airplane mode off.

### Phase 8: Start Robot Traffic (on each robot via SSH)

```bash
# Robot 1 (CRITICAL)
python3 ~/critical_traffic.py --server 10.45.0.1 --duration 999999

# Robot 2 (PERFORMANCE)
python3 ~/performance_traffic.py --server 10.45.0.1 --duration 999999

# Pixel: open YouTube or any streaming app
```

### Phase 9: Start Traffic Server on Tower-2

```bash
python3 ~/traffic_server.py
```

### Phase 10: Start xApp

```bash
cd ~/oran-sc-ric
docker compose exec python_xapp_runner python3 /opt/xApps/cqi_driven_xapp_three_phy.py
```

### Phase 11: Start Logger and Collect Dataset

```bash
cd ~/oran-sc-ric
docker exec python_xapp_runner bash -c 'rm -f /tmp/ue_metrics_log.csv /tmp/prb_decisions.json'
docker compose exec python_xapp_runner python3 /opt/xApps/metrics_logger_v2.py
```

Monitor in real time:

```bash
docker exec python_xapp_runner bash -c 'tail -f /tmp/ue_metrics_log.csv'
```

Collect when done:

```bash
docker cp python_xapp_runner:/tmp/ue_metrics_log.csv \
  ~/datasets/scen_A_$(date +%Y%m%d_%H%M).csv
```

## Terminal Layout (Tower-1)

| Terminal | Process |
|----------|---------|
| 1 | CU (srscu) |
| 2 | RF DU (du_x310.yml) |
| 3 | xApp |
| 4 | Logger |
| 5 | General commands |

## Key Implementation Notes

- **F1AP-ID to slice mapping resets on CU/DU restart.** Always reconnect Robot 1 (CRITICAL) first, Robot 2 (PERFORMANCE) second, Pixel (BUSINESS) third.
- **Pixel CQI is always 5.** Known characteristic of the Quectel/Pixel modem combination in this RF environment. Use as ground truth anchor for RNTI identification in post-processing.
- **Slice assignment is server-side only.** COTS UEs send SD:0xffffff (wildcard). AMF resolves from MongoDB.
- **CQI is not available via E2SM-KPM.** It comes from the DU websocket port 8001 (RF DU).
- **NAT rules lost on Tower-2 reboot.** Must reapply Phase 1.
- **srsUE library path.** /etc/ld.so.conf.d/srsran.conf must contain /usr/local/lib, run ldconfig after any srsRAN 4G install.



## Troubleshooting

**Physical UE no IP after connect5g.sh:** Check AMF log on Tower-2:
```bash
sudo tail -50 /var/log/open5gs/amf.log
```

**No traffic despite UE has IP:** NAT FORWARD rules missing on Tower-2. Reapply Phase 1.

**xApp shows no UEs:** websocket-client not installed in container:
```bash
docker compose exec python_xapp_runner pip3 install websocket-client
```

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
  }
])'
```

## Clean Shutdown

```bash
# Tower-1
sudo pkill -9 -f srsdu
sudo pkill -9 -f srscu
cd ~/oran-sc-ric && docker compose down

# Tower-2
sudo systemctl stop open5gs-amfd open5gs-smfd open5gs-upfd open5gs-nrfd \
  open5gs-scpd open5gs-ausfd open5gs-udmd open5gs-udrd open5gs-pcfd open5gs-bsfd
```
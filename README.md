# RF-Nano Sensor Network

A small wireless sensor network built around RF-Nano boards (Arduino Nano + on-board
nRF24L01+ 2.4 GHz radio). Remote nodes read sensors and transmit short packets by
radio to a gateway RF-Nano, which is plugged into a Raspberry Pi over USB and reprints
each packet to the serial port for the Pi to log or act on.

```
[ sensor node ] --radio--> [ gateway RF-Nano ] --USB serial--> [ Raspberry Pi ]
```

## Current boards

| Board | Role | Key details | Status |
|-------|------|-------------|--------|
| RF-Nano (V1/V2, micro-USB) | **Node 3 — door sensor** | ATmega328P @ 16 MHz, on-board nRF24L01+. Reads a Gebildet NC reed switch on D2. | Working |
| RF-Nano (V1/V2, micro-USB) | **Gateway** | Same board, plugged into the Pi over USB. Listens for all node packets and forwards them as serial text. | Working |
| Gebildet reed switch (NC) | Door sensor for Node 3 | Passive magnetic switch, 2 wires (no polarity). Wired D2 ↔ GND, uses internal pull-up. | Working |
| Raspberry Pi B+ | Serial host (candidate) | 40-pin header, USB host. Reads the gateway over `/dev/ttyUSB0`. | Available |
| Raspberry Pi 2 | Serial host (candidate) | 40-pin header, USB host. Either Pi can act as the host. | Available |

### Planned nodes (on the network diagram, not yet built)

- **Node 1 — temperature**
- **Node 2 — soil moisture**

## RF-Nano radio pins — read this first

The nRF24L01+ is on-board (no wiring), but **the CE/CSN pins differ by board version**.
This bites everyone; the wrong pair makes `radio.begin()`/`write()` silently fail or hang.

| Board version | USB | CE | CSN | RF24 constructor |
|---------------|-----|----|-----|------------------|
| V1.0 / V2.0 | Micro-USB | **10** | **9** | `RF24 radio(10, 9)` |
| V3.0 | USB-C | 7 | 8 | `RF24 radio(7, 8)` |

Our boards are the micro-USB V1/V2 variant → **CE=10, CSN=9**. SPI pins (D11/D12/D13)
are fixed and cannot be reused. Both sketches print a `chipConnected=yes/no` line at
startup so a wrong pin pair is obvious instead of hanging.

## Network configuration (must match on every board)

| Setting | Value |
|---------|-------|
| Channel | 76 |
| Data rate | 1 Mbps |
| Gateway address | `GWAY1` (5 bytes) |
| Power level | `RF24_PA_LOW` |
| Max payload | 32 bytes per packet |

### Shared packet format

```cpp
struct Packet {
  uint8_t nodeId;    // which node sent it
  uint8_t msgType;   // how to interpret the payload (1 = door)
  float   value1;    // door: 0.0 = closed, 1.0 = open
  float   value2;    // unused for door
};
```

Every message carries a `nodeId` and a `msgType` so the Pi can tell who sent what and
how to read it once everything funnels into one serial stream.

### What the Pi reads

The gateway prints one line per packet at **115200 baud**, e.g.:

```
node=3,type=1,door=OPEN
```

Unrecognized message types fall back to raw values (`node=9,type=4,v1=21.50,v2=48.00`)
so nothing is ever lost.

The gateway also emits a **liveness ping every 5 seconds** so the Pi knows the serial
link is alive even during radio silence:

```
node=0,type=99,uptime=42,radio=ok
```

The Pi reader treats the ping as a link-alive signal (not a sensor reading, so it is
not logged to CSV) and prints a warning if no ping arrives for ~12 seconds.

## Files

| File | Description |
|------|-------------|
| `door_node/door_node.ino` | Node 3 firmware — reads the reed switch, transmits on change + 5-min heartbeat. `DEBUG_TICK` prints state once/sec for bench testing. |
| `gateway_node/gateway_node.ino` | Gateway firmware — receives radio packets, forwards them to the Pi over serial, pings every 5s. |
| `pi_reader/read_gateway.py` | Pi console reader — prints readings, logs to CSV, warns if the gateway link goes quiet. |
| `pi_reader/mqtt_bridge.py` | Home Assistant MQTT bridge — publishes state + auto-discovery so the door appears in HA. |
| `gateway_wiring.svg` | Pictorial wiring / data-path diagram (node → radio → gateway → USB → Pi). |

A matching diagram also lives on the FigJam board **RF-Nano sensor network**.

## Home Assistant (MQTT auto-discovery)

`pi_reader/mqtt_bridge.py` publishes to an MQTT broker using HA's MQTT Discovery,
so the door shows up automatically as a `binary_sensor` with the `door` device
class — no YAML editing in Home Assistant. It requires the HA MQTT integration and
a broker (e.g. the Mosquitto add-on).

```bash
pip3 install pyserial paho-mqtt
python3 pi_reader/mqtt_bridge.py --mqtt-host 192.168.1.10 \
    --mqtt-user USER --mqtt-pass PASS
```

Topics:

| Topic | Purpose |
|-------|---------|
| `door/state` | `OPEN` / `CLOSED` (retained) |
| `bridge/status` | bridge alive — MQTT Last Will (this script / Pi / broker) |
| `gateway/status` | gateway alive — driven by the 5s ping watchdog |
| `bridge/log` | raw serial lines, for live viewing (last line retained) |
| `homeassistant/binary_sensor/door/config` | discovery config (retained) |

Availability is layered with `availability_mode: all` — HA shows the door as
**unavailable** if *either* the bridge dies (Last Will) *or* the gateway link goes
quiet (no ping for ~12s). Otherwise it reports open/closed in real time.

Use `read_gateway.py` for plain console/CSV logging, or `mqtt_bridge.py` for HA —
run whichever you need (or both, on different `--csv`/broker targets).

Watch the raw gateway output over MQTT from any machine:

```bash
mosquitto_sub -h <broker-ip> -t 'bridge/log' -v
```

### Run the bridge as a service

`pi_reader/service/install_service.sh` installs `mqtt_bridge.py` as a systemd
service that starts on boot and restarts on crash:

```bash
cd pi_reader/service
sudo bash install_service.sh
sudo nano /etc/rfnano-bridge.env     # enter your broker details
sudo systemctl start rfnano-bridge
journalctl -u rfnano-bridge -f       # watch service logs
```

Broker settings live in `/etc/rfnano-bridge.env` (root-only, mode 600), so no
credentials are stored in the unit file or the repo.

## Flashing & testing

1. Arduino IDE → Library Manager → install TMRh20 **RF24**.
2. Tools → Board → **Arduino Nano**. If uploads fail, Tools → Processor →
   **ATmega328P (Old Bootloader)**.
3. Install the **CH340** USB driver if no serial port appears.
4. Upload `door_node` to one board and `gateway_node` to the board on the Pi.
5. Open Serial Monitor at **115200**. Once both are running, the node's `(no ack)`
   lines flip to `(acked)` — that's the two boards confirming the link.

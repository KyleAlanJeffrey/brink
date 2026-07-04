#!/usr/bin/env python3
"""
Home Assistant MQTT bridge for the RF-Nano gateway.

Reads the gateway RF-Nano over USB serial and publishes to an MQTT broker so
Home Assistant discovers the sensors automatically (MQTT Discovery). No YAML
editing in HA is required -- the door shows up as a binary_sensor with the
"door" device class.

Availability is layered so the entity goes "unavailable" if either link breaks:
  * bridge status  -> MQTT Last Will (this script / the Pi died or lost the broker)
  * gateway status -> driven by the 5s gateway ping watchdog (radio board / USB down)
HA marks the door available only when BOTH are online (availability_mode: all).

Every raw serial line is also republished to bridge/log (last line retained)
so you can watch the gateway output live in any MQTT client.

Setup on the Pi:
    pip3 install pyserial paho-mqtt
    python3 mqtt_bridge.py --mqtt-host 192.168.1.10 \
        --mqtt-user USER --mqtt-pass PASS
    # serial port auto-detects; override with --port /dev/ttyUSB0

Requires read_gateway.py in the same folder (shared line parser).
"""

import argparse
import json
import os
import sys
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("paho-mqtt not installed. Run: pip3 install paho-mqtt")

# Reuse the tested serial parser + constants from the reader.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from read_gateway import parse_line, open_serial, PING_TYPE, LINK_TIMEOUT  # noqa: E402

import serial  # noqa: E402  (pyserial; read_gateway already validated it)

# ---------- topic layout ----------
BRIDGE_STATUS = "bridge/status"      # MQTT LWT: online/offline
GATEWAY_STATUS = "gateway/status"    # driven by ping watchdog
DOOR_STATE = "door/state"            # OPEN / CLOSED
LOG_TOPIC = "bridge/log"             # raw serial lines, for viewing

DEVICE = {
    "identifiers": ["rfnano_network"],
    "name": "RF-Nano Sensor Network",
    "manufacturer": "DIY",
    "model": "RF-Nano gateway + nRF24L01",
}


def discovery_configs(prefix):
    """Return [(config_topic, payload_dict), ...] for every entity."""
    door = {
        "name": "Door",
        "unique_id": "door",
        "state_topic": DOOR_STATE,
        "payload_on": "OPEN",
        "payload_off": "CLOSED",
        "device_class": "door",
        "availability": [
            {"topic": BRIDGE_STATUS},
            {"topic": GATEWAY_STATUS},
        ],
        "availability_mode": "all",
        "device": DEVICE,
    }
    return [
        (f"{prefix}/binary_sensor/door/config", door),
    ]


def make_client(args):
    """Create a paho client that works on both paho-mqtt 1.x and 2.x."""
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id="rfnano-bridge")
    except (AttributeError, TypeError):
        client = mqtt.Client(client_id="rfnano-bridge")  # paho 1.x

    if args.mqtt_user:
        client.username_pw_set(args.mqtt_user, args.mqtt_pass)

    # Last Will: if the bridge drops off the broker, mark it offline (retained).
    client.will_set(BRIDGE_STATUS, "offline", qos=1, retain=True)

    def on_connect(cl, userdata, *rest):  # *rest absorbs 1.x/2.x signature diff
        print("[mqtt] connected")
        cl.publish(BRIDGE_STATUS, "online", qos=1, retain=True)
        for topic, payload in discovery_configs(args.discovery_prefix):
            cl.publish(topic, json.dumps(payload), qos=1, retain=True)
        print("[mqtt] discovery published")

    client.on_connect = on_connect
    return client


def main():
    # Defaults fall back to environment variables so the systemd service can be
    # configured via /etc/rfnano-bridge.env without secrets in the unit file.
    ap = argparse.ArgumentParser(description="RF-Nano -> Home Assistant MQTT bridge.")
    ap.add_argument("--mqtt-host", default=os.environ.get("MQTT_HOST", "localhost"))
    ap.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    ap.add_argument("--mqtt-user", default=os.environ.get("MQTT_USER"))
    ap.add_argument("--mqtt-pass", default=os.environ.get("MQTT_PASS"))
    ap.add_argument("--discovery-prefix", default=os.environ.get("DISCOVERY_PREFIX", "homeassistant"))
    ap.add_argument("--port", default=os.environ.get("SERIAL_PORT"),
                    help="serial port (default: $SERIAL_PORT or auto-detect)")
    ap.add_argument("--baud", type=int, default=int(os.environ.get("BAUD", "115200")))
    args = ap.parse_args()

    client = make_client(args)
    client.connect(args.mqtt_host, args.mqtt_port, keepalive=30)
    client.loop_start()  # background network thread handles reconnects

    ser = open_serial(args.port, args.baud)
    last_ping = time.monotonic()
    gateway_online = None  # unknown until first ping/timeout, forces first publish

    def set_gateway(online):
        nonlocal gateway_online
        if gateway_online != online:
            gateway_online = online
            client.publish(GATEWAY_STATUS, "online" if online else "offline",
                           qos=1, retain=True)
            print(f"[gateway] {'online' if online else 'offline'}")

    try:
        while True:
            try:
                raw = ser.readline().decode("utf-8", errors="replace")
            except serial.SerialException:
                print("[serial] disconnected, reopening...")
                set_gateway(False)
                try:
                    ser.close()
                except Exception:
                    pass
                ser = open_serial(args.port, args.baud)
                last_ping = time.monotonic()
                continue

            # Republish the raw serial line so it can be watched over MQTT
            # (subscribe to rfnano/bridge/log). Retain the last line so a new
            # subscriber immediately sees the most recent output.
            line = raw.strip()
            if line:
                client.publish(LOG_TOPIC, line, qos=0, retain=True)

            now = time.monotonic()
            if now - last_ping > LINK_TIMEOUT:
                set_gateway(False)

            reading = parse_line(raw)
            if reading is None:
                continue

            if reading.get("type") == PING_TYPE:
                last_ping = now
                set_gateway(True)
                continue

            # Door state -> retained so HA restores it after a restart.
            if reading.get("node") == 3 and "door" in reading:
                client.publish(DOOR_STATE, reading["door"], qos=1, retain=True)
                print(f"[door] {reading['door']}")
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        client.publish(BRIDGE_STATUS, "offline", qos=1, retain=True)
        client.loop_stop()
        client.disconnect()
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

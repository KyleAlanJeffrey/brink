"""Shared serial helpers for the RF-Nano gateway.

Parsing and port handling used by both the MQTT bridge and the console reader.

Gateway line formats (see gateway_node.ino):
    node=3,type=1,door=OPEN                 # known type (door)
    node=9,type=4,v1=21.50,v2=48.00         # unknown type -> raw values
    node=0,type=99,uptime=42,radio=ok       # gateway liveness ping (every 5s)
    # comment / status lines start with '#'
"""

import glob
import os
import sys
import time

try:
    import serial  # pyserial
except ImportError:
    sys.exit("pyserial not installed. Install it (see requirements.txt): pip install pyserial")

# Gateway ping (see gateway_node.ino): node 0, type 99, every ~5s.
PING_TYPE = 99
# Warn/mark-offline if no ping for this long (a couple missed pings = a problem).
LINK_TIMEOUT = 12.0


def parse_line(line):
    """Parse one gateway line into a dict, or return None to skip it.

    Comment/status lines (starting with '#') and blank lines return None.
    A valid reading always has at least 'node' and 'type'.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    fields = {}
    for pair in line.split(","):
        if "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        fields[key.strip()] = value.strip()

    if "node" not in fields or "type" not in fields:
        return None  # not a reading we recognize

    for key in ("node", "type", "uptime"):
        if key in fields:
            try:
                fields[key] = int(fields[key])
            except ValueError:
                pass
    for key in ("v1", "v2"):
        if key in fields:
            try:
                fields[key] = float(fields[key])
            except ValueError:
                pass

    return fields


def find_port():
    """Return the first likely gateway serial port, or None."""
    candidates = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    return candidates[0] if candidates else None


def open_serial(port, baud):
    """Block until the serial port is available, then return an open handle."""
    while True:
        target = port or find_port()
        if target and os.path.exists(target):
            try:
                ser = serial.Serial(target, baud, timeout=1)
                print(f"[connected] {target} @ {baud}")
                return ser
            except serial.SerialException as exc:
                print(f"[waiting] {target}: {exc}")
        else:
            print("[waiting] no gateway serial port found "
                  "(/dev/ttyUSB* or /dev/ttyACM*)")
        time.sleep(2)

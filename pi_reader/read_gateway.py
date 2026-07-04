#!/usr/bin/env python3
"""
Raspberry Pi reader for the RF-Nano gateway.

Reads the gateway RF-Nano over USB serial and parses each packet line into a
dict. By default it prints every reading to the console and appends it to a
CSV log. If the gateway is unplugged it waits and reconnects automatically.

Gateway line formats (see gateway_node.ino):
    node=3,type=1,door=OPEN                 # known type (door)
    node=9,type=4,v1=21.50,v2=48.00         # unknown type -> raw values
    # comment / status lines start with '#' and are ignored for logging

Setup on the Pi:
    sudo apt install python3-serial        # or: pip3 install pyserial
    python3 read_gateway.py                 # auto-detects the port

Usage:
    python3 read_gateway.py [--port /dev/ttyUSB0] [--baud 115200]
                            [--csv readings.csv] [--quiet]
"""

import argparse
import csv
import glob
import os
import sys
import time
from datetime import datetime, timezone

try:
    import serial  # pyserial
except ImportError:
    sys.exit("pyserial not installed. Run: pip3 install pyserial")


# ---------- parsing ----------

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

    # Coerce known numeric fields where present.
    for key in ("node", "type"):
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


# ---------- port handling ----------

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


# ---------- logging ----------

def log_csv(path, reading):
    """Append one reading to a CSV, writing a header row if the file is new."""
    columns = ["timestamp", "node", "type", "door", "v1", "v2"]
    new_file = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow(reading)


def describe(reading):
    """Human-readable one-liner for the console."""
    node = reading.get("node")
    if "door" in reading:
        return f"node {node}: door {reading['door']}"
    extras = " ".join(f"{k}={reading[k]}" for k in ("v1", "v2") if k in reading)
    return f"node {node}: type {reading.get('type')} {extras}".rstrip()


# ---------- main loop ----------

def main():
    ap = argparse.ArgumentParser(description="Read the RF-Nano gateway over serial.")
    ap.add_argument("--port", help="serial port (default: auto-detect)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--csv", default="readings.csv", help="CSV log path")
    ap.add_argument("--quiet", action="store_true", help="don't print each reading")
    args = ap.parse_args()

    print("Reading gateway. Ctrl-C to stop.")
    ser = open_serial(args.port, args.baud)

    try:
        while True:
            try:
                raw = ser.readline().decode("utf-8", errors="replace")
            except serial.SerialException:
                print("[disconnected] reopening...")
                try:
                    ser.close()
                except Exception:
                    pass
                ser = open_serial(args.port, args.baud)
                continue

            reading = parse_line(raw)
            if reading is None:
                stripped = raw.strip()
                if stripped.startswith("#") and not args.quiet:
                    print(f"[gateway] {stripped}")
                continue

            reading["timestamp"] = datetime.now(timezone.utc).isoformat()
            log_csv(args.csv, reading)
            if not args.quiet:
                print(f"{reading['timestamp']}  {describe(reading)}")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

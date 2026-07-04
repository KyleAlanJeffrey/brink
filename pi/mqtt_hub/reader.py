"""Console/CSV reader for the RF-Nano gateway (no MQTT).

Prints every reading and appends it to a CSV. Treats the gateway ping as a
link-alive signal and warns if it goes quiet.

Run with:   python -m mqtt_hub.reader [--port /dev/ttyUSB0] [--csv readings.csv] [--quiet]
"""

import argparse
import csv
import os
import time
from datetime import datetime, timezone

import serial  # pyserial (validated in serial_io)

from .serial_io import parse_line, open_serial, PING_TYPE, LINK_TIMEOUT


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


def main():
    ap = argparse.ArgumentParser(description="Read the RF-Nano gateway over serial.")
    ap.add_argument("--port", help="serial port (default: auto-detect)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--csv", default="readings.csv", help="CSV log path")
    ap.add_argument("--quiet", action="store_true", help="don't print each reading")
    args = ap.parse_args()

    print("Reading gateway. Ctrl-C to stop.")
    ser = open_serial(args.port, args.baud)

    last_ping = time.monotonic()
    link_down = False

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
                last_ping = time.monotonic()
                link_down = False
                continue

            reading = parse_line(raw)

            now = time.monotonic()
            if now - last_ping > LINK_TIMEOUT and not link_down:
                link_down = True
                print(f"[warning] no gateway ping for {LINK_TIMEOUT:.0f}s "
                      "-- serial link may be down")

            if reading is None:
                stripped = raw.strip()
                if stripped.startswith("#") and not args.quiet:
                    print(f"[gateway] {stripped}")
                continue

            if reading.get("type") == PING_TYPE:
                last_ping = now
                if link_down:
                    link_down = False
                    print("[recovered] gateway ping resumed")
                if not args.quiet:
                    radio = reading.get("radio", "?")
                    up = reading.get("uptime", "?")
                    print(f"[alive] gateway up={up}s radio={radio}")
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

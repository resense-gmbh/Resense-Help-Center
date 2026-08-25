# ============================================================
# RESENSE Force/Torque Sensor -- Python Sample Script
# Mode: LEGACY (raw binary packets, 28 bytes per measurement)
# ============================================================
#
# The sensor continuously transmits 28-byte packets at 1 Mbit/s.
# Each packet contains 7 little-endian IEEE 754 float32 values:
#   fX, fY, fZ   -- Force components
#   mX, mY, mZ   -- Torque components
#   temperature  -- Sensor temperature in degrees C
#
# NOTE: In legacy mode there is NO framing and NO checksum.
#       If the connection starts mid-packet, data will be misaligned.
#       Re-connecting the port resets the alignment.
#
# Requirements:
#   pip install pyserial
#
# Usage:
#   1. Set PORT to the COM port shown in Force/Torque Explorer
#      (e.g. 'COM3' on Windows, '/dev/ttyACM0' on Linux/macOS)
#   2. Run:  python python_legacy.py
# ============================================================

import serial
import struct

PORT = 'COM3'     # Windows: 'COM3', Linux/macOS: '/dev/ttyACM0'
BAUD = 1_000_000  # Fixed at 1 Mbit/s -- do not change

PACKET_SIZE = 28  # 7 x float32


def read_sensor(port: str, baud: int) -> None:
    ser = serial.Serial(port, baud, timeout=2)
    print(f"Connected to {port} in legacy mode. Press Ctrl+C to stop.\n")
    print(f"{'Fx':>10}  {'Fy':>10}  {'Fz':>10}  "
          f"{'Mx':>10}  {'My':>10}  {'Mz':>10}  {'Temp':>8}")
    print("-" * 80)

    try:
        while True:
            raw = ser.read(PACKET_SIZE)
            if len(raw) < PACKET_SIZE:
                # Timeout -- retry without crashing
                continue

            fX, fY, fZ, mX, mY, mZ, temp = struct.unpack('<fffffff', raw)

            print(f"{fX:10.3f}  {fY:10.3f}  {fZ:10.3f}  "
                  f"{mX:10.3f}  {mY:10.3f}  {mZ:10.3f}  {temp:8.2f} C")

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        ser.close()


if __name__ == '__main__':
    read_sensor(PORT, BAUD)

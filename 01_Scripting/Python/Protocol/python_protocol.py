# ============================================================
# RESENSE Force/Torque Sensor -- Python Sample Script
# Mode: PROTOCOL (framed binary with CRC16-CCITT validation)
# ============================================================
#
# Frame format (all multi-byte values are little-endian):
#
#   Byte  Length  Description
#   ----  ------  -------------------------------------------
#   0     1       Start byte (0x7E)
#   1     1       Version (upper 4 bits) | Flags (lower 4 bits)
#   2     1       Message type (0=Measurement, 1=Config, 2=Diagnostic)
#   3     1       Payload count (number of float32 values)
#   4     1       Rolling frame counter (0-255, wraps around)
#   5..N  count*4 Payload: little-endian float32 values
#   N+1   2       CRC16-CCITT checksum (poly 0x1021, init 0xFFFF)
#
# Message type 0 -- Measurement (7 floats):
#   fX, fY, fZ, mX, mY, mZ, temperature
#
# Message type 2 -- Diagnostic (11 floats):
#   fX, fY, fZ, mX, mY, mZ, temperature,
#   current, raw_adc_voltage, board_temperature, board_voltage
#
#   Sensor voltage (V) = (raw_adc_voltage / board_voltage) * 3.3
#   (only use this formula when board_voltage > 0)
#
# Requirements:
#   pip install pyserial
#
# Usage:
#   1. Set PORT to the COM port shown in Force/Torque Explorer
#   2. Run:  python python_protocol.py
# ============================================================

import serial
import struct

PORT = 'COM3'     # Windows: 'COM3', Linux/macOS: '/dev/ttyACM0'
BAUD = 1_000_000  # Fixed at 1 Mbit/s -- do not change

START_BYTE      = 0x7E
PROTOCOL_VER    = 1
MSG_MEASUREMENT = 0x00
MSG_CONFIG      = 0x01
MSG_DIAGNOSTIC  = 0x02


def crc16_ccitt(data: bytes) -> int:
    """CRC16-CCITT: polynomial 0x1021, initial value 0xFFFF."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def read_frame(ser: serial.Serial):
    """
    Block until a complete, CRC-validated frame is received.

    Returns:
        (msg_type: int, values: list[float])  on success
        None                                  on CRC error (stream stays synced)
    """
    # Synchronise: scan byte-by-byte until the start byte is found
    while True:
        b = ser.read(1)
        if not b:
            continue
        if b[0] == START_BYTE:
            break

    # Read the 4-byte header
    header = ser.read(4)
    if len(header) < 4:
        return None

    version  = (header[0] >> 4) & 0x0F
    msg_type = header[1]
    count    = header[2]
    # header[3] is the rolling counter -- compare consecutive values to
    # detect dropped frames: (current_counter - previous_counter) & 0xFF == 1

    # Read payload (count float32 values)
    payload = ser.read(count * 4)
    if len(payload) < count * 4:
        return None

    # Read and validate CRC16
    crc_raw = ser.read(2)
    if len(crc_raw) < 2:
        return None

    received_crc   = struct.unpack_from('<H', crc_raw)[0]
    calculated_crc = crc16_ccitt(header + payload)

    if received_crc != calculated_crc:
        print(f"  [CRC error: received=0x{received_crc:04X}  "
              f"expected=0x{calculated_crc:04X}]")
        return None

    values = list(struct.unpack_from(f'<{count}f', payload))
    return msg_type, values


def read_sensor(port: str, baud: int) -> None:
    ser = serial.Serial(port, baud, timeout=2)
    print(f"Connected to {port} in protocol mode. Press Ctrl+C to stop.\n")

    prev_counter = None

    try:
        while True:
            result = read_frame(ser)
            if result is None:
                continue

            msg_type, values = result

            if msg_type == MSG_MEASUREMENT and len(values) >= 7:
                fX, fY, fZ, mX, mY, mZ, temp = values[:7]
                print(f"[MEAS]  "
                      f"Fx={fX:10.3f}  Fy={fY:10.3f}  Fz={fZ:10.3f}  "
                      f"Mx={mX:10.3f}  My={mY:10.3f}  Mz={mZ:10.3f}  "
                      f"Temp={temp:.2f} C")

            elif msg_type == MSG_DIAGNOSTIC and len(values) >= 11:
                fX, fY, fZ, mX, mY, mZ, temp, \
                    current, raw_v, board_temp, board_v = values[:11]
                sensor_v = (raw_v / board_v * 3.3) if board_v > 0 else 0.0
                print(f"[DIAG]  "
                      f"Fx={fX:10.3f}  Fy={fY:10.3f}  Fz={fZ:10.3f}  "
                      f"Mx={mX:10.3f}  My={mY:10.3f}  Mz={mZ:10.3f}  "
                      f"Temp={temp:.2f} C  "
                      f"I={current:.3f} A  V={sensor_v:.3f} V  "
                      f"BoardTemp={board_temp:.2f} C  BoardV={board_v:.3f} V")

            elif msg_type == MSG_CONFIG:
                # Configuration frames carry text payload -- decode as UTF-8
                pass  # Extend here if you need to process config responses

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        ser.close()


if __name__ == '__main__':
    read_sensor(PORT, BAUD)

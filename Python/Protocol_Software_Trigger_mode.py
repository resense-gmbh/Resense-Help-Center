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
# Message type 0 -- Measurement (9 floats):
#   CH2, CH1, CH3, CH4, CH5, CH6, T1
#
# Message type 2 -- Diagnostic (13 floats):
#   CH2, CH1, CH3, CH4, CH5, CH6, T1
#   I, V, BoardTemp, BoardVoltage
#
#   Sensor voltage (V) = (V / BoardVoltage) * 3.3
#   (only use this formula when BoardVoltage > 0)
#
# Requirements:
#   pip install pyserial matplotlib
#
# Usage:
#   1. Set PORT to the COM port shown in Force/Torque Explorer
#   2. Run: python Protocol_Software_ Trigger_mode.py
# ============================================================

import csv
import struct
import time
from pathlib import Path

import serial

PORT = 'COM24'     # Windows: 'COM3', Linux/macOS: '/dev/ttyACM0'
BAUD = 3_000_000  # Fixed at 3 Mbit/s -- do not change
SERIAL_TIMEOUT = 0.2
RECORD_SECONDS = 5.0  # Set to None to run until Ctrl+C

START_BYTE = 0x7E
MSG_MEASUREMENT = 0x00
MSG_CONFIG = 0x01
MSG_DIAGNOSTIC = 0x02

CSV_HEADERS = [
    'elapsed_s', 'msg_type',
    'CH2', 'CH1', 'CH3', 'CH4', 'CH5', 'CH6',
    'T1',
    'Current', 'RawV', 'BoardTemp', 'BoardV', 'SensorV',
]


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
        (msg_type: int, values: list[float]) on success
        None on CRC or incomplete frame error
    """
    while True:
        start = ser.read(1)
        if not start:
            return None
        if start[0] == START_BYTE:
            break

    header = ser.read(4)
    if len(header) < 4:
        return None

    msg_type = header[1]
    count = header[2]

    payload = ser.read(count * 4)
    if len(payload) < count * 4:
        return None

    crc_raw = ser.read(2)
    if len(crc_raw) < 2:
        return None

    received_crc = struct.unpack_from('<H', crc_raw)[0]
    calculated_crc = crc16_ccitt(header + payload)

    if received_crc != calculated_crc:
        print(
            f"  [CRC error: received=0x{received_crc:04X} "
            f"expected=0x{calculated_crc:04X}]"
        )
        return None

    values = list(struct.unpack_from(f'<{count}f', payload))
    return msg_type, values


def append_history(history: dict[str, list[float]], elapsed_s: float, values: list[float]) -> None:
    ch2, ch1, ch3, ch4, ch5, ch6, t1 = values[:7]
    history['elapsed_s'].append(elapsed_s)
    history['CH2'].append(ch2)
    history['CH1'].append(ch1)
    history['CH3'].append(ch3)
    history['CH4'].append(ch4)
    history['CH5'].append(ch5)
    history['CH6'].append(ch6)
    history['T1'].append(t1)
  


def plot_history(history: dict[str, list[float]], output_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print('matplotlib is not installed. Run: pip install matplotlib')
        return

    if not history['elapsed_s']:
        print('No valid measurement data available for plotting.')
        return

    time_axis = history['elapsed_s']
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    main_plot_path = output_dir / f'force_torque_plot_{timestamp}.png'
    temp_plot_path = output_dir / f'temperature_plot_{timestamp}.png'

    fig_main, (ax_force, ax_torque) = plt.subplots(2, 1, sharex=True, figsize=(12, 8))
    fig_main.suptitle('Main Data Plot')

    for label in ('CH2', 'CH1', 'CH3'):
        ax_force.plot(time_axis, history[label], label=label)
    ax_force.set_ylabel('Force')
    ax_force.grid(True)
    ax_force.legend()

    for label in ('CH4', 'CH5', 'CH6'):
        ax_torque.plot(time_axis, history[label], label=label)
    ax_torque.set_xlabel('Time (s)')
    ax_torque.set_ylabel('Torque')
    ax_torque.grid(True)
    ax_torque.legend()

    fig_temp, ax_temp = plt.subplots(figsize=(12, 4))
    fig_temp.suptitle('Temperature Time Series')
    for label in ('T1'):
        ax_temp.plot(time_axis, history[label], label=label)
    ax_temp.set_xlabel('Time (s)')
    ax_temp.set_ylabel('Temperature (C)')
    ax_temp.grid(True)
    ax_temp.legend()

    fig_main.tight_layout()
    fig_temp.tight_layout()
    fig_main.savefig(main_plot_path, dpi=150)
    fig_temp.savefig(temp_plot_path, dpi=150)
    print(f'Main plot saved to {main_plot_path}')
    print(f'Temperature plot saved to {temp_plot_path}')

    try:
        plt.show(block=True)
    except Exception as exc:
        print(f'Interactive plot display failed: {exc}')
    finally:
        plt.close(fig_main)
        plt.close(fig_temp)


def print_summary(history: dict[str, list[float]]) -> None:
    samples_received = len(history['elapsed_s'])
    if samples_received == 0:
        print('Samples received: 0')
        print('Effective frequency: 0.00 Hz')
        return

    duration_s = history['elapsed_s'][-1]
    frequency_hz = samples_received / duration_s if duration_s > 0 else 0.0
    print(f'Samples received: {samples_received}')
    print(f'Effective frequency: {frequency_hz:.2f} Hz')
    print(f'Recorded duration: {duration_s:.3f} s')


def read_sensor(port: str, baud: int) -> None:
    output_dir = Path(__file__).parent
    csv_path = Path(__file__).with_name(
        f"protocol_trigger_log_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    )
    history = {
        'elapsed_s': [],
        'CH2': [], 'CH1': [], 'CH3': [],
        'CH4': [], 'CH5': [], 'CH6': [],
        'T1': [],
    }

    with serial.Serial(port, baud, timeout=SERIAL_TIMEOUT) as ser:
        print(f"Connected to {port} in protocol mode. Press Ctrl+C to stop.")
        print('Software trigger command: R\\n')
        print(f"Saving data to {csv_path}\n")
        print('If Ctrl+C is slow in Windows Terminal, click the terminal first and press Ctrl+C once.')
        if RECORD_SECONDS is None:
            print('Recording mode: continuous until interrupted.')
        else:
            print(f'Recording mode: automatic stop after {RECORD_SECONDS:.1f} s.')

        start_time = time.perf_counter()

        try:
            with csv_path.open('w', newline='', encoding='utf-8') as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(CSV_HEADERS)

                while True:
                    elapsed_s = time.perf_counter() - start_time
                    if RECORD_SECONDS is not None and elapsed_s >= RECORD_SECONDS:
                        print(f'Completed recording window of {RECORD_SECONDS:.1f} s.')
                        break

                    ser.write(b'R\n')
                    result = read_frame(ser)
                    if result is None:
                        continue

                    msg_type, values = result
                    elapsed_s = time.perf_counter() - start_time

                    if msg_type == MSG_MEASUREMENT and len(values) >= 7:
                        append_history(history, elapsed_s, values)
                        ch2, ch1, ch3, ch4, ch5, ch6, t1 = values[:7]
                        writer.writerow([
                            elapsed_s, 'MEAS',
                            ch2, ch1, ch3, ch4, ch5, ch6,
                            t1,
                            '', '', '', '', '',
                        ])
                        csv_file.flush()
                        print(
                            f"[MEAS] CH2={ch2:10.3f} CH1={ch1:10.3f} CH3={ch3:10.3f} "
                            f"CH4={ch4:10.3f} CH5={ch5:10.3f} CH6={ch6:10.3f} "
                            f"T1={t1:.2f} C"
                        )

                    elif msg_type == MSG_DIAGNOSTIC and len(values) >= 11:
                        append_history(history, elapsed_s, values)
                        ch2, ch1, ch3, ch4, ch5, ch6, t1, current, raw_v, board_temp, board_v = values[:11]
                        sensor_v = (raw_v / board_v * 3.3) if board_v > 0 else 0.0
                        writer.writerow([
                            elapsed_s, 'DIAG',
                            ch2, ch1, ch3, ch4, ch5, ch6,
                            t1,
                            current, raw_v, board_temp, board_v, sensor_v,
                        ])
                        csv_file.flush()
                        print(
                            f"[DIAG] CH2={ch2:10.3f} CH1={ch1:10.3f} CH3={ch3:10.3f} "
                            f"CH4={ch4:10.3f} CH5={ch5:10.3f} CH6={ch6:10.3f} "
                            f"T1={t1:.2f} C"
                            f"I={current:.3f} A V={sensor_v:.3f} V "
                            f"BoardTemp={board_temp:.2f} C BoardV={board_v:.3f} V"
                        )

                    elif msg_type == MSG_CONFIG:
                        continue

        except KeyboardInterrupt:
            print('\nStopped.')

    print('Generating plots...')
    print_summary(history)
    plot_history(history, output_dir)


if __name__ == '__main__':
    read_sensor(PORT, BAUD)

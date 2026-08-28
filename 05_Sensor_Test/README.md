# SensorTest

A repository for debugging and testing sensor data collection, visualization, and analysis scripts.

## Overview

SensorTest provides tools for interfacing with sensors, collecting data, logging measurements, and visualizing results. The codebase includes components for serial communication, data acquisition, storage, and analysis.

## Components

### Executable scripts

- `data_collector.py` - Main script for collecting data from sensors
- `comm_modul.py` - Main script for interacting with Mini-Electronic
- `plot_data.py` - Visualizes collected data with various plotting options

### Serial Communication

- `data_serial.py` - Manages serial port connections with automatic detection and configuration
- `serial_handler.py` - Handles low-level serial communication with the sensor
- `serial_decoder.py` - Frame decoding and CRC validation for framed protocols
- `error_packet_logger.py` - Logs failed communication packets for debugging
- `protocol_definition.py` - Defines commands and transport constants
- `channel_schema.py` - Data model for the payload layout (`ChannelSpec`, `FrameSchema`, `SensorSample`)
- `schema_registry.py` - Loads `device_profiles.json` and resolves a profile per received frame

### User Interface

- `sensor_display.py` - Provides a graphical interface for real-time sensor data display
- `sensor_communicator.py` - Manages communication with the sensor device

### Testing

- `protocol_tests.py` - Contains tests for the communication protocol
- `run_tests.py` - Script to run test suites

### Features

- Serial port auto-detection and configuration
- Real-time data display with configurable UI (light/dark mode)
- Data logging to CSV files with timestamps
- Customizable plotting for sensor data analysis
- Support for multiple protocol modes
- Declarative device profiles: channel layout is configured in `device_profiles.json`, not in code
- Calibration matrix application for sensor measurements

## Protocol & Device Profiles

The meaning of the values a device sends is **not hardcoded in Python**. It is declared in
`device_profiles.json`. Connecting a new device with a different set of channels therefore
usually means adding one JSON entry — no code change.

### How it works

`SerialHandler.read_sensor_data()` no longer returns a bare tuple of floats. It returns a
`SensorSample`, which carries the values *and* the `FrameSchema` that explains them:

```text
serial bytes
   │
   ▼
FrameDecoder            → FrameHeader(message_type, count, counter) + payload
   │
   ▼
SchemaRegistry.resolve(protocol_mode, message_type, payload_count)
   │                                                 → FrameSchema (from device_profiles.json)
   ▼
SensorSample(values, schema, timestamp, frame_counter)
   │
   ├─► SensorCommunicator.send_data_to_display()  → labels/units from the schema
   ├─► DataLogger.add_sample()                    → CSV columns from the schema
   └─► DataPlotter                                → force/torque grouping from channel roles
```

Because `SensorSample` supports indexing, iteration and `len()`, code that used the old
float tuple keeps working.

The legacy 28-byte format has no frame header. It is resolved through the same path using a
synthetic header (`message_type = 0`, `payload_count = 7`), so legacy is just another profile
rather than a special case in the consumers.

### Profile resolution

1. If a profile was pinned via the `profile <id>` command, that profile is used.
2. Otherwise an exact match on `(protocol_mode, message_type, payload_count)` is used.
3. If that fails and exactly **one** profile matches `(message_type, payload_count)`, that one
   is used (same layout declared under a different protocol mode).
4. Otherwise the frame is discarded and a warning is logged **once** per unknown combination.
   There is no silent fallback to generic `CH1..CHn` — an unknown layout is always visible.

The warning names the values it could not match, so it can be pasted straight into a new
profile:

```text
No device profile for protocol_mode=extended, message_type=measurement, payload_count=7
```

### `device_profiles.json` reference

```json
{
    "profiles": [
        {
            "id": "legacy_ft7",
            "device": "Resense FT-Sensor (Legacy, 28 byte)",
            "protocol_mode": "legacy",
            "message_type": "measurement",
            "payload_count": 7,
            "csv_order": ["fX", "fY", "fZ", "mX", "mY", "mZ", "Temperature"],
            "channels": [
                { "key": "fY", "label": "CH2", "unit": "mN", "role": "force", "tarable": true, "csv_column": "fY" }
            ]
        }
    ]
}
```

#### Profile fields

| Field | Required | Description |
| --- | --- | --- |
| `id` | yes | Unique identifier, also written into the CSV header and used by the `profile` command |
| `device` | no | Human-readable device name shown in the display and in `profiles` |
| `protocol_mode` | yes | Name of a `ProtocolMode` member, e.g. `"legacy"`, `"extended"` |
| `message_type` | yes | Name of a `MessageType` member: `"measurement"`, `"config"` or `"diagnostic"` |
| `payload_count` | yes | Number of float32 values in the payload; must equal the length of `channels` |
| `channels` | yes | The floats **in the order they arrive on the wire** |
| `csv_order` | no | CSV column order; defaults to the wire order. Must be a permutation of all `csv_column` values |

`protocol_mode` and `message_type` accept **only the spelled-out names**. Writing the raw
number is rejected with an explicit error — the numbers live in `protocol_definition.py`
and `serial_decoder.py` and are mapped by the `ProtocolMode` / `MessageType` enums in
`channel_schema.py`.

#### Channel fields

| Field | Default | Description |
| --- | --- | --- |
| `key` | — | Unique identifier used for programmatic access (`sample.get("temperature")`) |
| `label` | `key` | Text shown in the live display |
| `unit` | `""` | Unit, documentation only for now |
| `role` | `"other"` | One of `force`, `torque`, `temperature`, `current`, `voltage`, `raw`, `other` |
| `tarable` | `false` | Whether the tare/offset is subtracted from this channel |
| `csv_column` | `key` | Column name in the CSV file |
| `scale` | `1.0` | Reserved for future scaling |
| `precision` | `5` | Decimal places in the live display |

`role` drives the automatic grouping: `DataPlotter` derives its force and torque columns from
it, and the 6×6 calibration matrix is applied to those columns only.

`tarable` drives the tare in `data_collector.py` — the offset array is sized from the schema
and only subtracted from the flagged channels.

### Wire order vs. CSV order

`channels` describes the **wire order**, `csv_order` the **file order**. The shipped FT
profiles need both because the device sends `CH2, CH1, CH4, CH3, CH6, CH5, temp` while the CSV
files have always been written as `fX, fY, fZ, mX, mY, mZ, Temperature`. Keeping them separate
preserves the historic CSV layout and guarantees the calibration matrix receives its columns as
`Fx, Fy, Fz, Mx, My, Mz`.

### Adding a new device / extending the protocol

#### Case A — the device sends a different number or set of channels

1. Determine the frame's `message_type` and `payload_count`. Run `comm_modul.py` and watch the
   log: an unmatched frame prints exactly the values you need:

   ```text
   No device profile for protocol_mode=extended, message_type=diagnostic, payload_count=9 - frame discarded.
   ```

2. Add a profile to `device_profiles.json` with those values and list the channels in wire order:

   ```json
   {
       "id": "gripper_v2",
       "device": "Gripper Sensor v2",
       "protocol_mode": "extended",
       "message_type": "measurement",
       "payload_count": 4,
       "channels": [
           { "key": "fX", "label": "Fx", "unit": "mN", "role": "force", "tarable": true },
           { "key": "fZ", "label": "Fz", "unit": "mN", "role": "force", "tarable": true },
           { "key": "grip", "label": "Grip", "unit": "mm", "role": "other" },
           { "key": "temperature", "label": "Temp", "unit": "degC", "role": "temperature" }
       ]
   }
   ```

3. Restart. Display, CSV logging, tare and plotting adapt automatically. **No Python change.**

#### Case B — a new frame type on an existing device

Add a second profile with the same `protocol_mode` but a different `message_type`. Both are
resolved independently, so a device can mix measurement and diagnostic frames on one link.

#### Case C — a new protocol mode

1. Add the constant in `protocol_definition.py` and the matching member in `ProtocolMode`
   (`channel_schema.py`), so it becomes usable by name in the JSON.
2. Add the profiles.

`SerialHandler.read_sensor_data()` needs no change: `legacy` is the only mode read as a raw
fixed-size block, **every other mode goes through the frame decoder**. Only a genuinely
different transport (other start byte, other CRC) would require touching that code.

#### What still requires code

- A new transport/framing (other start byte, other CRC) → `serial_decoder.py`
- A new protocol mode or message type → new enum member in `channel_schema.py`
- A new channel role beyond the seven listed above → `VALID_ROLES` in `channel_schema.py`
- Per-channel scaling: the `scale` field is parsed and validated but not yet applied

### Runtime commands

In `comm_modul.py`:

| Command | Effect |
| --- | --- |
| `profiles` | Lists all known profiles with their match keys and marks the pinned one |
| `profile <id>` | Pins a profile, bypassing auto-detection — useful when a device sends an ambiguous layout |
| `profile auto` | Returns to auto-detection |

### CSV format

`DataLogger` derives its columns from the schema and writes the profile id as the first line:

```text
# schema_id=legacy_ft7
,timestamp,fX,fY,fZ,mX,mY,mZ,Temperature
0,2026-08-17 11:33:02.166264,2.0,1.0,4.0,3.0,6.0,5.0,24.5
```

`DataPlotter.load_data()` reads that marker back and resolves the schema, which is how it knows
which columns are forces and which are torques. Files without the marker still load — the
plotter then falls back to name-based column detection.

If the schema changes while recording (e.g. after `set protocol_mode`), the current file is
closed and a new one is opened with the profile id appended to the filename. One CSV never
mixes two layouts.

### Profile file location

Which profile file is used is set in `serial_config.json`:

```json
{
    "device_profiles_file": "device_profiles.json"
}
```

A missing or malformed profile file raises an error at startup rather than falling back
silently.

## Configuration

The repository includes several configuration options:

- Protocol modes 28 Byte or 36 Byte receive (28 default)
- Software trigger mode
- Baudrate settings (default: 3000000)
- Plot customization options

### Error Packet Logging

The system can log failed communication packets (e.g., CRC errors) for debugging purposes. This feature is configured in `serial_config.json`:

```json
{
    "error_logging_enabled": false,
    "error_log_directory": "error_logs",
    "error_log_max_size_mb": 5,
    "error_log_max_backups": 3
}
```

**Configuration Options:**

- `error_logging_enabled` - Enable/disable error packet logging (default: `false`)
- `error_log_directory` - Directory where error logs are saved (default: `"error_logs"`)
- `error_log_max_size_mb` - Maximum log file size in MB before rotation (default: `5`)
- `error_log_max_backups` - Number of backup files to keep during rotation (default: `3`)

**Log Format:**

Error logs are saved as JSON files with session-based naming (`error_log_YYYY-MM-DD_HH-MM-SS.json`):

```json
{
  "session_start": "2026-02-11T10:30:00.123456",
  "errors": [
    {
      "timestamp": "2026-02-11T10:30:15.456789",
      "error_type": "CRC_MISMATCH",
      "header_hex": "10000642",
      "payload_hex": "3f8000003f800000...",
      "received_crc": "0x1234",
      "calculated_crc": "0x5678",
      "packet_length": 30,
      "message_type": 0,
      "message_counter": 66
    }
  ]
}
```

**Usage:**

1. Set `"error_logging_enabled": true` in `serial_config.json`
2. Run your sensor application
3. Failed packets are automatically logged to `error_logs/`
4. Analyze logs to identify communication issues

## Installation

Setting Up Development Environment
For the best development experience, follow these steps:

```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Requirements

- Python 3.8 or higher
- Serial port access permissions
- Required packages (automatically installed via requirements.txt):
- pyserial
- pandas
- matplotlib
- numpy
- tkinter (usually comes with Python)

## IDE Configuration

VS Code configuration files are included in the .vscode directory with:

- Debugging configurations for all main scripts
- Test discovery settings
- Python environment settings

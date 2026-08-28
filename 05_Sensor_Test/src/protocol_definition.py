# protocol_definition.py

# Protocol modes
LEGACY = 0  # 28 bytes
STANDARD = 1  # New Protocol only FT-Data
EXTENDED = 2  # New Protocol with additional data

# Commands
SET_BAUD_COMMAND = 'SET BAUD {}\n'
SET_MODE_COMMAND = 'SET MODE {}\n'
READ_COMMAND = 'R\n'
TARA_COMMAND = 'TARA\n'
BOOT_COMMAND = 'BOOT\n'
RESET_COMMAND = 'RESET\n'
GET_MATRIX_COMMAND = 'GET MATRIX\n'
GET_CONFIG_COMMAND = 'GET CONFIG\n'
GET_SENSOR_ID_COMMAND = 'GET SENSOR_ID\n'
GET_ELECTRONICS_ID_COMMAND = 'GET ELECTRONICS_ID\n'
GET_SOFTWARE_VERSION_COMMAND = 'GET FIRMWARE_VERSION\n'
GET_DIAGNOSTICS_COMMAND = 'GET DIAGNOSTICS\n'
GET_BAUDRATE_COMMAND = 'GET BAUD\n'
GET_SENSOR_CONFIG_COMMAND = 'GET SENSOR_CONFIG\n'
GET_ERROR_COMMAND = 'GET ERROR\n'
GET_ERROR_LOG_COMMAND = 'GET ERROR_LOG\n'
SET_CONFIG_MODE_COMMAND = 'SET CONFIG_MODE {}\n'
SET_PROTOCOL_MODE_COMMAND = 'SET PROTOCOL_MODE {}\n'
SET_MATRIX_CALC_COMMAND = 'SET MATRIX_CALC {}\n'
SET_FILTER_COMMAND = 'SET FILTER {}\n'
SET_MATRIX_COMMAND = 'SET MATRIX {} {}\n'
SET_MVPV_COMMAND = 'SET MVpV {}\n'


# Expected response sizes
RESPONSE_SIZE_MODE_LEGACY = 28
RESPONSE_SIZE_MODE_STANDARD = 35


def legacy_format(response_size: int = RESPONSE_SIZE_MODE_LEGACY) -> str:
    """Struct format for the headerless legacy frame."""
    return '<' + 'f' * (response_size // 4)


# Deprecated: channel meaning now lives in device_profiles.json
FORMAT_MODE_LEGACY = legacy_format()
CHANNEL_ORDER = ['CH2', 'CH1', 'CH3', 'CH4', 'CH5', 'CH6', 'temp', 'current', 'voltage']

# Expected value ranges
TEMPERATURE_RANGE = (-10, 80)  # Normal operating temperature range in Celsius
VOLTAGE_RANGE = (11.0, 13.0)   # Expected voltage range
CURRENT_RANGE = (0.0, 1.0)     # Expected current range
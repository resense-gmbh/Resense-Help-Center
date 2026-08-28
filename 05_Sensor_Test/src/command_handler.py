import src.protocol_definition as protocol

def get_commands():
    """
    Return a dictionary with command names as keys and descriptions as values.

    This function is used by the command handler to provide a list of available commands
    and their descriptions to the user.

    Returns:
        dict: Dictionary with command names as keys and descriptions as values
    """
    return {
        "reconnect": "Reconnect to sensor with <baudrate>",
        "disconnect": "Disconnect from sensor",
        "boot": "(Re)boot Mini-Electronic",
        "protocol_mode": "Set protocol mode (1 or 2)",
        "sample_mode": "Set sample mode (0 .. 4)",
        "tara": "Tare sensor",
        "reset": "Reset flash to default values",
        "baud": "Set baud rate",
        "matrix": "Get calibration matrix",
        "config": "Get sensor configuration",
        "cm" : "Set sensor configuration mode",
        "cme": "Exit sensor configuration mode",
        "swt_on": "Enable software trigger mode",
        "swt_off": "Disable software trigger mode",
        "get baud": "Get baudrate",
        "get sensor_config": "Get sensor configuration",
        "get error": "Get sensor error",
        "get error_log": "Get sensor error log",
        "set mvpv_mode": "Set MVpV mode (0: disabled, 1: enabled)",
        "set emulation_mode": "Set emulation mode (0: disabled, 1: enabled)",
        "profiles": "List the known device profiles from device_profiles.json",
        "profile": "Force a device profile <id>, or 'profile auto' to detect it from the frame header",
        "set protocol_mode": "Set protocol mode (0: Legacy, 1: Standard, 2: Extended)",
        "elec_id": "Get electronics ID",
        "diagnostics": "Get diagnostics",
        "help": "Show this help",
        "exit": "Exit program"
    }

def handle_command(command, sensor):
    """Handle user commands and return True if program should exit"""
    
    # Command options - moved from main
    commands = get_commands()
    
    if command == "exit":
        return True
            
    elif command == "help":
        print("\nAvailable commands:")
        for cmd, desc in commands.items():
            print(f"  {cmd:12} - {desc}")
                
    elif command == "disconnect":
        sensor.disconnect()

    elif command.startswith("reconnect "):
        try:
            rate = int(command.split()[1])
            sensor.disconnect()
            sensor.connect(rate)
        except (IndexError, ValueError):
            print("Invalid baud rate. Usage: reconnect <baudrate>") 

    elif command == "profiles":
        active = sensor.schema_registry.forced_profile
        print("\nKnown device profiles:")
        for schema in sensor.schema_registry.schemas:
            marker = " [FORCED]" if schema.id == active else ""
            print(f"  {schema.id:16} mode={schema.protocol_mode.name} type={schema.message_type.name} "
                  f"count={schema.payload_count} - {schema.device}{marker}")
        if active is None:
            print("  (auto-detection active)")

    elif command.startswith("profile "):
        profile_id = command.split(maxsplit=1)[1].strip()
        try:
            sensor.schema_registry.force_profile(None if profile_id == "auto" else profile_id)
            print(f"Profile selection: {profile_id}")
        except Exception as e:
            print(f"Invalid profile: {e}")
    elif command.startswith("set protocol_mode "):
        try:
            mode = int(command.split()[2])
            if mode not in [0, 1, 2]:
                print("Invalid mode. Use 0, 1, or 2.")
            else:
                sensor.send_command(protocol.SET_PROTOCOL_MODE_COMMAND.format(mode), 
                                   f"Setting protocol mode to {mode}")
                sensor.read_command_response(debug=True)
        except (IndexError, ValueError):
            print("Invalid mode. Usage: set protocol_mode <0|1|2>")

    elif command.startswith("sample_mode "):
        try:
            mode = int(command.split()[1])
            if mode not in range(5):
                print("Invalid mode. Use a value between 0 and 4.")
            else:
                sensor.send_command(protocol.SET_MODE_COMMAND.format(mode), 
                                   f"Setting mode to {mode}")
                sensor.set_protocol_mode(mode)
                sensor.read_command_response(debug=True)
        except (IndexError, ValueError):
            print("Invalid mode. Usage: mode <0..4>")
            
    elif command.startswith("baud "):
        try:
            rate = int(command.split()[1])
            sensor.send_command(protocol.SET_BAUD_COMMAND.format(rate), 
                               f"Setting baud rate to {rate}")
            print("Note: You'll need to reconnect at the new baud rate")
        except (IndexError, ValueError):
            print("Invalid baud rate. Usage: baud <rate>")
            
    elif command == "matrix":
        sensor.send_command(protocol.GET_MATRIX_COMMAND, "Requesting calibration matrix")
        sensor.read_command_response(debug=True)

    elif command == "tara":
        sensor.send_command(protocol.TARA_COMMAND, "Taring sensor")

    elif command == "boot":
        print("Rebooting Mini-Electronic")
        sensor.send_command(protocol.BOOT_COMMAND, "(Re)booting Mini-Electronic")

    elif command == "reset":
        print("Resetting flash to default values")
        sensor.send_command(protocol.RESET_COMMAND, "Resetting flash to default values")
        sensor.read_command_response(debug=True)

    elif command == "config":
        sensor.send_command(protocol.GET_CONFIG_COMMAND, "Requesting sensor configuration")
        sensor.read_command_response(debug=True)

    elif command == "get error":
        sensor.send_command(protocol.GET_ERROR_COMMAND, "Requesting sensor error")
        sensor.read_command_response(debug=True)

    elif command == "get error_log":
        sensor.send_command(protocol.GET_ERROR_LOG_COMMAND, "Requesting sensor error log")
        sensor.read_command_response(debug=True)

    elif command == "cm":
        sensor.pause_continuous_read()
        sensor.send_command(protocol.SET_CONFIG_MODE_COMMAND.format(1), "Setting sensor configuration mode")
        print("\nSensor in configuration mode")
        print("Enter 'cme' to exit sensor configuration mode")

    elif command == "cme":
        sensor.send_command(protocol.SET_CONFIG_MODE_COMMAND.format(0), "Exiting sensor configuration mode")
        print("\nSensor configuration mode exited")
        sensor.resume_continuous_read()

    elif command == "get baud":
        sensor.send_command(protocol.GET_BAUDRATE_COMMAND, "Requesting baudrate")
        sensor.read_command_response(debug=True)

    elif command == "get sensor_config":
        sensor.send_command(protocol.GET_SENSOR_CONFIG_COMMAND, "Requesting sensor configuration")
        sensor.read_command_response(debug=True)

    elif command == "swt_on":
        sensor.set_software_trigger_mode(True)
        sensor.read_command_response(debug=True)

    elif command.startswith("set mvpv_mode"):
        try:
            mode = int(command.split()[2])
            if mode not in [0, 1]:
                print("Invalid MVpV mode. Use 0 for disabled, 1 for enabled.")
                return False
            sensor.send_command(protocol.SET_MVPV_COMMAND.format(mode), 
                            f"Setting MVpV mode to {'enabled' if mode == 1 else 'disabled'}")
        except (IndexError, ValueError):
            print("Invalid MVpV mode. Usage: set mvpv_mode <0|1> ; (0: disabled, 1: enabled)")

    elif command == "swt_off":
        sensor.set_software_trigger_mode(False)
        sensor.read_command_response(debug=True)
        
    elif command == "sensor_id":
        sensor.send_command(protocol.GET_SENSOR_ID_COMMAND, "Requesting sensor ID")
        sensor.read_command_response(debug=True)
        
    elif command == "elec_id":
        sensor.send_command(protocol.GET_ELECTRONICS_ID_COMMAND, "Requesting electronics ID")
        sensor.read_command_response(debug=True)
        
    elif command == "diagnostics":
        sensor.send_command(protocol.GET_DIAGNOSTICS_COMMAND, "Requesting diagnostics")
        
    else:
        print(f"Unknown command: {command}")
        print("Type 'help' for available commands")
    
    return False  # Don't exit by default
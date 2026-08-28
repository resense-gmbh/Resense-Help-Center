import serial
import time
import numpy as np
import signal
import src.protocol_definition as protocol
from src.data_logger import DataLogger
from src.data_plotter import DataPlotter
from src.data_serial import SerialPortManager
from src.serial_handler import SerialHandler
from src.schema_registry import SchemaRegistry
import os



# Recording settings
USE_SOFTWARE_TRIGGER = False
RECORD_TIME = 60  # Recording duration in minutes
# --------------------------------------------------

# Global variables
logger = None
exit_requested = False

def signal_handler(sig, frame):
    """Signal handler for clean termination with Ctrl+C"""
    global exit_requested
    print("\nProgram interrupted. Finishing up...")
    exit_requested = True

def cleanup_handler():
    """
    Handler for normal program exit
    This will be called when the program exits normally
    """
    global exit_requested

    # Skip if we're already handling an exit (to avoid duplicate handling)
    if exit_requested:
        return
        
    print("\nProgram is ending normally...")
    
    # Create plotter instance
    plotter = DataPlotter()
    
    if logger:
        logger.save_data()  # Save all remaining data
        
        filename = logger.get_filename()
        plotter.load_data(filename)
        #plotter.plot_temperature(temp_column="Temperature", timestamp_column="timestamp")
        plotter.plot_force(show_stats=True, use_matrix=False)
        
        print(f"Data saved to: {filename}")
        
def cleanup_serial_connection(ser, use_software_trigger):

    # Reset communication mode if using software trigger
    """
    Resets the serial connection to its default state by disabling software trigger mode

    Args:
        ser (serial.Serial): The serial connection to reset
        use_software_trigger (bool): Whether software trigger was used
    """
    if use_software_trigger:
        command =protocol.SET_MODE_COMMAND.format(0)
        ser.write(command.encode('cp1252'))
        time.sleep(0.5)

def setup_serial_connection(serial_port, baudrate, use_software_trigger):
    """
    Sets up the serial connection with the sensor.
    
    Args:
        serial_port (str): COM port for the serial connection
        baudrate (int): Baud rate for the communication
        use_software_trigger (bool): Enable software trigger
        
    Returns:
        serial.Serial: The opened serial connection
    """
    # Open serial connection
    ser = serial.Serial(serial_port, baudrate)
    print(f"Starting data collection on {ser.portstr} at {ser.baudrate} baud.")
    
    # Set protocol mode
    if use_software_trigger:
        print("Set Mode to 4 - Software-Trigger")
        command = protocol.SET_MODE_COMMAND.format(4)
        ser.write(command.encode('cp1252'))
    
    # Set config mode
    print("Set Config Mode to 0 - Normal Mode")
    command = protocol.SET_CONFIG_MODE_COMMAND.format(0x00)
    ser.write(command.encode('cp1252'))
    
    # Wait until the connection is stable
    time.sleep(1)
    
    return ser


def initialize_data_logger(base_directory: str = None) -> DataLogger:
    """
    Initialize the data logger
    
    This function initializes a DataLogger instance with the specified base directory.
    
    Args:
        base_directory (str, optional): Base directory for storing CSV files. Defaults to None.

    Returns:
        DataLogger: The initialized DataLogger instance
    """
    logger = DataLogger(base_directory=base_directory)
    return logger


def process_data(sample, offset):
    """
    Process a decoded sample received from the sensor
    
    Args:
        sample (SensorSample): Values plus the schema describing them
        offset (numpy.ndarray): Per-channel offset values
        
    Returns:
        int: Updated sample count
    """
    return logger.add_sample(sample, offsets=offset)

def read_sensor_data(handler, use_software_trigger):
    """
    Read data from the sensor
    
    Args:
        handler (SerialHandler): Connected serial handler
        use_software_trigger (bool): Whether to use software trigger
        
    Returns:
        SensorSample: Decoded sample, or None if no complete frame was received
    """
    return handler.read_sensor_data(use_software_trigger=use_software_trigger)

def check_temperature(temperature):
    """Check if temperature is within valid range"""
    if temperature == 0 or temperature > 100:
        print("Temperature Error")

def save_data_if_needed():
    """Save data if buffer reaches threshold"""
    if len(logger.data_buffer) >= 10000:  # Buffer size as trigger
        logger.save_data()

def collect_data(handler, use_software_trigger, offsets, end_time):
    """
    Collect data from the sensor until end time is reached
    
    Args:
        handler (SerialHandler): Connected serial handler
        use_software_trigger (bool): Whether to use software trigger
        offsets (dict): Maps schema id to the per-channel offset array
        end_time (float): End time in seconds since epoch
    """
    global exit_requested
    sample_count = 0
    while time.time() < end_time and not exit_requested:
        try:
            sample = read_sensor_data(handler, use_software_trigger)

            if sample is None:
                continue

            offset = offsets.setdefault(sample.schema.id, np.zeros(len(sample), dtype=float))

            # Process data
            sample_count = process_data(sample, offset)
            
            temperature = sample.get('temperature')

            # Display status
            print(f"Samples: {sample_count}, Temp: {temperature:+10.5f}", end='\r')
            
            # Check temperature
            check_temperature(temperature)
            
            # Save data if needed
            save_data_if_needed()
                
        except Exception as e:
            print(f"\nError during data collection: {e}")
            # Continue despite error
            time.sleep(0.1)
            # Check exit flag again
            if exit_requested:
                break

    # After exiting the loop, check if it was due to an interrupt
    if exit_requested:
        print("\nData collection stopped by user.")
        return True  # Return True to indicate interrupted
    
    return False  # Return False to indicate normal completion




def main():
    # Register signal handlers and initialize logger
    global exit_requested, logger, ser
    signal.signal(signal.SIGINT, signal_handler)  # CTRL+C

    data_dir = os.path.join(os.getcwd(), "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    logger = initialize_data_logger(base_directory=data_dir)
    
    serial_port_manager = SerialPortManager()
    serial_port, baudrate = serial_port_manager.select_port_interactive()

    # Configuration
    protocol_mode = serial_port_manager.get_protocol_mode()
    use_software_trigger = USE_SOFTWARE_TRIGGER
    record_time = RECORD_TIME
    
    ser = None
    interupted = False
    
    try:
        # Setup serial connection
        ser = setup_serial_connection(serial_port, baudrate, use_software_trigger)
        
        handler = SerialHandler(
            connection=ser,
            protocol_mode=protocol_mode,
            error_logging_config=serial_port_manager.get_error_logging_config(),
            schema_registry=SchemaRegistry.from_file(serial_port_manager.get_device_profiles_file())
        )

        # Offsets are sized per schema once the first sample of that schema arrives
        offsets = {}
        
        # Start data collection
        start_time = time.time()
        end_time = start_time + (record_time * 60)

        timestamp_start = time.localtime()
        formatted_timestamp = time.strftime("%Y-%m-%d %H:%M:%S", timestamp_start)
        print(f"{formatted_timestamp} Starting data collection for {record_time} minutes. Press CTRL+C to stop.")
        
        # Collect data until end time
        interupted = collect_data(handler, use_software_trigger, offsets, end_time)

        if not interupted:
            print("\nData collection completed successfully.")

    except KeyboardInterrupt:
        # CTRL+C was pressed - handled by the signal handler
        pass
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        # Cleanup
        if ser and ser.is_open:
            # switch back to normal mode
            cleanup_serial_connection(ser, use_software_trigger)
            
            print("Closing serial connection...")
            ser.close()
        
        # Save any remaining data
        if logger:
            print("Saving data...")
            filename = logger.save_data()
            print(f"Data saved to: {filename}")
            
            # Plot the temperature data
            print("Plotting temperature data...")
            try:
                plotter = DataPlotter()
                filename = logger.get_filename()
                plotter.load_data(filename)
                plotter.plot_temperature(temp_column="Temperature", timestamp_column="timestamp")
                print("Temperature plot displayed. Close plot window to exit.")
            except Exception as e:
                print(f"Error plotting data: {e}")
        

if __name__ == "__main__":
    main()
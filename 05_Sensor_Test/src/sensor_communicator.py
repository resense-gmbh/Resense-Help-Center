import serial
import time
import src.protocol_definition as protocol
from src.data_serial import SerialPortManager
from src.serial_handler import SerialHandler
from src.channel_schema import SensorSample
from src.schema_registry import SchemaRegistry
import src.sensor_display as sensor_display
import threading
import queue
import collections
from typing import Optional


class SensorCommunicator:
    """Class for communicating with a connected sensor."""
    # Define command types as constants
    CMD_PAUSE = "PAUSE"
    CMD_RESUME = "RESUME"
    CMD_STOP = "STOP"
    CMD_SET_PROTOCOL = "SET_PROTOCOL"
    CMD_SOFTWARE_TRIGGER_MODE = "SOFTWARE_TRIGGER_MODE"
    def __init__(self):
        """Initialize the sensor communicator."""
        self.serial_manager = SerialPortManager()
        self.protocol_mode = self.serial_manager.get_protocol_mode()
        error_logging_config = self.serial_manager.get_error_logging_config()
        self.schema_registry = SchemaRegistry.from_file(
            self.serial_manager.get_device_profiles_file()
        )
        self.serial_handler = SerialHandler(
            protocol_mode=self.protocol_mode,
            error_logging_config=error_logging_config,
            schema_registry=self.schema_registry
        )
        self.connection = None
        self.active_schema_id = None

        # Thread control
        self.is_running = False
        self.is_paused = False

        self.software_trigger_mode = False

        # Queues for thread communication
        self.display_queue = queue.Queue()
        self.command_queue = queue.Queue()
        self.freq_queue = queue.Queue()  # New queue for frequency updates
        self.data_timestamps = collections.deque(maxlen=100)  # Store recent timestamps
        self.last_freq_update = time.time()

        # Thread references
        self.display_thread = None
        self.read_thread = None
        
    def start_display(self, dark_mode=True):
        """Start the display in a separate thread."""
        if self.display_thread is not None and self.display_thread.is_alive():
            print("Data display window already running")
            self.update_display_status("Data display window already running")
            return

        if self.display_thread is None or not self.display_thread.is_alive():
            self.display_thread = threading.Thread(
                target=sensor_display.start_display,
                args=(self.display_queue,self.freq_queue, dark_mode),
                daemon=True
            )
            self.display_thread.start()
            print("Data display window started")

    def update_frequency(self):
        """Calculate and update data frequency."""
        now = time.time()
        # Add current timestamp to the queue
        self.data_timestamps.append(now)
        
        # Only update frequency display once per second to avoid flickering
        if now - self.last_freq_update >= 1.0 and len(self.data_timestamps) >= 2:
            # Calculate frequency based on timestamps in the queue
            if len(self.data_timestamps) >= 2:
                # Calculate time span
                time_span = self.data_timestamps[-1] - self.data_timestamps[0]
                if time_span > 0:
                    # Calculate frequency (samples per second)
                    frequency = (len(self.data_timestamps) - 1) / time_span
                    
                    # Send frequency update
                    self.freq_queue.put({"frequency": frequency})
                    self.last_freq_update = now    
            
    def update_display_status(self, message):
        """Update the status in the display window."""
        self.display_queue.put({"type": "status", "message": message})
        
    def send_data_to_display(self, data):
        """Send data to be displayed in the display window."""
        if isinstance(data, SensorSample):
            if data.schema.id != self.active_schema_id:
                self.active_schema_id = data.schema.id
                self.update_display_status(f"Active profile: {data.schema}")
            message = data.format_channels()
        else:
            message = str(data)
            
        self.display_queue.put({"type": "data", "message": message})
        
    def connect(self, new_baudrate: Optional[int] = None) -> bool:
        """
        Connect to the sensor.
        
        Args:
            new_baudrate: Overrides the baudrate from serial_config.json when given
        
        Returns:
            bool: True if connection successful
        """
        port, baudrate = self.serial_manager.select_port_interactive()


        if not port:
            print("No port selected")
            self.update_display_status("No port selected")
            return False
        
        if new_baudrate is not None and new_baudrate != baudrate:
            print(f"Overriding configured baudrate {baudrate} with {new_baudrate}")
            baudrate = new_baudrate
            
        try:
            self.connection = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=1.0
            )
            
            # Clear buffers
            self.connection.reset_input_buffer()
            self.connection.reset_output_buffer()

            self.serial_handler.set_connection(self.connection)
            self.serial_handler.set_protocol_mode(self.protocol_mode)
            
            status_msg = f"Connected to sensor on {port} at {baudrate} baud"
            print(status_msg)
            self.update_display_status(status_msg)
            return True
        except Exception as e:
            error_msg = f"Connection error: {e}"
            print(error_msg)
            self.update_display_status(error_msg)
            return False

    def disconnect(self) -> None:
        """Disconnect from the sensor."""
        self.is_running = False
        time.sleep(0.5)  # Give time for any ongoing operations to finish
        
        if self.connection and self.connection.is_open:
            self.connection.reset_input_buffer()
            self.connection.reset_output_buffer()
            self.connection.close()
            print("Disconnected from sensor")
            self.update_display_status("Disconnected from sensor")
    
    def set_protocol_mode(self, mode: int) -> bool:
        """
        Set the protocol mode on the sensor.
        
        Args:
            mode: The protocol mode to set
            
        Returns:
            bool: True if successful
        """
        """Set the protocol mode."""
        if mode in [protocol.LEGACY, protocol.STANDARD, protocol.EXTENDED]:
            self.protocol_mode = mode
            self.serial_handler.set_protocol_mode(mode)
            # Also send to command queue if read thread is running
            if self.is_running:
                self.command_queue.put((protocol.SET_PROTOCOL_MODE_COMMAND, mode))
            return True
        return False
    
    def set_software_trigger_mode(self, mode: bool = False) -> bool:
        """
        Set the software trigger mode on the sensor.
        
        Args:
            mode: The software trigger mode to set (default: False)
            
        Returns:
            bool: True if successful
        """
        """Set the protocol mode."""
        self.software_trigger_mode = mode
        protocol_mode = 4 if mode else 2
        self.serial_handler.send_command(protocol.SET_MODE_COMMAND.format(protocol_mode))
        # Also send to command queue if read thread is running
        if self.is_running:
            self.command_queue.put((self.CMD_SOFTWARE_TRIGGER_MODE, mode))

        self.send_data_to_display(f"Set mode to: {protocol_mode}")
        return True
    
   
    def start_continuous_display(self):
        """Start continuously displaying sensor data in a separate window."""
        if not self.connection or not self.connection.is_open:
            print("Not connected to sensor")
            self.update_display_status("Not connected to sensor")
            return
            
        # Make sure the display window is open
        self.start_display()
        
        print("Starting continuous sensor data display")
        self.update_display_status("Reading sensor data...")
        
        # Set the running flag
        self.is_running = True
        
        # Give time for the display window to open
        time.sleep(1)
        # Start the reading thread
        self.start_continuous_read()

  

        
    def start_continuous_read(self):
        """Start the continuous read loop in a separate thread."""
        if self.read_thread is not None and self.read_thread.is_alive():
            print("Continuous read already running")
            return False
            
        if not self.connection or not self.connection.is_open:
            print("Not connected to any device")
            return False
            
        # Create and start the thread
        self.is_running = True
        self.is_paused = False
        self.read_thread = threading.Thread(
            target=self.continuous_read_loop,
            daemon=True
        )
        self.read_thread.start()
        print("Started continuous read")
        return True
    
    def pause_continuous_read(self):
        """Pause the continuous read loop."""
        if not self.is_running or self.is_paused:
            return False
        self.command_queue.put((self.CMD_PAUSE, None))
        return True
    
    def resume_continuous_read(self):
        """Resume the continuous read loop."""
        if not self.is_running or not self.is_paused:
            return False
        self.command_queue.put((self.CMD_RESUME, None))
        return True
    
    def stop_continuous_read(self):
        """Stop the continuous read loop."""
        if not self.is_running:
            return False
        self.command_queue.put((self.CMD_STOP, None))
        # Wait for thread to terminate
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=2.0)
        self.is_running = False
        self.is_paused = False
        return True
    
    def continuous_read_loop(self):
        """The main continuous read loop that runs in a separate thread."""
        try:
            while self.is_running:
                # Check for commands in the queue
                try:
                    # Non-blocking check for commands
                    cmd, value = self.command_queue.get(block=False)
                    
                    if self.software_trigger_mode:
                        msg = "in software trigger mode"
                    else:
                        msg = "in continuous mode"
                    

                    if cmd == self.CMD_PAUSE:
                        self.is_paused = True
                        self.update_display_status("Continuous value reading paused")
                    elif cmd == self.CMD_RESUME:
                        self.is_paused = False
                        self.update_display_status(f"Reading resumed {msg}")
                    elif cmd == self.CMD_STOP:
                        self.update_display_status("Reading stopped")
                        break  # Exit the loop
                    elif cmd == self.CMD_SET_PROTOCOL:
                        self.protocol_mode = value
                        self.serial_handler.set_protocol_mode(value)
                        self.update_display_status(f"Protocol mode set to {value}")
                    elif cmd == self.CMD_SOFTWARE_TRIGGER_MODE:
                        self.software_trigger_mode = value
                        print(f"Software trigger mode set to {value}")
                        self.update_display_status(f"Software trigger mode set to {value}")
                        
                    self.command_queue.task_done()
                    
                except queue.Empty:
                    # No commands in queue, continue normal operation
                    pass
                
                # If paused, just sleep and continue the loop
                if self.is_paused:
                    time.sleep(0.1)
                    continue
                
                # Read data from the sensor
                data = self.serial_handler.read_sensor_data(debug=False, use_software_trigger=self.software_trigger_mode)
                
                if data:
                    # Send to display
                    self.send_data_to_display(data)

                    # Update frequency calculation
                    self.update_frequency()
                else:
                    # Sleep a bit to avoid hammering the serial port
                    if not self.software_trigger_mode:
                        time.sleep(0.01)
                    
        except Exception as e:
            self.update_display_status(f"Error in read loop: {e}")
            print(f"Error in continuous read loop: {e}")
        finally:
            self.is_running = False
            self.is_paused = False
            self.update_display_status("Read loop terminated")

    def send_command(self, command_string, status_msg=None, debug=False):
        """
        Send a command to the sensor.
        
        Args:
            command_string: The command to send
            
        Returns:
            bool: True if command sent successfully
        """
        if status_msg:
            self.send_data_to_display(status_msg)
        return self.serial_handler.send_command(command_string, debug=debug)

    def read_command_response(self, debug):
        data = self.serial_handler.read_command_response(debug=debug)

        if data:
            self.send_data_to_display(data=data)
    

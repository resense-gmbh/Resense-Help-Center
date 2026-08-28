import serial
import serial.tools.list_ports
import time
import json
import os
from typing import List, Dict, Optional, Tuple
import src.protocol_definition as protocol

class SerialPortManager:
    """
    Class for managing serial interfaces.
    Enables listing, selecting, and connecting to serial ports.
    Includes saving/loading port configuration from a file.
    """
    
    def __init__(self, config_file: str = "serial_config.json", default_baudrate: int = 3000000):
        """
        Initializes the SerialPortManager.
        
        Args:
            config_file: Path to the configuration file
            default_baudrate: Default baudrate to use if not specified in config
        """
        self.available_ports = []
        self.selected_port = None
        self.serial_connection = None
        self.config_file = config_file
        self.baudrate = default_baudrate
        self.protocol_mode = protocol.LEGACY  # Default protocol mode
        self.device_profiles_file = "device_profiles.json"
        
        # Error logging configuration
        self.error_logging_config = {
            'enabled': False,
            'directory': 'error_logs',
            'max_size_mb': 5,
            'max_backups': 3
        }
        
        # Load previously selected port if available
        self.load_config()
        self.refresh_ports()

    def set_baudrate(self, baudrate: int) -> None:
        """
        Sets the baudrate.
        
        Args:
            baudrate: The baudrate to set
        """
        self.baudrate = baudrate
    
    def refresh_ports(self) -> List[Dict[str, str]]:
        """
        Updates the list of available serial ports.
        
        Returns:
            List[Dict[str, str]]: List of available ports with details
        """
        self.available_ports = []
        for port in serial.tools.list_ports.comports():
            port_info = {
                'device': port.device,
                'name': port.name,
                'description': port.description,
                'hwid': port.hwid,
                'vid': port.vid,
                'pid': port.pid,
                'manufacturer': port.manufacturer if hasattr(port, 'manufacturer') else 'Unknown'
            }
            self.available_ports.append(port_info)
        
        # Check if previously selected port is still available
        if self.selected_port:
            available_devices = [port['device'] for port in self.available_ports]
            if self.selected_port not in available_devices:
                print(f"Warning: Previously selected port {self.selected_port} is no longer available.")
        
        return self.available_ports
    
    def list_ports(self) -> None:
        """
        Displays a list of available serial ports in the terminal.
        """
        self.refresh_ports()
        
        if not self.available_ports:
            print("No serial ports found.")
            return
        
        print("\nAvailable serial ports:")
        print(f"{'No':>3} | {'Port':<6} | {'Description':<50} | {'Manufacturer':<12} | {'Status':<6} | {'Vendor ID':<6} | {'Product ID':<6}")
        print("-" * 100)
        
        for i, port in enumerate(self.available_ports, 1):
            # Shortened description for better readability
            description = port['description']
            if len(description) > 47:
                description = description[:44] + "..."
                
            manufacturer = port['manufacturer']
            if len(manufacturer) > 17:
                manufacturer = manufacturer[:14] + "..."

            vendor_id = f"0x{port['vid']:04X}" if port['vid'] is not None else 'N/A'
            product_id = f"0x{port['pid']:04X}" if port['pid'] is not None else 'N/A'
            
            # Mark the currently selected port
            status = " [USED]" if port['device'] == self.selected_port else ""

            print(f"{i:3d} | {port['device']:<6} | {description:<50} | {manufacturer:<12} |{status:<7} | {vendor_id:<6} | {product_id:<6}")

    def get_protocol_mode(self) -> int:
        """
        Gets the current protocol mode.
        
        Returns:
            int: The current protocol mode
        """
        return self.protocol_mode

    def get_device_profiles_file(self) -> str:
        """
        Gets the path of the device profile file describing the payload layouts.

        Returns:
            str: Path to the device profiles JSON file
        """
        return self.device_profiles_file

    def select_port_interactive(self, save_config: bool = True) -> Tuple[Optional[str], Optional[int]]:
        """
        Enables interactive selection of a serial port in the terminal.
        
        Args:
            save_config: Whether to save the selection to config file
            
        Returns:
            Optional[str]: The selected port name or None if cancelled
            Optional[int]: The selected baudrate
        """
        self.list_ports()
        
        if not self.available_ports:
            return None, None

        if self.selected_port and self.baudrate:
            print(f"\nPreviously selected port: {self.selected_port}")
            return self.selected_port, self.baudrate
        
        while True:
            try:
                selection = input("\nSelect a port (enter number or 'q' to cancel): ")
                
                if selection.lower() == 'q':
                    return None, None
                
                index = int(selection)
                if 1 <= index <= len(self.available_ports):
                    self.selected_port = self.available_ports[index-1]['device']
                    print(f"Port {self.selected_port} selected.")
                    
                    if save_config:
                        self.save_config()
                    
                    return self.selected_port, self.baudrate
                else:
                    print(f"Please enter a number between 1 and {len(self.available_ports)}.")
            except ValueError:
                print("Please enter a valid number.")
    
    def save_config(self) -> bool:
        """
        Saves the current port configuration to a file.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.selected_port:
            return False
            
        config = {
            'selected_port': self.selected_port,
            'baudrate': self.baudrate,
            'protocol_mode': self.protocol_mode,
            'device_profiles_file': self.device_profiles_file,
            'error_logging_enabled': self.error_logging_config['enabled'],
            'error_log_directory': self.error_logging_config['directory'],
            'error_log_max_size_mb': self.error_logging_config['max_size_mb'],
            'error_log_max_backups': self.error_logging_config['max_backups'],
            'last_used': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
            print(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False
    
    def load_config(self) -> bool:
        """
        Loads port configuration from a file.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not os.path.exists(self.config_file):
            return False
            
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            self.selected_port = config.get('selected_port')
            last_used = config.get('last_used', 'unknown')

            self.baudrate = config.get('baudrate', self.baudrate)

            self.protocol_mode = config.get('protocol_mode', self.protocol_mode)
            self.device_profiles_file = config.get('device_profiles_file', self.device_profiles_file)
            
            # Load error logging configuration
            self.error_logging_config['enabled'] = config.get('error_logging_enabled', False)
            self.error_logging_config['directory'] = config.get('error_log_directory', 'error_logs')
            self.error_logging_config['max_size_mb'] = config.get('error_log_max_size_mb', 5)
            self.error_logging_config['max_backups'] = config.get('error_log_max_backups', 3)
            
            if self.selected_port:
                print(f"Loaded {self.config_file}: {self.selected_port}, baudrate: {self.baudrate} (last used: {last_used})")
            return True
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return False
    
    def connect(self, port: Optional[str] = None, baudrate: int = 9600, 
                timeout: float = 1.0) -> Optional[serial.Serial]:
        """
        Establishes a connection to a serial port.
        
        Args:
            port: The port to use (if None, uses the previously selected port)
            baudrate: The baudrate to use
            timeout: The timeout value in seconds
            
        Returns:
            Optional[serial.Serial]: The Serial object or None on error
        """
        if port is None:
            port = self.selected_port
            
        if port is None:
            print("No port selected. Please select a port first.")
            return None
        
        try:
            # Close existing connection if present
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
            
            # Establish new connection
            self.serial_connection = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=timeout,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                rtscts=False,  # Disable hardware flow control
                dsrdtr=False,  # Disable hardware flow control
                xonxoff=False  # Disable software flow control
            )
            
            print(f"Connection to {port} established at {baudrate} baud.")
            return self.serial_connection
            
        except serial.SerialException as e:
            print(f"Error connecting to {port}: {e}")
            return None
    
    def get_error_logging_config(self) -> dict:
        """
        Get the error logging configuration.
        
        Returns:
            dict: Error logging configuration dictionary
        """
        return self.error_logging_config.copy()
   
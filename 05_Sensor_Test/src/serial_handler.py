# serial_handler.py
import time
import struct
import datetime
import src.protocol_definition as protocol
import traceback
import src.serial_decoder as serial_decoder
from src.channel_schema import SensorSample
from src.schema_registry import SchemaRegistry, UnknownSchemaError
from src.error_packet_logger import ErrorPacketLogger
import logging

logger = logging.getLogger(__name__)


class SerialHandler:
    """Handles all serial communication with the sensor."""

    PLAUSIBILITY_LOG_INTERVAL = 2.0  # seconds between repeated warnings
    
    def __init__(self, connection=None, protocol_mode=protocol.LEGACY, error_logging_config=None,
                 schema_registry=None):
        """
        Initialize the serial handler.
        
        Args:
            connection: Optional existing serial connection
            protocol_mode: Protocol mode to use
            error_logging_config: Optional error logging configuration dict
            schema_registry: SchemaRegistry describing the payload layouts
        """
        self.connection = connection
        self.protocol_mode = protocol_mode
        self.encoded_read_command = protocol.READ_COMMAND.encode('cp1252')
        self.schema_registry = schema_registry or SchemaRegistry.from_file()
        self._reported_unknown_schemas = set()
        
        # Initialize error logger if enabled
        error_logger = None
        if error_logging_config and error_logging_config.get('enabled', False):
            error_logger = ErrorPacketLogger(
                log_directory=error_logging_config.get('directory', 'error_logs'),
                max_size_mb=error_logging_config.get('max_size_mb', 5),
                max_backups=error_logging_config.get('max_backups', 3)
            )
        
        self.frame_decoder = serial_decoder.FrameDecoder(
            error_logger=error_logger,
            allowed_counts={s.payload_count for s in self.schema_registry.schemas},
        )
        self.error_logger = error_logger

        # Bytes read ahead of the current frame, carried over into the next call
        self._rx_buffer = b""
        self._rx_pos = 0
        self._last_frame_counter = None
        self.dropped_frames = 0
        self.implausible_samples = 0
        self._last_plausibility_log = 0.0
        self._last_implausible_counter = None
        self.implausible_periods = {}
    
    def set_connection(self, connection):
        """Set the serial connection."""
        self.connection = connection
        self._discard_read_ahead()

    def _discard_read_ahead(self):
        """Drop buffered bytes and half-decoded frame state."""
        self._rx_buffer = b""
        self._rx_pos = 0
        self._last_frame_counter = None
        self.frame_decoder.reset()
    
    def set_protocol_mode(self, mode):
        """Set the protocol mode."""
        self.protocol_mode = mode
    
    def is_connected(self):
        """Check if the connection is open and valid."""
        return self.connection is not None and self.connection.is_open
    
    def clear_buffers(self):
        """Clear input and output buffers."""
        if self.is_connected():
            self.connection.reset_input_buffer()
            self.connection.reset_output_buffer()
        self._discard_read_ahead()
    
    def send_command(self, command_string, debug=False):
        """
        Send a command to the sensor in 28-byte chunks.
        
        Args:
            command_string: The command to send
            debug: Whether to print debug info
            
        Returns:
            bool: True if command sent successfully
        """
        if not self.is_connected():
            return False
            
        try:
            #self.clear_buffers()
            # Encode the command
            cmd_str = command_string.encode('cp1252')
            
            # Pad to 8-byte boundary first
            len_cmd = len(cmd_str)
            if len_cmd % 8 != 0:
                padding_needed = 8 - (len_cmd % 8)
                padding = b' ' * padding_needed
                cmd_str = cmd_str[:-1] + padding + cmd_str[-1:]
            
            # Send data in 28-byte chunks
            chunk_size = 28
            total_bytes = len(cmd_str)
            chunks_sent = 0
            
            for i in range(0, total_bytes, chunk_size):
                # Extract chunk (up to 28 bytes)
                chunk = cmd_str[i:i + chunk_size]
                
                # Send the chunk
                self.connection.write(chunk)
                chunks_sent += 1
                
                if debug:
                    logger.info(f"Sent chunk {chunks_sent}: {len(chunk)} bytes (total: {i + len(chunk)}/{total_bytes})")
                
            
            if debug:
                logger.info(f"Command sent successfully: {command_string}")
                logger.info(f"Total: {chunks_sent} chunks, {total_bytes} bytes")
            
            return True
            
        except Exception as e:
            if debug:
                logger.error(f"Error sending command: {e}")
            return False
    
    def read_command_response(self, timeout=1.0, debug=False):
        """
        Read response to a command.
        
        Args:
            timeout: Timeout in seconds
            debug: Whether to print debug info
            
        Returns:
            str: The response text or None if error
        """
        if not self.is_connected():
            return None
            
        try:
            # Collect data for the entire timeout duration
            start_time = time.time()
            collected_data = b''  # Buffer for collected data
            
            while time.time() - start_time < timeout:
                if debug and self.connection.in_waiting > 0:
                    logger.info(f"Reading {self.connection.in_waiting} bytes...")
                
                # Read any available data
                if self.connection.in_waiting > 0:
                    new_data = self.connection.read(self.connection.in_waiting)
                    collected_data += new_data
                    if debug:
                        logger.info(f"Collected {len(new_data)} bytes, total: {len(collected_data)} bytes")
                
                time.sleep(0.01)  # Small delay to prevent CPU overload

            if len(collected_data) == 0:
                return None
            
            # Decode and return all collected data
            return collected_data.decode('cp1252')
        
        except Exception as e:
            logger.error("Error reading command response")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception message: {e}")
            logger.error("Stack trace:")
            traceback.print_exc()
            return None

    
    def _build_sample(self, values, message_type, frame_counter, debug=False, payload=None):
        """Attach the matching schema to raw float values."""
        try:
            schema = self.schema_registry.resolve(self.protocol_mode, message_type, len(values))
        except UnknownSchemaError as e:
            if e.args not in self._reported_unknown_schemas:
                self._reported_unknown_schemas.add(e.args)
                logger.warning(f"{e} - frame discarded. Add a matching entry to device_profiles.json.")
            return None

        sample = SensorSample(
            values=tuple(values),
            schema=schema,
            timestamp=datetime.datetime.now(),
            frame_counter=frame_counter,
            message_type=message_type,
        )
        self._check_plausibility(sample, payload)
        return sample

    def _check_plausibility(self, sample, payload=None):
        """Warn about values outside the declared channel range - a mis-decoded frame."""
        issues = sample.implausible_channels()
        if not issues:
            return

        self.implausible_samples += 1

        # Distance to the previous bad frame: a constant period points at the source clocking,
        # a random one at transmission noise.
        period = None
        if sample.frame_counter is not None:
            if self._last_implausible_counter is not None:
                period = (sample.frame_counter - self._last_implausible_counter) & 0xFF
                self.implausible_periods[period] = self.implausible_periods.get(period, 0) + 1
            self._last_implausible_counter = sample.frame_counter

        now = time.time()
        if now - self._last_plausibility_log < self.PLAUSIBILITY_LOG_INTERVAL:
            return
        self._last_plausibility_log = now

        channel_keys = [c.key for c in sample.schema.channels]
        parts = []
        for channel, value, reason in issues:
            raw = ""
            if payload is not None:
                index = channel_keys.index(channel.key)
                word = payload[index * 4:index * 4 + 4]
                if len(word) == 4:
                    raw = f" raw=0x{int.from_bytes(word, 'little'):08X}"
            parts.append(f"{channel.label}={value:.3f}{channel.unit} ({reason}){raw}")

        logger.warning(
            f"Implausible value in frame counter={sample.frame_counter} "
            f"[{sample.schema.id}]: {'; '.join(parts)} | period={period}, "
            f"total={self.implausible_samples}, periods={self.implausible_periods}, "
            f"decoder stats={self.frame_decoder.stats}"
        )
        logger.warning(f"  full frame: {['%.3f' % v for v in sample.values]}")

    def _check_frame_continuity(self, header):
        """Warn when the 8-bit frame counter skips, which indicates lost or faked frames."""
        previous = self._last_frame_counter
        self._last_frame_counter = header.counter
        if previous is None:
            return
        gap = (header.counter - previous) & 0xFF
        if gap != 1:
            self.dropped_frames += gap - 1
            logger.warning(
                f"Frame counter gap: {previous} -> {header.counter} (missing {gap - 1}); "
                f"decoder stats={self.frame_decoder.stats}"
            )

    def read_sensor_data(self, debug=False, use_software_trigger=False, timeout=1.0):
        """
        Read a single data packet from the sensor.
        
        Args:
            debug: Whether to print debug information
            use_software_trigger: Whether to trigger a read via software
            timeout: Timeout in seconds for Mode 3 reading
            
        Returns:
            SensorSample: Values plus the schema describing them, or None if error
        """
        if not self.is_connected():
            return None
            
        try:
            # Trigger data readout 
            if use_software_trigger:
                self.connection.write(self.encoded_read_command)
            
            if self.protocol_mode == protocol.LEGACY:
                # Legacy is the only mode without a frame header: fixed-size binary block
                expected_size = protocol.RESPONSE_SIZE_MODE_LEGACY
                response = self.connection.read(expected_size)
                
                if len(response) < expected_size:
                    if debug:
                        logger.warning(f"Incomplete data: expected {expected_size} bytes, got {len(response)}")
                    return None
                
                try:
                    values = struct.unpack(protocol.legacy_format(expected_size), response)
                except struct.error:
                    return None

                return self._build_sample(
                    values, serial_decoder.MEASUREMENT_DATA, None, debug=debug
                )

            else:
                # Every other mode uses the framed protocol
                start_time = time.time()
                process_byte = self.frame_decoder.process_byte

                while True:
                    # Drain the read-ahead buffer before touching the port again
                    buffer = self._rx_buffer
                    pos = self._rx_pos
                    end = len(buffer)

                    while pos < end:
                        result = process_byte(buffer[pos])
                        pos += 1

                        if result is not None:
                            self._rx_pos = pos
                            header, payload = result
                            self._check_frame_continuity(header)
                            floats = self.frame_decoder.parse_floats(payload)
                            if debug:
                                logger.info(f"Header: {header}")
                                logger.info(f"Decoded Protocol data: {floats}")
                            return self._build_sample(
                                floats, header.message_type, header.counter, debug=debug,
                                payload=payload,
                            )

                    self._rx_pos = pos

                    if time.time() - start_time >= timeout:
                        if debug:
                            logger.warning("Timeout waiting for a complete frame")
                        return None

                    # One blocking read per chunk instead of one syscall pair per byte
                    chunk = self.connection.read(max(1, self.connection.in_waiting))
                    if chunk:
                        self._rx_buffer = chunk
                        self._rx_pos = 0
                
        except Exception as e:
            if debug:
                logger.error(f"Error reading sensor data: {e}")
                traceback.print_exc()
            return None

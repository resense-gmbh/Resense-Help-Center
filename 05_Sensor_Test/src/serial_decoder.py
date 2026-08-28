import struct
import logging
from collections import deque
from datetime import datetime
from typing import Optional, Set
from src.error_packet_logger import ErrorPacketLogger

START_BYTE = 0x7E

# Upper bound for header[2] when no explicit whitelist is supplied
MAX_FLOAT_COUNT = 64

MEASUREMENT_DATA = 0x00
CONFIGURATION_DATA = 0x01
DIAGNOSTIC_DATA = 0x02

PROTOCOL_VERSION = 1

VALID_TYPES = {MEASUREMENT_DATA, CONFIGURATION_DATA, DIAGNOSTIC_DATA}

logger = logging.getLogger(__name__)

# CRC16-CCITT (0x1021), initial 0xFFFF
def _build_crc16_table():
    table = []
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        table.append(crc)
    return tuple(table)


CRC16_TABLE = _build_crc16_table()


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ CRC16_TABLE[(crc >> 8) ^ b]
    return crc


class FrameHeader:
    """Represents a decoded frame header with easy access to fields."""
    
    def __init__(self, header_bytes: bytes):
        """
        Parse header bytes into structured data.
        
        Header format:
        - Byte 0: Version (upper 4 bits) | Flags (lower 4 bits)
        - Byte 1: Message Type
        - Byte 2: Count (number of float32 values)
        - Byte 3: Message counter
        """
        self.raw = bytes(header_bytes)
        self.version = (header_bytes[0] >> 4) & 0x0F
        self.flags = header_bytes[0] & 0x0F
        self.message_type = header_bytes[1]
        self.count = header_bytes[2]
        self.counter = header_bytes[3]
    
    def __repr__(self):
        return (f"FrameHeader(version={self.version}, flags={self.flags}, "
                f"type={self.message_type}, count={self.count}), counter={self.counter})")
    
    def __str__(self):
        type_names = {0x00: "MEASUREMENT", 0x01: "CONFIG", 0x02: "DIAGNOSTIC"}
        type_str = type_names.get(self.message_type, f"UNKNOWN(0x{self.message_type:02X})")
        return f"v{self.version} {type_str} count={self.count} counter={self.counter}"


"""State machine for decoding incoming serial data frames."""
class FrameDecoder:
    ST_WAIT_START = 0
    ST_READ_HEADER = 1
    ST_READ_PAYLOAD = 2
    ST_READ_CRC = 3

    def __init__(self, error_logger: Optional[ErrorPacketLogger] = None,
                 allowed_counts: Optional[Set[int]] = None):
        self.state = self.ST_WAIT_START
        self.header = bytearray(4)
        self.payload = bytearray()
        self.crc_buf = bytearray(2)
        self.hdr_index = 0
        self.payload_index = 0
        self.expected_payload_len = 0
        self.last_logged_version = None
        self.error_logger = error_logger
        self.allowed_counts = set(allowed_counts) if allowed_counts else None

        # Bytes consumed for the frame currently being assembled, replayed on resync
        self._frame_bytes = bytearray()
        self._inbox = deque()
        self.stats = {
            "frames_ok": 0,
            "crc_errors": 0,
            "bad_header": 0,
            "resyncs": 0,
        }

    def reset(self):
        self._inbox.clear()
        self._reset_frame_state()

    def _reset_frame_state(self):
        self.state = self.ST_WAIT_START
        self.hdr_index = 0
        self.payload_index = 0
        self.expected_payload_len = 0
        self.payload = bytearray()
        self._frame_bytes = bytearray()

    def _resync(self):
        """Replay the discarded bytes so a start byte hidden inside them is not lost."""
        self.stats["resyncs"] += 1
        pending = bytes(self._frame_bytes[1:])
        self._reset_frame_state()
        self._inbox.extendleft(reversed(pending))

    """Parse payload bytes into floats."""
    def parse_floats(self, payload: bytes):
        count = len(payload) // 4
        return struct.unpack("<" + "f" * count, payload[:count * 4])

    """Feed one byte into the state machine.
           Returns a tuple (header, payload) when a frame is complete,
           or None if still waiting for a full frame.
           Args: b: byte to process
           Returns: (header: bytes, payload: bytes) or None
        """
    def process_byte(self, b: int):
        self._inbox.append(b)
        while self._inbox:
            frame = self._feed(self._inbox.popleft())
            if frame is not None:
                return frame
        return None

    def _feed(self, b: int):
        if self.state != self.ST_WAIT_START:
            self._frame_bytes.append(b)

        if self.state == self.ST_WAIT_START:
            if b == START_BYTE:
                self.state = self.ST_READ_HEADER
                self.hdr_index = 0
                self._frame_bytes = bytearray([b])
            return None

        elif self.state == self.ST_READ_HEADER:
            self.header[self.hdr_index] = b
            self.hdr_index += 1

            if self.hdr_index == 4:
                # Header-validation: Check if MessageType (Index 1) is valid
                if self.header[1] not in VALID_TYPES:
                    # Invalid header → Resync
                    self.stats["bad_header"] += 1
                    self._resync()
                    return None
                
                # Check protocol version
                received_version = (self.header[0] >> 4) & 0x0F
                if received_version != PROTOCOL_VERSION:
                    if self.last_logged_version != received_version:
                        self.last_logged_version = received_version
                        logger.warning(
                            f"Protocol version mismatch: expected {PROTOCOL_VERSION}, "
                            f"got {received_version}"
                        )
                    self.stats["bad_header"] += 1
                    self._resync()
                    return None
                
                count = self.header[2]

                if self.allowed_counts is not None:
                    plausible = count in self.allowed_counts
                else:
                    plausible = 0 < count <= MAX_FLOAT_COUNT
                if not plausible:
                    self.stats["bad_header"] += 1
                    self._resync()
                    return None

                self.expected_payload_len = count * 4
                self.payload = bytearray(self.expected_payload_len)
                self.payload_index = 0
                self.state = self.ST_READ_PAYLOAD
            return None

        elif self.state == self.ST_READ_PAYLOAD:
            self.payload[self.payload_index] = b
            self.payload_index += 1

            if self.payload_index == self.expected_payload_len:
                self.crc_buf = bytearray(2)
                self.payload_index = 0
                self.state = self.ST_READ_CRC
            return None

        elif self.state == self.ST_READ_CRC:
            self.crc_buf[self.payload_index] = b
            self.payload_index += 1

            if self.payload_index == 2:
                received_crc = self.crc_buf[0] | (self.crc_buf[1] << 8)

                calc_crc = crc16_ccitt(self.header + self.payload)

                if calc_crc == received_crc:
                    # Valid frame
                    header_obj = FrameHeader(self.header)
                    frame = (header_obj, bytes(self.payload))
                    self.stats["frames_ok"] += 1
                    self._reset_frame_state()
                    return frame
                else:
                    # CRC error → resync
                    self.stats["crc_errors"] += 1
                    logger.warning(
                        f"CRC mismatch: calculated 0x{calc_crc:04X}, "
                        f"received 0x{received_crc:04X}"
                    )
                    
                    # Log failed packet if error logger is enabled
                    if self.error_logger:
                        header_obj = FrameHeader(self.header)
                        self.error_logger.log_crc_error(
                            header=bytes(self.header),
                            payload=bytes(self.payload),
                            received_crc=received_crc,
                            calculated_crc=calc_crc,
                            message_type=header_obj.message_type,
                            message_counter=header_obj.counter
                        )
                    
                    self._resync()
                    return None

        return None
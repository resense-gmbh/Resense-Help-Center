"""
Error Packet Logger
Logs failed communication packets (e.g., CRC errors) with raw data for debugging.
"""

import json
import os
import threading
from datetime import datetime
from typing import Optional


class ErrorPacketLogger:
    """
    Logs failed communication packets to JSON files with automatic rotation.
    
    Thread-safe implementation for use in multi-threaded communication scenarios.
    """
    
    def __init__(
        self, 
        log_directory: str = "error_logs",
        max_size_mb: float = 5.0,
        max_backups: int = 3
    ):
        """
        Initialize the error packet logger.
        
        Args:
            log_directory: Directory to store error log files
            max_size_mb: Maximum size of log file in MB before rotation
            max_backups: Number of backup files to keep during rotation
        """
        self.log_directory = log_directory
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.max_backups = max_backups
        self.lock = threading.Lock()
        self.log_file_path: Optional[str] = None
        self.current_session_start = None
        
        # Create log directory if it doesn't exist
        os.makedirs(self.log_directory, exist_ok=True)
        
        # Initialize session log file
        self._start_new_session()
    
    def _start_new_session(self):
        """Start a new logging session with timestamped filename."""
        self.current_session_start = datetime.now()
        timestamp = self.current_session_start.strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file_path = os.path.join(
            self.log_directory, 
            f"error_log_{timestamp}.json"
        )
        
        # Create initial log file with metadata
        with open(self.log_file_path, 'w', encoding='utf-8') as f:
            json.dump({
                "session_start": self.current_session_start.isoformat(),
                "errors": []
            }, f, indent=2)
    
    def _rotate_log(self):
        """Rotate log file when size limit is reached."""
        if not self.log_file_path or not os.path.exists(self.log_file_path):
            return
        
        # Shift existing backups
        for i in range(self.max_backups - 1, 0, -1):
            old_backup = f"{self.log_file_path}.{i}"
            new_backup = f"{self.log_file_path}.{i + 1}"
            if os.path.exists(old_backup):
                if i + 1 <= self.max_backups:
                    os.replace(old_backup, new_backup)
                else:
                    os.remove(old_backup)
        
        # Create first backup from current file
        if os.path.exists(self.log_file_path):
            os.replace(self.log_file_path, f"{self.log_file_path}.1")
        
        # Start new session
        self._start_new_session()
    
    def _check_rotation_needed(self):
        """Check if log rotation is needed based on file size."""
        if self.log_file_path and os.path.exists(self.log_file_path):
            file_size = os.path.getsize(self.log_file_path)
            if file_size >= self.max_size_bytes:
                self._rotate_log()
    
    def log_crc_error(
        self,
        header: bytes,
        payload: bytes,
        received_crc: int,
        calculated_crc: int,
        message_type: Optional[int] = None,
        message_counter: Optional[int] = None
    ):
        """
        Log a CRC error with full packet details.
        
        Args:
            header: Raw header bytes
            payload: Raw payload bytes
            received_crc: CRC value received in packet
            calculated_crc: CRC value calculated from data
            message_type: Optional message type from header
            message_counter: Optional message counter from header
        """
        with self.lock:
            try:
                # Check if rotation is needed
                self._check_rotation_needed()
                
                # Create error entry
                error_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "error_type": "CRC_MISMATCH",
                    "header_hex": header.hex(),
                    "payload_hex": payload.hex(),
                    "received_crc": f"0x{received_crc:04X}",
                    "calculated_crc": f"0x{calculated_crc:04X}",
                    "packet_length": len(header) + len(payload) + 2,
                }
                
                # Add optional metadata
                if message_type is not None:
                    error_entry["message_type"] = message_type
                if message_counter is not None:
                    error_entry["message_counter"] = message_counter
                
                # Read current log file
                with open(self.log_file_path, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
                
                # Append new error
                log_data["errors"].append(error_entry)
                
                # Write back to file
                with open(self.log_file_path, 'w', encoding='utf-8') as f:
                    json.dump(log_data, f, indent=2)
                    
            except Exception as e:
                # Avoid breaking the main application if logging fails
                print(f"Error logging failed packet: {e}")
    
    def get_error_count(self) -> int:
        """
        Get the number of errors logged in the current session.
        
        Returns:
            Number of errors in current session
        """
        with self.lock:
            try:
                if not self.log_file_path or not os.path.exists(self.log_file_path):
                    return 0
                
                with open(self.log_file_path, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
                    return len(log_data.get("errors", []))
            except Exception:
                return 0
    
    def close(self):
        """Close the logger and finalize the current session."""
        with self.lock:
            if self.log_file_path and os.path.exists(self.log_file_path):
                try:
                    # Update session metadata
                    with open(self.log_file_path, 'r', encoding='utf-8') as f:
                        log_data = json.load(f)
                    
                    log_data["session_end"] = datetime.now().isoformat()
                    log_data["total_errors"] = len(log_data.get("errors", []))
                    
                    with open(self.log_file_path, 'w', encoding='utf-8') as f:
                        json.dump(log_data, f, indent=2)
                except Exception as e:
                    print(f"Error finalizing log session: {e}")

import tkinter as tk
import time
import queue
import threading

exit_requested = False

class SensorDisplay:
    def __init__(self, root, data_queue, freq_queue=None, dark_mode=True):
        """Initialize the sensor display."""
        self.root = root
        self.data_queue = data_queue
        self.freq_queue = freq_queue
        self.dark_mode = dark_mode
        
        # Create a buffer queue for processed data
        self.display_buffer = queue.Queue(maxsize=500)
        
        # Flag to control the processor thread
        self.processor_running = True
        
        # Start the queue processor thread
        self.processor_thread = threading.Thread(
            target=self.queue_processor,
            daemon=True
        )
        self.processor_thread.start()
        
        # Set up the UI
        self.setup_ui(dark_mode)
        
        # Start the display update cycle
        self.update_display()
        
    def setup_ui(self, dark_mode=True):
        """
        Set up the user interface.
        
        Args:
            dark_mode (bool): Whether to use dark mode theme (default: True)
        """
        # Set colors based on theme
        if dark_mode:
            bg_color = "black"
            text_color = "#00FF00"  # Bright green
            highlight_color = "#005500"  # Dark green for highlights/selections
            timestamp_color = "#AAFFAA"  # Light green for timestamps
            error_color = "#FF5555"  # Red for errors
        else:
            bg_color = "white"
            text_color = "#006600"  # Dark green
            highlight_color = "#CCFFCC"  # Light green for highlights
            timestamp_color = "#008800"  # Medium green for timestamps
            error_color = "#CC0000"  # Dark red for errors
        
        # Store theme colors for later reference
        self.theme_colors = {
            "bg": bg_color,
            "text": text_color,
            "highlight": highlight_color,
            "timestamp": timestamp_color,
            "error": error_color
        }
        
        # Configure the root window with theme
        self.root.title("Sensor Data Display")
        self.root.geometry("1600x400")
        self.root.configure(bg=bg_color)
        
        # Configure the main frame
        self.frame = tk.Frame(self.root, padx=10, pady=10, bg=bg_color)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Create a status bar frame
        status_frame = tk.Frame(self.frame, bg=bg_color)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        # Add frequency label on the left of status frame
        self.freq_label = tk.Label(
            status_frame, 
            text="Data Rate: 0 Hz", 
            font=("Courier", 12),
            bg=bg_color,
            fg=timestamp_color,
            anchor=tk.W
        )
        self.freq_label.pack(side=tk.LEFT, padx=(0, 20))

       # Status label on the right of status frame
        self.status_label = tk.Label(
            status_frame,  # Changed from self.frame to status_frame
            text="Waiting for data...", 
            font=("Courier", 12),
            bg=bg_color,
            fg=text_color
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Data display in its own row
        self.data_text = tk.Text(
            self.frame, 
            height=15, 
            width=80, 
            font=("Courier", 12),
            bg=bg_color,
            fg=text_color,
            # ... rest of your configuration
        )
        self.data_text.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbar with theme styling
        scrollbar = tk.Scrollbar(
            self.data_text,
            bg=bg_color,
            troughcolor=bg_color,
            activebackground=highlight_color
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.data_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.data_text.yview)
        
        # Add some initial text with timestamp
        current_time = time.strftime('%H:%M:%S')
        self.data_text.insert(tk.END, f"Sensor Data Display - {current_time}\n")
        self.data_text.insert(tk.END, "=================================\n\n")
        self.data_text.insert(tk.END, "Waiting for data from the main program...\n\n")
        
        # Create a tag for timestamps with a different color
        self.data_text.tag_configure("timestamp", foreground=timestamp_color)
        
        # Create a tag for error messages
        self.data_text.tag_configure("error", foreground=error_color)
        
        # Store current theme state
        self.dark_mode = dark_mode

   
    def queue_processor(self):
        """Process queue items in a separate thread."""
        while self.processor_running:
            try:
                # Process items from the data queue
                items_processed = 0
                max_batch = 1000  # Process up to 1000 items per batch
                
                while not self.data_queue.empty() and items_processed < max_batch:
                    # Get data from the main queue
                    data = self.data_queue.get_nowait()
                    items_processed += 1
                    
                    # Process based on data type
                    if data.get("type") == "status":
                        # Status updates go directly to the buffer
                        self.display_buffer.put(data)
                    elif data.get("type") == "data":
                        # Format the data with timestamp
                        timestamp = time.strftime('%H:%M:%S')
                        processed_data = {
                            "type": "formatted_data",
                            "timestamp": timestamp,
                            "message": data["message"]
                        }
                        # Try to add to buffer, don't block if full
                        try:
                            self.display_buffer.put_nowait(processed_data)
                        except queue.Full:
                            # Buffer is full, skip this item
                            pass
                
                # If queue is severely backed up, log a warning
                if self.data_queue.qsize() > 5000:
                    print(f"Warning: Queue backlog of {self.data_queue.qsize()} items")
                
                # Small sleep to prevent CPU hogging
                time.sleep(0.005)
            except Exception as e:
                print(f"Error in queue processor: {e}")
                time.sleep(0.1)  # Sleep longer on error
    def update_display(self):
        """Update the UI with data from the display buffer."""
        try:
            # Process the display buffer (this runs in the main UI thread)
            items_processed = 0
            max_display_items = 50  # Process up to 50 items per UI update
            
            while not self.display_buffer.empty() and items_processed < max_display_items:
                data = self.display_buffer.get_nowait()
                items_processed += 1
                
                if data.get("type") == "status" and hasattr(self, 'status_label') and self.status_label.winfo_exists():
                    self.status_label.config(text=data["message"])
                    
                elif data.get("type") == "formatted_data" and hasattr(self, 'data_text') and self.data_text.winfo_exists():
                    # Insert timestamp with its special tag
                    self.data_text.insert(tk.END, f"{data['timestamp']}: ", "timestamp")
                    
                    # Insert the actual data with default color
                    self.data_text.insert(tk.END, f"{data['message']}\n")
                    
                    # Auto-scroll to the bottom
                    self.data_text.see(tk.END)
                    
                    # Line limiting logic
                    current_lines = int(float(self.data_text.index('end-1c').split('.')[0]))
                    if current_lines > 100:
                        lines_to_delete = current_lines - 90
                        self.data_text.delete('1.0', f'{lines_to_delete}.0')
            
            # Process frequency queue
            if self.freq_queue and hasattr(self, 'freq_label') and self.freq_label.winfo_exists():
                try:
                    # Process frequency updates
                    frequency_updates = []
                    for _ in range(5):
                        if self.freq_queue.empty():
                            break
                        frequency_updates.append(self.freq_queue.get_nowait())
                    
                    # Only apply the most recent update
                    if frequency_updates:
                        most_recent = frequency_updates[-1]
                        if "frequency" in most_recent:
                            self.freq_label.config(text=f"Data Rate: {most_recent['frequency']:.1f} Hz")
                except Exception as freq_e:
                    print(f"Error processing frequency update: {freq_e}")
        
        except Exception as e:
            print(f"Error in update_display: {e}")
        
        # Schedule the next update
        if hasattr(self, 'root') and self.root.winfo_exists():
            self.root.after(50, self.update_display)  # Update every 50ms
        else:
            print("Root window no longer exists, stopping update cycle")
            self.processor_running = False  # Stop the processor thread
    
    def cleanup(self):
        """Clean up resources when closing."""
        self.processor_running = False
        if hasattr(self, 'processor_thread') and self.processor_thread.is_alive():
            self.processor_thread.join(timeout=1.0)



def start_display(data_queue, freq_queue=None, dark_mode=True):
    """
    Start the sensor data display window.
    
    Args:
        data_queue: Queue for receiving data to display
        freq_queue: Queue for frequency updates (optional)
        dark_mode (bool): Whether to use dark mode theme (default: True)
    """
    def on_closing():
        """Handle window close event"""
        print("Window closing, cleaning up...")
        root.destroy()

    def check_exit(root):
        global exit_requested
        if exit_requested:
            root.quit()
            return
        root.after(100, check_exit, root)  # Check every 100ms

    try:
        root = tk.Tk()
        root.createcommand('exit', root.destroy)  # Allow exit() to work

        root.protocol("WM_DELETE_WINDOW", on_closing)
        root.after(100, check_exit, root)
        app = SensorDisplay(root, data_queue, freq_queue, dark_mode)
        print("Display initialized, starting main loop")
        root.mainloop()
        print("Main loop ended")
    except Exception as e:
        print(f"Error in display: {e}")

if __name__ == "__main__":
    print("This script should be imported by comm_modul.py, not run directly.")
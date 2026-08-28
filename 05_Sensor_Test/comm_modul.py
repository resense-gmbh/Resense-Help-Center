import signal
import time
import src.sensor_display as sensor_display
import sys
from src.sensor_communicator import SensorCommunicator
from src.command_handler import handle_command, get_commands
import src.protocol_definition as protocol
import logging


class _LevelFormatter(logging.Formatter):
    """Plain text for INFO, timestamped and level-tagged for WARNING and above."""

    PLAIN = logging.Formatter('%(message)s')
    DETAILED = logging.Formatter(
        '[%(levelname)s] %(asctime)s %(name)s - %(message)s', datefmt='%H:%M:%S'
    )

    def format(self, record):
        if record.levelno >= logging.WARNING:
            return self.DETAILED.format(record)
        return self.PLAIN.format(record)


_console = logging.StreamHandler(sys.stdout)
_console.setFormatter(_LevelFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_console], force=True)
# Global flag for controlled shutdown
exit_requested = False
sensor = None
logger = logging.getLogger(__name__)

def signal_handler(sig, frame):
    """Signal handler for clean termination with Ctrl+C"""
    global exit_requested
    global sensor
    logger.error("\nProgram interrupted. Shutting down...")
    exit_requested = True
    sensor_display.exit_requested = True
    
    # Close sensor connection
    if 'sensor' in globals() and sensor is not None:
        sensor.disconnect()
    
    # Force exit if needed
    sys.exit(0)

def main():
    global exit_requested

    # Register the signal handler
    signal.signal(signal.SIGINT, signal_handler)  # CTRL+C
    signal.signal(signal.SIGTERM, signal_handler)  # termination request 
    
    logger.info("Sensor Communication Module")
    logger.info("==========================")

   

    # Show initial help by displaying all available commands
    logger.info("\nAvailable commands:")

    # Import the commands dictionary from command_handlers
    commands = get_commands()
    
    for cmd, desc in commands.items():
        logger.info(f"  {cmd:12} - {desc}")
    

    time.sleep(0.5)  # Small delay before starting command loop

     # Create the sensor communicator
    sensor = SensorCommunicator()
    logger.info("\nConnecting to sensor in protocol mode {}...".format(sensor.protocol_mode))
    sensor.connect()
    sensor.start_continuous_display()
    # Main command loop
    while not exit_requested:
        try:
            command = input("\n> ").strip().lower()
            
            # Handle command using the function from command_handlers.py
            should_exit = handle_command(command, sensor)
            if should_exit:
                break
                
        except KeyboardInterrupt:
            logger.info("\nOperation interrupted")
            break
        except Exception as e:
            logger.error(f"Error: {e}")

    # Cleanup before exit
    if 'sensor' in globals():
        sensor.disconnect()
    logger.info("Program exited")

if __name__ == "__main__":
    main()
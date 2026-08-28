import pandas as pd
import datetime
import os

class DataLogger:
    def __init__(self, base_directory=None):
        """
        Initialize the DataLogger.
        
        Args:
            base_directory: Directory for storing CSV files (default: current directory)
        """
        self.data_buffer = []  # Buffer for new data points
        self.sample_count = 0  # Counter for total samples collected
        self.total_saved = 0   # Counter for samples already saved to file
        self.start_time = datetime.datetime.now()
        
        # Set directory for data storage
        self.base_directory = base_directory if base_directory else os.getcwd()
        
        # Filename, schema and columns are established with the first sample
        self.filename = None
        self.schema = None
        self.columns = None
    
    def _new_filename(self, suffix=""):
        stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        return os.path.join(self.base_directory, f"data_{stamp}{suffix}.csv")

    def _create_csv_file(self):
        """
        Create the CSV file with a schema marker line followed by the header.
        """
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.write(f"# schema_id={self.schema.id}\n")
        pd.DataFrame(columns=self.columns).to_csv(self.filename, index=True, mode='a')
        print(f"CSV file created: {self.filename}")
    
    def _start_file_for(self, schema):
        """Begin a new CSV file whose columns are derived from the given schema."""
        if self.schema is not None:
            self.save_data()
        suffix = "" if self.schema is None else f"_{schema.id}"
        self.schema = schema
        self.columns = ['timestamp'] + list(schema.csv_columns())
        self.filename = self._new_filename(suffix)
        self._create_csv_file()

    def add_sample(self, sample, offsets=None) -> int:
        """
        Add a decoded sensor sample to the buffer.
        
        Args:
            sample: SensorSample carrying both the values and their schema
            offsets: Optional sequence of per-channel offsets to subtract
            
        Returns:
            int: Updated total sample count
        """
        if self.schema is None or sample.schema.id != self.schema.id:
            self._start_file_for(sample.schema)

        values = list(sample.values)
        if offsets is not None:
            for index in sample.schema.tarable_indices():
                values[index] -= offsets[index]

        row = [values[i] for i in sample.schema.csv_value_indices()]
        self.data_buffer.append([sample.timestamp] + row)
        self.sample_count += 1
        return self.sample_count
    
    def save_data(self):
        """
        Saves the collected data in the CSV file in append mode.
        
        Returns:
            str: Filename of the saved file, or None if buffer was empty
        """
        if len(self.data_buffer) > 0:
            # Create DataFrame from buffer
            df_buffer = pd.DataFrame(self.data_buffer, columns=self.columns)
            
            # Save in append mode, without repeating the header
            with open(self.filename, 'a') as f:
                df_buffer.to_csv(f, header=False, index=True)
            
            # Update counters
            self.total_saved += len(self.data_buffer)
            # buffer_count = len(self.data_buffer)
            
            # Clear buffer
            self.data_buffer = []
            
            # print(f"\nIntermediate save: {buffer_count} new samples (Total: {self.total_saved})")
            return self.filename
        return None
    
    def get_filename(self):
        """
        Get the current CSV filename.
        
        Returns:
            str: Full path to the CSV file
        """
        return self.filename
    
    def load_data_for_plot(self):
        """
        Load the data for plotting.
        
        Returns:
            pandas.DataFrame: The loaded data, or None if file doesn't exist
        """
        if self.filename and os.path.exists(self.filename):
            return pd.read_csv(self.filename, index_col=0, comment='#')
        return None
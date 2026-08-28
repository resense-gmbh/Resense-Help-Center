import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
import glob
import numpy as np

from src.channel_schema import ROLE_FORCE, ROLE_TORQUE
from src.schema_registry import SchemaRegistry

SCHEMA_MARKER = "# schema_id="


class DataPlotter:
    def __init__(self, directory=None):
        """
        Initialize the DataPlotter with an optional directory.
        
        Args:
            directory (str): Directory containing CSV files
        """
        self.directory = directory
        self.csv_files = []
        self.selected_file = None
        self.df = None
        self.schema = None
    
    def format_file_size(self, size_bytes):
        """
        Format file size to a readable format (KB, MB, GB).
        
        Args:
            size_bytes (int): Size in bytes
            
        Returns:
            str: Formatted size string
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    def get_file_details(self, file_path):
        """
        Get file size and creation date.
        
        Args:
            file_path (str): Path to the file
            
        Returns:
            tuple: (size, created_date)
        """
        try:
            file_stats = os.stat(file_path)
            size = self.format_file_size(file_stats.st_size)
            created = pd.to_datetime(file_stats.st_ctime, unit='s').strftime('%Y-%m-%d %H:%M:%S')
            return size, created
        except Exception as e:
            return "Error", "Error"
    
    def find_csv_files(self, directory=None):
        """
        Find all CSV files in the specified directory.
        
        Args:
            directory (str): Directory to search in
            
        Returns:
            list: List of CSV file paths
        """
        if directory:
            self.directory = directory
        
        if not self.directory:
            raise ValueError("No directory specified")
        
        self.csv_files = glob.glob(os.path.join(self.directory, '*.csv'))
        return self.csv_files
    
    def display_available_files(self):
        """
        Display all available CSV files with details.
        
        Returns:
            bool: True if files were found, False otherwise
        """
        if not self.csv_files:
            if not self.directory:
                print("No directory specified.")
                return False
            
            self.find_csv_files()
            
            if not self.csv_files:
                print(f"No CSV files found in directory {self.directory}.")
                return False
        
        print("Available CSV files:")
        print(f"{'No':>3} | {'Filename':<40} | {'Size':>10} | {'Created on':<19}")
        print("-" * 80)
        
        for i, file in enumerate(self.csv_files, 1):
            # Show only filename without path
            filename = os.path.basename(file)
            size, created = self.get_file_details(file)
            print(f"{i:3d} | {filename:<40} | {size:>10} | {created:<19}")
        
        return True
    

    def _find_matrix_file(self):
        """
        Find calibration matrix file in data directory or its parent/subdirectories.
        
        Returns:
            str: Path to matrix file or None if not found
        """
        # Start with the directory of the current data file
        search_dirs = []
        working_dir = os.getcwd()
        search_dirs.append(working_dir)
        

        # Check 'data' subfolder if it exists
        data_subfolder = os.path.join(working_dir, "data")
        if os.path.exists(data_subfolder):
            search_dirs.append(data_subfolder)
            
        # Check 'calibration' subfolder if it exists
        cal_subfolder = os.path.join(working_dir, "calibration")
        if os.path.exists(cal_subfolder):
            search_dirs.append(cal_subfolder)
        
            
        
        # Common matrix file patterns
        patterns = ["Matrix*.txt", "matrix*.txt", "*.matrix", "calibration*.txt"]
        
        # Search for matrix files
        for directory in search_dirs:
            for pattern in patterns:
                matrix_path = os.path.join(directory, pattern)
                matrix_files = glob.glob(matrix_path)
                
                if matrix_files:
                    print(f"Found matrix file: {matrix_files[0]}")
                    return matrix_files[0]
        
        print("No matrix file found in search directories.")
        return None
    def select_file(self, selection=None):
        """
        Select a file by index or prompt user for selection.
        
        Args:
            selection (int): File index to select
            
        Returns:
            str: Selected file path
        """
        if not self.csv_files:
            if not self.display_available_files():
                return None
        
        if selection is None:
            try:
                selection = int(input("\nSelect a file (enter number): "))
                if selection < 1 or selection > len(self.csv_files):
                    print("Invalid selection.")
                    return None
            except ValueError:
                print("Please enter a number.")
                return None
        
        self.selected_file = self.csv_files[selection - 1]
        filename = os.path.basename(self.selected_file)
        size, created = self.get_file_details(self.selected_file)
        print(f"\nLoading file: {filename} ({size}, created on {created})")
        
        return self.selected_file
    
    def _read_schema_marker(self, file_path):
        """Read the schema id written into the CSV header, if the file carries one."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
        except OSError:
            return None

        if not first_line.startswith(SCHEMA_MARKER):
            return None

        schema_id = first_line[len(SCHEMA_MARKER):].strip()
        try:
            return SchemaRegistry.from_file().by_id(schema_id)
        except Exception as e:
            print(f"Schema '{schema_id}' referenced by the CSV could not be loaded: {e}")
            return None

    def _columns_for_roles(self, *roles):
        """Columns of the given roles, restricted to those actually present in the data."""
        if self.schema is None:
            return None
        columns = [c for c in self.schema.columns_by_role(*roles) if c in self.df.columns]
        return columns or None

    def load_data(self, file_path=None):
        """
        Load data from the selected file or specified file path.
        
        Args:
            file_path (str): Path to the file to load
            
        Returns:
            pandas.DataFrame: Loaded data
        """
        if file_path:
            self.selected_file = file_path
        
        if not self.selected_file:
            print("No file selected.")
            return None
        
        try:
            self.schema = self._read_schema_marker(self.selected_file)
            self.df = pd.read_csv(self.selected_file, comment='#')
            if self.schema:
                print(f"Schema: {self.schema}")
            print(f"File loaded: {len(self.df)} rows, {len(self.df.columns)} columns")
            return self.df
        except Exception as e:
            import traceback
            print("Error loading file:")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print("\nDetailed traceback:")
            traceback.print_exc()
            return None
    
    def identify_columns(self):
        """
        Identify temperature and timestamp columns.
        
        Returns:
            tuple: (temperature_column, timestamp_column)
        """
        if self.df is None:
            print("No data loaded.")
            return None, None
        
        # Display column headers
        print("\nAvailable columns:")
        for i, col in enumerate(self.df.columns):
            print(f"{i:2d}: {col}")
        
        # Identify temperature column
        temp_column = None
        for col in self.df.columns:
            if 'temp' in col.lower() or 'temperature' in col.lower():
                temp_column = col
                break
        
        if temp_column is None:
            # If no temperature column found, assume it's column 7
            try:
                temp_column = self.df.columns[8]  # 8 because first column is often index
                print(f"\nNo clear temperature column found. Using: {temp_column}")
            except IndexError:
                print("\nNo suitable temperature column found.")
                return None, None
        else:
            print(f"\nTemperature column found: {temp_column}")
        
        # Identify timestamp column
        timestamp_column = None
        for col in self.df.columns:
            if 'time' in col.lower() or 'date' in col.lower() or 'timestamp' in col.lower():
                timestamp_column = col
                break
        
        return temp_column, timestamp_column
    
    # create a function to plot the force data
    def plot_force(self, force_columns=None, moment_columns=None, timestamp_column=None, 
               show_stats=True, offset_step=200, use_matrix=False):
        """
        Plot force data with channels separated by vertical offsets.
        
        Args:
            force_columns (list): List of force column names (e.g., ['fx', 'fy', 'fz'])
            moment_columns (list): List of moment column names (e.g., ['mx', 'my', 'mz'])
            timestamp_column (str): Name of timestamp column
            show_stats (bool): Whether to show force statistics
            offset_step (int): Vertical offset between force channels
            use_matrix (bool): Toggle using the calibration matrix
            
        Returns:
            matplotlib.figure.Figure: The plot figure
        """
        # Check if data is loaded
        if self.df is None:
            print("No data loaded.")
            return None
        
        # Identify columns if not specified
        if force_columns is None:
            force_columns = self._identify_force_columns()
        
        if moment_columns is None:
            moment_columns = self._identify_moment_columns()
        
        # Validate force columns exist in the DataFrame
        missing_columns = [col for col in force_columns if col not in self.df.columns]
        if missing_columns:
            print(f"Error: Force column(s) {', '.join(missing_columns)} not found in data.")
            print(f"Available columns: {', '.join(self.df.columns)}")
            return None
        
        # Validate moment columns if provided
        if moment_columns:
            missing_moment_cols = [col for col in moment_columns if col not in self.df.columns]
            if missing_moment_cols:
                print(f"Warning: Moment column(s) {', '.join(missing_moment_cols)} not found in data.")
                # Remove missing columns
                moment_columns = [col for col in moment_columns if col in self.df.columns]
        
        # Validate timestamp column if provided
        if timestamp_column and timestamp_column not in self.df.columns:
            print(f"Error: Column '{timestamp_column}' not found in data.")
            print(f"Available columns: {', '.join(self.df.columns)}")
            timestamp_column = None
        
        # Try to load matrix file if specified or look for default matrix file
        matrix = self._load_calibration_matrix() if use_matrix else None
        
        # Apply matrix calibration if available
        if matrix is not None:
            self._apply_calibration_matrix(matrix, force_columns, moment_columns)
        
        # Create and configure figure
        fig = plt.figure(figsize=(14, 8))
        
        # Define colors for force channels
        colors = {
            'fx': '#1f77b4',  # Blue
            'fy': '#ff7f0e',  # Orange
            'fz': '#2ca02c',  # Green
        }
        
        # Plot force data with offsets
        self._plot_force_data(force_columns, timestamp_column, colors, offset_step)
        
        # Add statistics if requested
        if show_stats:
            self._add_force_statistics(force_columns)
        
        # Finalize plot
        plt.ylabel(f"Force (mN) + Offset {offset_step}")
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        # Display plot
        plt.ion()  # Turn on interactive mode
        plt.draw()
        plt.pause(0.001)  # Pause to render the plot
        input("Press Enter to exit...")
        
        return fig
    
    def _identify_moment_columns(self):
        """Helper method to identify moment columns"""
        schema_columns = self._columns_for_roles(ROLE_TORQUE)
        if schema_columns:
            return schema_columns

        moment_columns = []
        
        # Look for columns with 'm' or 'moment' in the name
        for col in self.df.columns:
            col_lower = col.lower()
            if 'mx' in col_lower or 'my' in col_lower or 'mz' in col_lower or 'moment' in col_lower:
                moment_columns.append(col)
        
        return moment_columns

    def _load_calibration_matrix(self, matrix_file=None):
        """
        Load calibration matrix from file
        
        Args:
            matrix_file (str): Path to matrix file, if None will look in data folder
            
        Returns:
            np.ndarray: Calibration matrix or None if not found
        """
        # If matrix file not specified, look for default matrix file
        if matrix_file is None:
            matrix_file = self._find_matrix_file()
            
            if not matrix_file:
                print("No matrix file found.")
                return None
        
        # Load the matrix file
        try:
            print(f"Loading calibration matrix from: {matrix_file}")
            matrix_data = np.loadtxt(matrix_file, delimiter=',')
            
            # Check if the matrix has the expected shape (typically 6x6)
            if matrix_data.shape != (6, 6):
                print(f"Warning: Matrix has unexpected shape {matrix_data.shape}, expected (6, 6).")
            
            return matrix_data
        except Exception as e:
            print(f"Error loading matrix file: {e}")
            return None

    def _apply_calibration_matrix(self, matrix, force_columns, moment_columns):
        """
        Apply calibration matrix to force and moment data
        
        Args:
            matrix (np.ndarray): Calibration matrix
            force_columns (list): List of force column names
            moment_columns (list): List of moment column names
        """
        # We need 6 columns (3 forces + 3 moments) to apply the 6x6 matrix
        if len(force_columns) + len(moment_columns) != 6:
            print(f"Warning: Need exactly 6 columns to apply 6x6 matrix, but got {len(force_columns)} force columns and {len(moment_columns)} moment columns.")
            return
        
        # Combine force and moment columns in the expected order
        # Typically: [Fx, Fy, Fz, Mx, My, Mz]
        all_columns = force_columns + moment_columns
        
        # Create a copy of the original data for the combined columns
        original_data = np.zeros((len(self.df), len(all_columns)))
        for i, col in enumerate(all_columns):
            original_data[:, i] = self.df[col].values
        
        # Apply the calibration matrix to each row
        calibrated_data = np.matmul(original_data, matrix.T)
        
        # Update the DataFrame with calibrated values
        for i, col in enumerate(all_columns):
            # Create a new column with '_cal' suffix for the calibrated data
            cal_col = f"{col}_cal"
            self.df[cal_col] = calibrated_data[:, i]
            
            # Replace the original column names in the force_columns and moment_columns lists
            if col in force_columns:
                idx = force_columns.index(col)
                force_columns[idx] = cal_col
            elif col in moment_columns:
                idx = moment_columns.index(col)
                moment_columns[idx] = cal_col

    def _identify_force_columns(self):
        """Helper method to identify force columns"""
        schema_columns = self._columns_for_roles(ROLE_FORCE)
        if schema_columns:
            return schema_columns

        force_columns = []
        
        # Look for columns with 'f' or 'force' in the name
        for col in self.df.columns:
            col_lower = col.lower()
            if 'fx' in col_lower or 'fy' in col_lower or 'fz' in col_lower or 'force' in col_lower:
                force_columns.append(col)
        
        # If no force columns found, look for columns that might contain force data
        if not force_columns:
            # Check if we have columns that might be force data (often first few numeric columns)
            numeric_cols = [col for col in self.df.columns if pd.api.types.is_numeric_dtype(self.df[col])]
            if len(numeric_cols) >= 3:
                # Assume first three numeric columns are force data
                force_columns = numeric_cols[:3]
                print(f"No clear force columns found. Using: {force_columns}")
        
        return force_columns

    def _plot_force_data(self, force_columns, timestamp_column, colors, offset_step):
        """Helper method to plot force data with offsets"""
        # Use sample numbers for x-axis by default
        x_values = np.arange(1, len(self.df) + 1)
        x_label = 'Sample Number'
        
        # Use timestamp if available
        if timestamp_column is not None:
            try:
                # Convert timestamps if they're strings
                if not pd.api.types.is_datetime64_any_dtype(self.df[timestamp_column]):
                    self.df[timestamp_column] = pd.to_datetime(self.df[timestamp_column])
                
                x_values = self.df[timestamp_column]
                x_label = 'Time'
                
                # Format x-axis time display if it's datetime
                plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
                plt.gcf().autofmt_xdate()  # Rotate date labels
            except Exception as e:
                print(f"Error converting timestamps: {e}")
                # Fall back to sample numbers
        
        # Plot each force channel with offset
        legend_entries = []
        offsets = {}

        # Variables to track global min and max values (including offsets)
        global_min = float('inf')
        global_max = float('-inf')
        
        for i, col in enumerate(force_columns):
            offset = i * offset_step
            offsets[col] = offset
            
            # Get color, default to a color from the cycle if not in our predefined colors
            color = colors.get(col.lower(), f'C{i}')
            
            # Calculate min and max values for this channel (with offset)
            channel_min = self.df[col].min() + offset
            channel_max = self.df[col].max() + offset
            
            # Update global min and max
            global_min = min(global_min, channel_min)
            global_max = max(global_max, channel_max)

            # Plot the data with offset
            line, = plt.plot(x_values, self.df[col] + offset, color=color, 
                            linewidth=1.8, label=f'{col}')
            legend_entries.append(line)
            
            # Add reference line at offset
            plt.axhline(y=offset, color='gray', linestyle='--', alpha=0.3)
            
            # Add text label for the channel
            plt.text(len(self.df) * 1.01, offset, col, fontsize=12, 
                    color=color, fontweight='bold')
        
        # Set plot styling
        plt.xlabel(x_label)
        plt.title('Force Channels')
        plt.legend(handles=legend_entries, fontsize=10, loc='upper right', framealpha=0.9)
        
        
        # Set y-limits based on data min/max with some padding (10% of the range)
        y_range = global_max - global_min
        padding = y_range * 0.1  # 10% padding
        plt.ylim(global_min - padding, global_max + padding)


        # max_offset = (len(force_columns) - 1) * offset_step
        # plt.ylim(-50, max_offset + 50)
        
        # Style the plot
        plt.gca().set_facecolor('#f8f9fa')
        for spine in plt.gca().spines.values():
            spine.set_visible(True)
            spine.set_color('#cccccc')

        
    def _add_force_statistics(self, force_columns):
        """Helper method to calculate and display force statistics"""
        stats_text = "Force Statistics:\n"
        
        for col in force_columns:
            force_min = self.df[col].min()
            force_max = self.df[col].max()
            force_avg = self.df[col].mean()
            force_std = self.df[col].std()
            
            stats_text += f"{col} - Min: {force_min:.2f}mN, Max: {force_max:.2f}mN, "
            stats_text += f"Avg: {force_avg:.2f}mN, Std: {force_std:.2f}mN\n"
        
        # Add statistics text to the plot
        plt.title(f'Force Channels\n{stats_text}')

    def plot_temperature(self, temp_column=None, timestamp_column=None, show_stats=True):
        """
        Plot temperature data.
        
        Args:
            temp_column (str): Name of temperature column
            timestamp_column (str): Name of timestamp column
            show_stats (bool): Whether to show temperature statistics
            
        Returns:
            matplotlib.figure.Figure: The plot figure
        """
        # Check if data is loaded
        if self.df is None:
            print("No data loaded.")
            return None
        
        # Identify columns if not specified
        temp_column, timestamp_column = self._validate_and_identify_columns(temp_column, timestamp_column)
        if temp_column is None:
            return None
        
        # Create and configure figure
        fig = plt.figure(figsize=(12, 6))
        
        # Plot data with appropriate x-axis
        self._plot_temperature_data(temp_column, timestamp_column)
        
        # Add statistics if requested
        if show_stats:
            self._add_temperature_statistics(temp_column)
        
        # Finalize plot
        plt.ylabel('Temperature (°C)')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        
        # Display plot
        plt.ion()  # Turn on interactive mode
        plt.draw()
        plt.pause(0.001)  # Pause to render the plot
        input("Press Enter to exit...")
        
        return fig

    def _validate_and_identify_columns(self, temp_column, timestamp_column):
        """Helper method to validate and identify columns"""
        # Check if specified columns exist
        if temp_column and temp_column not in self.df.columns:
            print(f"Error: Column '{temp_column}' not found in data.")
            print(f"Available columns: {', '.join(self.df.columns)}")
            return None, None
            
        if timestamp_column and timestamp_column not in self.df.columns:
            print(f"Error: Column '{timestamp_column}' not found in data.")
            print(f"Available columns: {', '.join(self.df.columns)}")
            return None, None
        
        # Auto-identify columns if needed
        if not temp_column or not timestamp_column:
            identified_temp, identified_time = self.identify_columns()
            
            if not temp_column:
                temp_column = identified_temp
            
            if not timestamp_column:
                timestamp_column = identified_time
                
        if not temp_column:
            print("Could not identify temperature column.")
            return None, None
            
        return temp_column, timestamp_column

    def _plot_temperature_data(self, temp_column, timestamp_column):
        """Helper method to plot temperature data with appropriate x-axis"""
        # Check if we can use timestamp for x-axis
        can_use_timestamp = (
            timestamp_column is not None and 
            (pd.api.types.is_datetime64_any_dtype(self.df[timestamp_column]) or 
            isinstance(self.df[timestamp_column].iloc[0], str))
        )
        
        if can_use_timestamp:
            try:
                # Convert timestamps if they're strings
                if not pd.api.types.is_datetime64_any_dtype(self.df[timestamp_column]):
                    self.df[timestamp_column] = pd.to_datetime(self.df[timestamp_column])
                
                plt.plot(self.df[timestamp_column], self.df[temp_column], label='Temperature')
                
                # Format x-axis time display
                plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
                plt.gcf().autofmt_xdate()  # Rotate date labels
                plt.xlabel('Time')
                return
            except Exception as e:
                print(f"Error converting timestamps: {e}")
                # Fall through to sample numbers approach
        
        # Use sample numbers if timestamp not available or conversion failed
        plt.plot(np.arange(1, len(self.df) + 1), self.df[temp_column], label='Temperature')
        plt.xlabel('Sample Number')

    def _add_temperature_statistics(self, temp_column):
        """Helper method to calculate and display temperature statistics"""
        temp_min = self.df[temp_column].min()
        temp_max = self.df[temp_column].max()
        temp_avg = self.df[temp_column].mean()
        temp_std = self.df[temp_column].std()
        
        plt.title(f'Temperature Data\nMin: {temp_min:.2f}°C, Max: {temp_max:.2f}°C, Avg: {temp_avg:.2f}°C')
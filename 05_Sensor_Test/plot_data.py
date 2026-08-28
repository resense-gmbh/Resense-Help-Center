import sys
from src.data_plotter import DataPlotter
import os
# --------------------------------------------------
# Configuration Settings
# --------------------------------------------------
# Plot settings
SHOW_STATISTICS = True  # Whether to show statistics on the plot
# Directory settings
DATA_DIRECTORY = os.getcwd() + '\\data'

# --------------------------------------------------
def main():
    """Main function to load and plot temperature data using DataPlotter."""
    try:
        # Initialize the DataPlotter with the configured directory
        plotter = DataPlotter(directory=DATA_DIRECTORY)
        
        # Find and display available CSV files
        if not plotter.display_available_files():
            print(f"No CSV files found in directory {DATA_DIRECTORY}.")
            sys.exit(1)
        
        # Let the user select a file
        selected_file = plotter.select_file()
        if selected_file is None:
            print("No file selected. Exiting.")
            sys.exit(1)
        
        # Load the selected file
        df = plotter.load_data()
        if df is None:
            print("Failed to load data. Exiting.")
            sys.exit(1)
        
        # Identify temperature and timestamp columns
        temp_column, timestamp_column = plotter.identify_columns()
        
        # # Plot the temperature data
        # fig = plotter.plot_temperature(
        #     temp_column=temp_column,
        #     timestamp_column=timestamp_column,
        #     show_stats=SHOW_STATISTICS
        # )
        
        # Plot the force data
        fig = plotter.plot_force(
            force_columns=["fX", "fY", "fZ"],
            show_stats=SHOW_STATISTICS,
            offset_step=0,
            use_matrix=True
        )
        
        # If you want to save the figure
        # fig.savefig(f"{os.path.splitext(os.path.basename(selected_file))[0]}_plot.png")
        
        print("Plot complete.")
        
    except Exception as e:
        import traceback
        print(f"Error: {type(e).__name__}: {str(e)}")
        print("\nDetailed traceback:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
# klipper_fan_calibrate

## Installation
1. Run the `install.sh` script to set up the module:
   ```bash
   ./install.sh
   ```

2. After installation is complete, add the following section to your printer.cfg file:

    ```[measure_fan]```

## Usage
Running the Calibration
Use the MEASURE_FAN G-code command to start the fan calibration process. Example:

```
MEASURE_FAN [FAN=<fan_name>] [STEPS=<steps>]
```

- FAN: Name of the fan to calibrate (default: fan).
- STEPS: Number of steps to run the fan through (default: 10).

## Plotting the Calibration Results

After the calibration is complete, if you want to plot a graph of the results, run the calibrate_fan.py script with the following command:

```
~/klipper/scripts/calibrate_fan.py <input_csv_file> [output_file_or_directory]
```

- <input_csv_file>: Path to the CSV file generated during calibration (e.g., /tmp/calibration_data_<timestamp>_<fan_name>.csv).
- [output_file_or_directory] (optional): Path to save the output graph. If not provided, the graph will be saved in the current directory with the same name as the input file but with a .png extension.

Example:

```
~/klipper/scripts/calibrate_fan.py /tmp/calibration_data_fan_20231001_123456_.csv ~/graphs/
```

This will save the graph as ~/graphs/calibration_data_fan_20231001_123456_.png.
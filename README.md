# klipper_fan_calibrate

## Table of Contents
1. [Installation](#installation)
2. [Usage](#usage)
   - [MEASURE_FAN Command](#measure_fan-command)
   - [MEASURE_FAN_SPINUP Command](#measure_fan_spinup-command)
3. [Plotting the Calibration Results](#plotting-the-calibration-results)

---

## Installation

1. Run the `install.sh` script to set up the module:
   ```bash
   ./install.sh
   ```

2. After installation is complete, add the following section to your `printer.cfg` file:
   ```ini
   [measure_fan]
   ```

---

## Usage

### MEASURE_FAN Command
The `MEASURE_FAN` G-code command starts the fan calibration process. This command measures the fan's RPM at different power levels to determine its performance characteristics.

#### Syntax:
```gcode
MEASURE_FAN [FAN=<fan_name>] [STEPS=<steps>]
```

#### Parameters:
- `FAN`: Name of the fan to calibrate (default: `fan`).
- `STEPS`: Number of steps to run the fan through (default: `10`).

#### Example:
```gcode
MEASURE_FAN FAN=fan1 STEPS=15
```

---

### MEASURE_FAN_SPINUP Command
The `MEASURE_FAN_SPINUP` G-code command measures the time it takes for the fan to spin up to a target RPM from an initial power level. This is useful for determining the fan's responsiveness.

#### Syntax:
```gcode
MEASURE_FAN_SPINUP [FAN=<fan_name>] [INITIAL_POWER=<initial_power>] [TARGET_POWER=<target_power>] [STEP_TIME=<step_time>] [RPM_THRESHOLD=<rpm_threshold>]
```

#### Parameters:
- `FAN`: Name of the fan to measure (default: `fan`).
- `INITIAL_POWER`: Initial power level to start the fan (default: `0`).
- `TARGET_POWER`: Target power level to reach (default: `1`).
- `STEP_TIME`: Time (in seconds) to wait between steps (default: `0.01`).
- `RPM_THRESHOLD`: RPM threshold to consider the fan stabilized (default: `100`).

#### Example:
```gcode
MEASURE_FAN_SPINUP FAN=fan1 INITIAL_POWER=0.2 TARGET_POWER=0.8 STEP_TIME=0.05 RPM_THRESHOLD=50
```

---

## Plotting the Calibration Results

After the calibration is complete, you can plot a graph of the results using the `calibrate_fan.py` script.

#### Syntax:
```bash
~/klipper/scripts/calibrate_fan.py <input_csv_file> [output_file_or_directory]
```

#### Parameters:
- `<input_csv_file>`: Path to the CSV file generated during calibration (e.g., `/tmp/calibration_data_<timestamp>_<fan_name>.csv`).
- `[output_file_or_directory]` (optional): Path to save the output graph. If not provided, the graph will be saved in the current directory with the same name as the input file but with a `.png` extension.

#### Example:
```bash
~/klipper/scripts/calibrate_fan.py /tmp/calibration_data_fan_20231001_123456_fan1.csv ~/graphs/
```

This will save the graph as `~/graphs/calibration_data_fan_20231001_123456_fan1.png`.

---
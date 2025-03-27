#!/usr/bin/env python3

import matplotlib.pyplot as plt
import csv
from typing import Dict, List
import os
import sys
import numpy as np

def load_data(file_path: str) -> Dict[float, float]:
    """Load CSV data from a file and average RPM readings for duplicate power settings."""
    data = {}
    with open(file_path, "r") as file:
        reader = csv.reader(file)
        next(reader)  # Skip header row
        for row in reader:
            # Skip rows that do not have at least 2 columns
            if len(row) < 2:
                continue
            try:
                power, rpm = float(row[0]), float(row[1])
                if power not in data:
                    data[power] = []
                data[power].append(rpm)
            except ValueError:
                # Skip rows with invalid data
                continue

    # Average RPM readings for each power setting
    averaged_data = {power: sum(rpms) / len(rpms) for power, rpms in data.items()}
    return averaged_data

def prepare_plot_data(file_path: str) -> Dict[str, List[float]]:
    """Prepare x and y values for plotting from a single dataset."""
    data = load_data(file_path)
    all_x_values = sorted(data.keys())
    y_values = [data[x] for x in all_x_values]
    return {"x_values": all_x_values, "y_values": y_values}

def plot_data(x_values: List[float], y_values: List[float], label: str, output_file: str, color: str = "blue"):
    """Plot the data and save it to a file."""
    plt.figure(figsize=(10, 5))

    # Plot the dataset
    plt.plot(x_values, y_values, label=label, color=color)

    # Add horizontal lines for min and max RPM values
    min_rpm = min(y_values)
    max_rpm = max(y_values)
    min_power = x_values[y_values.index(min_rpm)]
    max_power = x_values[y_values.index(max_rpm)]

    plt.axhline(y=min_rpm, color="green", linestyle="--", label=f"Min RPM: {min_rpm}")
    plt.axhline(y=max_rpm, color="red", linestyle="--", label=f"Max RPM: {max_rpm}")

    # Add a textbox with recommended settings
    text = (
        f"Recommended settings for this fan:\n"
        f"min_power: {min_power:.2f}\n"
        f"max_power: {max_power:.2f}"
    )
    plt.text(
        0.05, 0.95, text, transform=plt.gca().transAxes, fontsize=10,
        verticalalignment="top", bbox=dict(boxstyle="round", facecolor="white", alpha=0.5)
    )

    # Labels and title
    plt.xlabel("Power")
    plt.ylabel("RPM")
    plt.title("Power vs RPM")
    plt.legend()
    plt.grid(True)

    # Customize x-axis labels to show 10 evenly spaced values from the range of x_values
    num_ticks = 10
    tick_positions = np.linspace(min(x_values), max(x_values), num_ticks)
    plt.xticks(ticks=tick_positions, labels=[f"{tick:.2f}" for tick in tick_positions])

    # Save the plot to a file
    plt.savefig(output_file, format="png", dpi=300)
    print(f"Plot saved to {output_file}")

    # Show the plot
    # plt.show()

# Main execution
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python calibrate_fan.py <input_csv_file> [output_file_or_directory]")
        sys.exit(1)

    input_file = sys.argv[1]
    if not os.path.isfile(input_file):
        print(f"Error: File '{input_file}' not found.")
        sys.exit(1)

    # Determine output file path
    if len(sys.argv) > 2:
        output_arg = sys.argv[2]
        if os.path.isdir(output_arg):
            # If the second argument is a directory, use it to construct the output file path
            output_file = os.path.join(output_arg, os.path.splitext(os.path.basename(input_file))[0] + ".png")
        else:
            # If the second argument is a file path, use it as is
            output_file = output_arg
    else:
        # Default output file path: use input filename without path, with .png extension
        output_file = os.path.splitext(os.path.basename(input_file))[0] + ".png"

    # Prepare data and plot
    plot_data_dict = prepare_plot_data(input_file)
    plot_data(plot_data_dict["x_values"], plot_data_dict["y_values"], label=os.path.basename(input_file), output_file=output_file)
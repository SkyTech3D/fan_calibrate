#!/usr/bin/env python3

import matplotlib.pyplot as plt
import csv
from typing import Dict, List
import os
import sys
import numpy as np
from statistics import mean, stdev

def load_data(file_path: str) -> Dict[float, List[float]]:
    """Load CSV data from a file."""
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
    return data

def prepare_plot_data(file_path: str) -> Dict[str, List[float]]:
    """Prepare x and y values for plotting from a single dataset."""
    data = load_data(file_path)
    all_x_values = sorted(data.keys())
    y_values = [data[x] for x in all_x_values]
    return {"x_values": all_x_values, "y_values": y_values}

def plot_data(x_values: List[float], y_values: List[List[float]], label: str, output_file: str, color: str = "blue"):
    """Plot the data and save it to a file."""
    plt.figure(figsize=(20, 10))

    # Calculate mean and standard deviation for each power setting
    means = [mean(rpms) for rpms in y_values]
    stdevs = [stdev(rpms) if len(rpms) > 1 else 0 for rpms in y_values]

    # Plot the mean line
    plt.plot(x_values, means, label=label, color=color)

    # Plot all individual RPM values as scatter points
    for x, rpms in zip(x_values, y_values):
        plt.scatter([x] * len(rpms), rpms, color=color, alpha=0.5, edgecolor="black", zorder=5, s=3)

    # Add a shaded region for the standard deviation
    lower_bound = [m - s for m, s in zip(means, stdevs)]
    upper_bound = [m + s for m, s in zip(means, stdevs)]
    plt.fill_between(x_values, lower_bound, upper_bound, color=color, alpha=0.9, label="±1 stdev")

    # Filter out 0 values and those with outstandingly large ranges for min_rpm calculation
    ranges = [u - l for u, l in zip(upper_bound, lower_bound)]
    threshold = np.mean(ranges) + 2 * np.std(ranges)  # Define an outlier threshold
    filtered_means = [
        rpm for rpm, r in zip(means, ranges) if rpm > 0 and r <= threshold
    ]
    min_rpm = min(filtered_means)
    min_power = x_values[means.index(min_rpm)]

    # Find max_power based on the derivative of the means line, ignoring zero values
    non_zero_means = [m for m in means if m > 0]
    non_zero_x_values = [x for x, m in zip(x_values, means) if m > 0]
    derivatives = np.gradient(non_zero_means, non_zero_x_values)  # Calculate the numerical derivative
    derivative_threshold = 10  # Define a threshold for a nearly horizontal line
    max_power_index = next(
        (i for i, d in enumerate(derivatives) if abs(d) < derivative_threshold),
        len(non_zero_x_values) - 1,  # Default to the last index if no threshold is met
    )
    max_power = non_zero_x_values[max_power_index-1]
    max_rpm = non_zero_means[max_power_index-1]

    # Add horizontal lines for min and max RPM values
    plt.axhline(y=min_rpm, color="green", linestyle="--", label=f"Min RPM: {min_rpm}")
    plt.axhline(y=max_rpm, color="red", linestyle="--", label=f"Max RPM: {max_rpm}")

    # Add vertical lines at min_power and max_power
    plt.axvline(x=min_power, color="green", linestyle="--", label=f"Min Power: {min_power}")
    plt.axvline(x=max_power, color="red", linestyle="--", label=f"Max Power: {max_power}")

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
import argparse
import csv
import os
import sys
import time
from datetime import datetime

import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import numpy as np


def find_observer_port() -> str:
    """Find the serial port connected to the ESP32 Observer."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        # Common identifiers for ESP32 boards
        if "USB" in port.description or "UART" in port.description or "CH340" in port.description or "CP210" in port.description:
            return port.device
            
    # Fallback for Mac
    for port in ports:
        if "cu.usbmodem" in port.device or "cu.usbserial" in port.device:
            return port.device
            
    raise RuntimeError("Could not find ESP32 hardware observer port automatically.")


def run_collection(port: str, baudrate: int, num_samples: int) -> str:
    """Read sync data from the observer serial port and save to CSV."""
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "test_results")
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = os.path.join(results_dir, f"arch2_sync_test_{timestamp}.csv")

    raw_data = []
    
    print(f"Opening Serial Port: {port} at {baudrate} baud...")
    
    with serial.Serial(port, baudrate, timeout=1) as ser:
        print("\n=======================================================")
        print(f" Architecture 2 Observer Sync Test started ")
        print(f" Waiting for {num_samples} state machine pulses...")
        print("=======================================================\n")
        
        # Clear any old data in the buffer
        ser.reset_input_buffer()
        print("Waiting for first signal... (Make sure Devices A and B are running their State Machines)")
        
        while len(raw_data) < num_samples:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                
                if line.startswith("DATA:"):
                    parts = line[5:].split(',')
                    if len(parts) == 3:
                        time_a = int(parts[0])
                        time_b = int(parts[1])
                        drift_us = int(parts[2])
                        
                        raw_data.append({
                            "sample": len(raw_data) + 1,
                            "time_a_us": time_a,
                            "time_b_us": time_b,
                            "drift_us": drift_us
                        })
                        
                        sys.stdout.write(f"\rCollected {len(raw_data)}/{num_samples} samples... (Last Drift: {drift_us} µs)    ")
                        sys.stdout.flush()
                        
            except ValueError:
                pass
            except KeyboardInterrupt:
                print("\n\nTest interrupted by user. Saving collected data...")
                break

    print(f"\n\nSaving {len(raw_data)} samples to {csv_file}")
    with open(csv_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["sample", "time_a_us", "time_b_us", "drift_us"])
        writer.writeheader()
        writer.writerows(raw_data)

    return csv_file


def analyze_sync_results(csv_file: str):
    """Analyze the CSV data and plot the results."""
    print(f"\nAnalyzing results from: {csv_file}")
    
    drifts_us = []
    
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            drifts_us.append(int(row['drift_us']))

    if not drifts_us:
        print("No data collected in CSV.")
        return

    # Convert to NumPy array for easier math
    data = np.array(drifts_us)
    data_abs = np.abs(data)
    
    # Calculate statistics
    avg_drift = np.mean(data)
    std_dev = np.std(data)
    max_drift = np.max(data_abs)
    min_drift = np.min(data_abs)
    
    p95 = np.percentile(data_abs, 95)
    p99 = np.percentile(data_abs, 99)
    
    # Identify which device is usually faster
    # drift_us = capturedRisingA - capturedRisingB
    # positive means A fired AFTER B (so B was faster)
    # negative means A fired BEFORE B (so A was faster)
    b_faster_count = np.sum(data > 0)
    a_faster_count = np.sum(data < 0)
    perfect_count  = np.sum(data == 0)

    print("\n=======================================================")
    print(" Architecture 2 - Synchronization Analysis Report ")
    print("=======================================================")
    print(f"Total Pulses Analyzed : {len(data)}")
    print(f"Average Sync Error    : {np.mean(data_abs):.2f} µs")
    print(f"Maximum Jitter        : {max_drift} µs")
    print(f"Minimum Jitter        : {min_drift} µs")
    print(f"Standard Deviation    : {std_dev:.2f} µs")
    print(f"95th Percentile       : {p95:.1f} µs")
    print(f"99th Percentile       : {p99:.1f} µs")
    print("-------------------------------------------------------")
    print(f"Device A was faster   : {a_faster_count} times")
    print(f"Device B was faster   : {b_faster_count} times")
    print(f"Perfect Sync (0µs)    : {perfect_count} times")
    print("=======================================================\n")

    # ----- Plotting -----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    # 1. Time Series Plot
    ax1.plot(range(1, len(data) + 1), data, marker='o', linestyle='-', markersize=3, alpha=0.7)
    ax1.axhline(0, color='black', linewidth=1, linestyle='--')
    ax1.set_title("Sync Drift Over Time")
    ax1.set_xlabel("Pulse Number")
    ax1.set_ylabel("Drift (microseconds)\n+ve = B faster, -ve = A faster")
    ax1.grid(True, alpha=0.3)
    
    # 2. Histogram
    # Use smart bins based on standard deviation to catch outliers clearly
    ax2.hist(data, bins=40, color='skyblue', edgecolor='black', alpha=0.8)
    ax2.axvline(0, color='red', linestyle='--', linewidth=1.5, label='Perfect Sync')
    ax2.set_title("Distribution of Synchronization Error")
    ax2.set_xlabel("Jitter / Drift (microseconds)")
    ax2.set_ylabel("Frequency")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plot_file = csv_file.replace(".csv", "_plot.png")
    plt.savefig(plot_file, dpi=300)
    print(f"\nPlot saved to: {plot_file}")
    print("Showing plot now... (Close the plot window to exit)")
    
    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Arch 2 synchronization drift.")
    parser.add_argument("--port", help="Serial port of the observer ESP32", default=None)
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    parser.add_argument("--samples", type=int, default=200, help="Number of pulses to measure")
    parser.add_argument("--analyze-only", help="Skip collection and analyze an existing CSV file", default=None)

    args = parser.parse_args()

    if args.analyze_only:
        if os.path.exists(args.analyze_only):
            analyze_sync_results(args.analyze_only)
        else:
            print(f"File not found: {args.analyze_only}")
    else:
        # Determine port
        port = args.port
        if not port:
            try:
                port = find_observer_port()
            except Exception as e:
                print(f"Error: {e}")
                print("Please explicitly provide the port like: python arch2_sync_test.py --port /dev/cu.usbserial-110")
                sys.exit(1)
                
        # Run test
        saved_csv = run_collection(port, args.baud, args.samples)
        
        # Analyze and Plot
        analyze_sync_results(saved_csv)

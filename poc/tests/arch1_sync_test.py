#!/usr/bin/env python3
"""
Architecture 1 Sync & Absolute Latency Test

Tests absolute network latency and synchronization drift by broadcasting UDP "relay:on" 
messages to edge devices, and then using the Observer ESP32 via serial to measure
the temporal drift between the Mac sending the command and both edge devices triggering.
"""

import argparse
import csv
import os
import socket
import sys
import time
from datetime import datetime

import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import numpy as np

UDP_BROADCAST_IP = "255.255.255.255"
UDP_BROADCAST_PORT = 4210

def find_observer_port() -> str:
    """Find the serial port connected to the ESP32 Observer."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "USB" in port.description or "UART" in port.description or "CH340" in port.description or "CP210" in port.description:
            return port.device
            
    # Fallback for Mac
    for port in ports:
        if "cu.usbmodem" in port.device or "cu.usbserial" in port.device:
            return port.device
            
    raise RuntimeError("Could not find ESP32 hardware observer port automatically.")


def run_collection(port: str, baudrate: int, num_samples: int, delay: float) -> str:
    """Send UDP broadcasts, read sync/latency data from the observer serial port, and save to CSV."""
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "test_results")
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = os.path.join(results_dir, f"arch1_latency_sync_test_{timestamp}.csv")

    raw_data = []
    
    # Setup UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    print(f"Opening Serial Port: {port} at {baudrate} baud...")
    
    with serial.Serial(port, baudrate, timeout=1.0) as ser:
        print("\n=======================================================")
        print(f" Architecture 1 (UDP) Full Latency & Sync Test started ")
        print(f" Waiting for {num_samples} samples...")
        print("=======================================================\n")
        
        # Synchronize edge devices to OFF first
        print("Synchronizing Edge ESP32 state to OFF...")
        sock.sendto(b"relay:off", (UDP_BROADCAST_IP, UDP_BROADCAST_PORT))
        time.sleep(1)
        
        ser.reset_input_buffer()
        print("Commencing Test... Sending UDP Broadcasts")
        
        while len(raw_data) < num_samples:
            try:
                # 1. Ensure devices are OFF
                sock.sendto(b"relay:off", (UDP_BROADCAST_IP, UDP_BROADCAST_PORT))
                time.sleep(0.1)
                
                # 2. Tell the observer to start timing immediately
                ser.reset_input_buffer()
                ser.write(b"H")
                ser.flush()
                
                # 3. Quickly Fire ON pulse
                sock.sendto(b"relay:on", (UDP_BROADCAST_IP, UDP_BROADCAST_PORT))
                
                # 4. Wait for observer response (using timeout loop)
                start_wait = time.time()
                while time.time() - start_wait < 2.0:
                    if ser.in_waiting:
                        line = ser.readline().decode('utf-8', errors='ignore').strip()
                        
                        if line.startswith("DATA:"):
                            parts = line[5:].split(',')
                            if len(parts) == 2:
                                lat_a_us = int(parts[0])
                                lat_b_us = int(parts[1])
                                drift_us = lat_a_us - lat_b_us
                                
                                raw_data.append({
                                    "sample": len(raw_data) + 1,
                                    "latency_a_us": lat_a_us,
                                    "latency_b_us": lat_b_us,
                                    "drift_us": drift_us
                                })
                                
                                sys.stdout.write(f"\rCollected {len(raw_data)}/{num_samples}... Latency A: {lat_a_us}µs | Latency B: {lat_b_us}µs | Drift: {drift_us}µs    ")
                                sys.stdout.flush()
                            break
                        elif line.startswith("TIMEOUT"):
                            print(f"\nHardware Observer Timeout: {line}")
                            break
                            
                time.sleep(delay)
                
            except KeyboardInterrupt:
                print("\n\nTest interrupted by user. Saving collected data...")
                break

    sock.close()

    if not raw_data:
        print("\nNo valid data collected.")
        sys.exit(0)

    print(f"\n\nSaving {len(raw_data)} samples to {csv_file}")
    with open(csv_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["sample", "latency_a_us", "latency_b_us", "drift_us"])
        writer.writeheader()
        writer.writerows(raw_data)

    return csv_file


def analyze_sync_results(csv_file: str):
    """Analyze the CSV data and plot the results."""
    print(f"\nAnalyzing results from: {csv_file}")
    
    lat_a = []
    lat_b = []
    drifts_us = []
    
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat_a.append(int(row['latency_a_us']))
            lat_b.append(int(row['latency_b_us']))
            drifts_us.append(int(row['drift_us']))

    if not drifts_us:
        print("No data collected in CSV.")
        return

    # Convert to NumPy array for easier math
    data_drift = np.array(drifts_us)
    data_abs_drift = np.abs(data_drift)
    data_lata = np.array(lat_a) / 1000.0  # Convert to ms
    data_latb = np.array(lat_b) / 1000.0  # Convert to ms
    
    print("\n=======================================================")
    print(" Architecture 1 - Network Latency & Sync Report ")
    print("=======================================================")
    print(f"Total Pulses Analyzed : {len(data_drift)}")
    print("-------------------------------------------------------")
    print(" --- ABSOLUTE CONNECTIVITY LATENCY (ms) --- ")
    print(f"Device A Avg Latency  : {np.mean(data_lata):.2f} ms")
    print(f"Device B Avg Latency  : {np.mean(data_latb):.2f} ms")
    print(f"Network Latency Jitter: {np.std(data_lata):.2f} ms (DevA) / {np.std(data_latb):.2f} ms (DevB)")
    print("-------------------------------------------------------")
    print(" --- SYNCHRONIZATION DRIFT (µs) --- ")
    print(f"Average Sync Error    : {np.mean(data_abs_drift):.2f} µs")
    print(f"Maximum Jitter        : {np.max(data_abs_drift)} µs")
    print(f"Minimum Jitter        : {np.min(data_abs_drift)} µs")
    print(f"Standard Deviation    : {np.std(data_drift):.2f} µs")
    print(f"95th Percentile       : {np.percentile(data_abs_drift, 95):.1f} µs")
    print(f"99th Percentile       : {np.percentile(data_abs_drift, 99):.1f} µs")
    print("=======================================================\n")

    # ----- Plotting -----
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. Latency Time Series Plot
    ax1.plot(range(1, len(data_lata) + 1), data_lata, color='blue', label='Device A', alpha=0.7)
    ax1.plot(range(1, len(data_latb) + 1), data_latb, color='green', label='Device B', alpha=0.7)
    ax1.set_title("Absolute Network Latency")
    ax1.set_xlabel("Pulse Number")
    ax1.set_ylabel("Latency (ms)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. Latency Histogram
    ax2.hist([data_lata, data_latb], bins=30, color=['blue', 'green'], label=['Device A', 'Device B'], alpha=0.7)
    ax2.set_title("Network Latency Distribution")
    ax2.set_xlabel("Latency (millseconds)")
    ax2.set_ylabel("Frequency")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # 3. Sync Drift Time Series Plot
    ax3.plot(range(1, len(data_drift) + 1), data_drift, marker='o', color='purple', linestyle='-', markersize=3, alpha=0.7)
    ax3.axhline(0, color='red', linewidth=1, linestyle='--')
    ax3.set_title("Sync Drift Over Time")
    ax3.set_xlabel("Pulse Number")
    ax3.set_ylabel("Drift (microseconds)\n+ve = B faster, -ve = A faster")
    ax3.grid(True, alpha=0.3)
    
    # 4. Drift Histogram
    ax4.hist(data_drift, bins=40, color='purple', edgecolor='black', alpha=0.7)
    ax4.axvline(0, color='red', linestyle='--', linewidth=1.5, label='Perfect Sync')
    ax4.set_title("Synchronization Error Distribution")
    ax4.set_xlabel("Drift (microseconds)")
    ax4.set_ylabel("Frequency")
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plot_file = csv_file.replace(".csv", "_plot.png")
    plt.savefig(plot_file, dpi=300)
    print(f"\nPlot saved to: {plot_file}")
    print("Showing plot now... (Close the plot window to exit)")
    
    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Arch 1 synchronization drift and absolute network latency.")
    # Notice we updated the baudrate to 2,000,000 to match the new firmare's high-speed USB settings.
    parser.add_argument("--port", help="Serial port of the observer ESP32", default=None)
    parser.add_argument("--baud", type=int, default=2000000, help="Baud rate (Must match Observer)")
    parser.add_argument("--samples", type=int, default=200, help="Number of pulses to measure")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between UDP broadcasts in seconds")
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
                print("Please explicitly provide the port like: python arch1_sync_test.py --port /dev/cu.usbserial-110")
                sys.exit(1)
                
        # Run test
        saved_csv = run_collection(port, args.baud, args.samples, args.delay)
        
        # Analyze and Plot
        analyze_sync_results(saved_csv)

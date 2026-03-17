#!/usr/bin/env python3
"""
Hardware Latency Test (Ground Truth)

Drives an Observer ESP32 via serial to measure the true physical latency 
between the Mac sending a UDP packet and the Edge ESP32 changing its GPIO pin.

Usage:
    python -m src.tests.hardware_latency_test /dev/cu.usbserial-XXXX
"""

import argparse
import csv
import os
import socket
import sys
import time
from datetime import datetime

import serial

UDP_BROADCAST_IP = "255.255.255.255"
UDP_BROADCAST_PORT = 4210

def main():
    parser = argparse.ArgumentParser(description="Hardware Latency Observer Test")
    parser.add_argument("port", help="Serial port of the Observer ESP32 (e.g., /dev/cu.usbserial-1410)")
    parser.add_argument("--baud", type=int, default=2000000, help="Baud rate (must match Observer)")
    parser.add_argument("--count", type=int, default=100, help="Number of test cycles")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between toggles in seconds")
    parser.add_argument("--output", type=str, default="test_results", help="Output directory")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Hardware Latency Test (Observer Mode)")
    print(f"  Port:  {args.port} @ {args.baud} bps")
    print(f"  Count: {args.count} cycles")
    print(f"{'='*60}\n")

    # 1. Setup UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    # 2. Setup Serial connection
    try:
        ser = serial.Serial(args.port, args.baud, timeout=2.0)
    except serial.SerialException as e:
        print(f"Error opening serial port {args.port}: {e}")
        sys.exit(1)

    # Wait for Observer to reboot/initialize
    print("Waiting for Observer ESP32 to initialize...")
    time.sleep(2)
    ser.reset_input_buffer()

    results_us = []
    
    # 3. Synchronize initial state to OFF
    print("\nSynchronizing Edge ESP32 state to OFF...")
    sock.sendto(b"relay:off", (UDP_BROADCAST_IP, UDP_BROADCAST_PORT))
    time.sleep(1)

    # 4. Run the test loop
    print("\nCommencing Test...")
    for i in range(1, args.count + 1):
        # ── Test ON transition ──
        ser.write(b"H")                   # 1. Tell Observer to start timer & wait for HIGH
        ser.flush()                       # 2. Force USB transmission
        sock.sendto(b"relay:on", (UDP_BROADCAST_IP, UDP_BROADCAST_PORT)) # 3. Multicast UDP Command
        
        # Read the microsecond latency back from the Observer
        line = ser.readline().decode('utf-8').strip()
        
        if line and line.isdigit():
            latency_ms = int(line) / 1000.0
            results_us.append(int(line))
            print(f"  [{i:>3}/{args.count}] ON  latency: {latency_ms:>7.2f} ms")
        else:
            print(f"  [{i:>3}/{args.count}] ON  FAILED: {line}")

        time.sleep(args.delay)

        # ── Test OFF transition ──
        ser.write(b"L")                   # 1. Tell Observer to start timer & wait for LOW
        ser.flush()                       # 2. Force USB transmission
        sock.sendto(b"relay:off", (UDP_BROADCAST_IP, UDP_BROADCAST_PORT)) # 3. Multicast UDP Command
        
        line = ser.readline().decode('utf-8').strip()
        
        if line and line.isdigit():
            latency_ms = int(line) / 1000.0
            results_us.append(int(line))
            print(f"  [{i:>3}/{args.count}] OFF latency: {latency_ms:>7.2f} ms")
        else:
            print(f"  [{i:>3}/{args.count}] OFF FAILED: {line}")

        time.sleep(args.delay)

    ser.close()
    sock.close()

    if not results_us:
        print("\nNo valid results collected.")
        return

    # 5. Compute Stats & Save
    latency_array = [x / 1000.0 for x in results_us] # convert to ms
    latency_array.sort()
    
    n = len(latency_array)
    avg = sum(latency_array) / n
    variance = sum((r - avg) ** 2 for r in latency_array) / n
    jitter = variance ** 0.5
    
    print(f"\n{'='*60}")
    print(f"  HARDWARE RESULTS (Ground Truth)")
    print(f"{'='*60}")
    print(f"  Samples:  {n} / {args.count * 2}")
    print(f"  Min:      {latency_array[0]:>7.2f} ms")
    print(f"  Avg:      {avg:>7.2f} ms")
    print(f"  Median:   {latency_array[int(n*0.5)]:>7.2f} ms")
    print(f"  P95:      {latency_array[int(n*0.95)]:>7.2f} ms")
    print(f"  Max:      {latency_array[-1]:>7.2f} ms")
    print(f"  Jitter:   {jitter:>7.2f} ms\n")

    # Save to CSV
    os.makedirs(args.output, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(args.output, f"hardware_test_{timestamp}.csv")
    
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sample", "latency_ms"])
        for i, val in enumerate(results_us):
            writer.writerow([i + 1, f"{val / 1000.0:.3f}"])
            
    print(f"  → Saved raw data to: {csv_path}")

if __name__ == "__main__":
    main()

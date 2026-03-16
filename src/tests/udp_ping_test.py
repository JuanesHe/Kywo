#!/usr/bin/env python3
"""
UDP Round-Trip Latency Test for Architecture 1.

Sends 'ping:<seq>' packets via UDP broadcast and measures the round-trip
time for each ESP32 that echoes back 'pong:<seq>'.

Usage:
    python -m src.tests.udp_ping_test                        # 100 pings, 50ms apart
    python -m src.tests.udp_ping_test --count 500 --interval 20  # 500 pings, 20ms apart

Output:  CSV file + live console stats (min/max/avg/p95/p99/jitter).
"""

import argparse
import csv
import os
import socket
import time
from collections import defaultdict
from datetime import datetime


def run_ping_test(count: int, interval_ms: int, port: int, output_dir: str):
    # --- Create the broadcast socket ---
    tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    tx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    tx_sock.setblocking(False)

    # --- Create the receive socket (bound to same port to catch pong replies) ---
    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Bind to 0.0.0.0 so we receive replies from any interface
    rx_sock.bind(("0.0.0.0", port))
    rx_sock.settimeout(0.002)  # 2ms poll timeout

    broadcast_addr = ("255.255.255.255", port)

    # --- Results storage: device_ip -> list of RTT values (µs) ---
    results: dict[str, list[float]] = defaultdict(list)
    send_times: dict[int, float] = {}  # seq -> perf_counter_ns
    lost = 0

    print(f"\n{'='*60}")
    print(f"  UDP Round-Trip Latency Test")
    print(f"  Pings: {count}  |  Interval: {interval_ms}ms  |  Port: {port}")
    print(f"{'='*60}\n")

    for seq in range(1, count + 1):
        # Send ping
        message = f"ping:{seq}".encode("utf-8")
        t_send = time.perf_counter_ns()
        tx_sock.sendto(message, broadcast_addr)
        send_times[seq] = t_send

        # Collect replies for 'interval_ms' duration
        deadline = time.perf_counter_ns() + interval_ms * 1_000_000
        while time.perf_counter_ns() < deadline:
            try:
                data, addr = rx_sock.recvfrom(512)
            except (socket.timeout, BlockingIOError):
                continue

            text = data.decode("utf-8", errors="ignore")
            if not text.startswith("pong:"):
                continue

            try:
                pong_seq = int(text[5:])
            except ValueError:
                continue

            if pong_seq in send_times:
                rtt_ns = time.perf_counter_ns() - send_times[pong_seq]
                rtt_us = rtt_ns / 1_000
                device_ip = addr[0]
                results[device_ip].append(rtt_us)

                if seq % 10 == 0 or seq == 1:
                    print(f"  [ping {seq:>4}] {device_ip:>15}  RTT = {rtt_us:>8.1f} µs  ({rtt_us/1000:.2f} ms)")

    # --- Check for lost pings ---
    all_responded_seqs = set()
    for rtts in results.values():
        all_responded_seqs.update(range(len(rtts)))
    lost = count - max((len(v) for v in results.values()), default=0)

    # --- Statistics per device ---
    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}\n")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(output_dir, exist_ok=True)

    for device_ip, rtts in sorted(results.items()):
        rtts_sorted = sorted(rtts)
        n = len(rtts_sorted)
        avg = sum(rtts_sorted) / n
        mn = rtts_sorted[0]
        mx = rtts_sorted[-1]
        p50 = rtts_sorted[int(n * 0.50)]
        p95 = rtts_sorted[int(n * 0.95)]
        p99 = rtts_sorted[min(int(n * 0.99), n - 1)]

        # Jitter = standard deviation of RTT
        variance = sum((r - avg) ** 2 for r in rtts_sorted) / n
        jitter = variance ** 0.5

        print(f"  Device: {device_ip}")
        print(f"  ├── Samples:  {n}/{count}")
        print(f"  ├── Min:      {mn:>8.1f} µs  ({mn/1000:.2f} ms)")
        print(f"  ├── Avg:      {avg:>8.1f} µs  ({avg/1000:.2f} ms)")
        print(f"  ├── Median:   {p50:>8.1f} µs  ({p50/1000:.2f} ms)")
        print(f"  ├── P95:      {p95:>8.1f} µs  ({p95/1000:.2f} ms)")
        print(f"  ├── P99:      {p99:>8.1f} µs  ({p99/1000:.2f} ms)")
        print(f"  ├── Max:      {mx:>8.1f} µs  ({mx/1000:.2f} ms)")
        print(f"  └── Jitter:   {jitter:>8.1f} µs  ({jitter/1000:.2f} ms)")
        print()

        # Save CSV
        csv_path = os.path.join(output_dir, f"ping_results_{device_ip}_{timestamp}.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["seq", "rtt_us", "rtt_ms"])
            for i, rtt in enumerate(rtts):
                writer.writerow([i + 1, f"{rtt:.1f}", f"{rtt/1000:.3f}"])
        print(f"  → Saved: {csv_path}")

    if not results:
        print("  ⚠  No responses received! Make sure:")
        print("     1. At least one ESP32 is running the UDP firmware")
        print("     2. The ESP32 is on the same WiFi network")
        print(f"     3. UDP port {port} is not blocked by a firewall")

    # Cleanup
    tx_sock.close()
    rx_sock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UDP Round-Trip Latency Test")
    parser.add_argument("--count", type=int, default=100, help="Number of pings to send")
    parser.add_argument("--interval", type=int, default=50, help="Interval between pings in ms")
    parser.add_argument("--port", type=int, default=4210, help="UDP port")
    parser.add_argument("--output", type=str, default="test_results", help="Output directory")
    args = parser.parse_args()

    run_ping_test(
        count=args.count,
        interval_ms=args.interval,
        port=args.port,
        output_dir=args.output,
    )

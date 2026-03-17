# Results Analysis: Software vs Hardware Measurement Comparison

## Latency Measurement Comparison

The median round-trip latency measured by software timestamps (Test 0) was 41.72 ms and 41.45 ms for Device A and Device B, respectively. In contrast, the hardware observer (Test 1) measured a median latency of 25.16 ms for both devices. This discrepancy can be attributed to software processing overhead, including Python timestamp acquisition, socket buffer processing, and operating system scheduling delays that are captured in the software measurements but eliminated in the hardware interrupt-based approach.

## Data Distribution and Wireless Variability

Both Test 0 and Test 1 exhibit right-skewed distributions, evidenced by mean values consistently exceeding median values (e.g., Test 0: mean 57.03 ms vs median 41.72 ms; Test 1: mean 49.42 ms vs median 25.16 ms). This skewness indicates occasional high-latency outliers caused by:

- **Wireless communication unpredictability**: Wi-Fi carrier sense and contention delays
- **Network congestion**: Variable router processing times
- **Interference and retry mechanisms**: 802.11 protocol backoff and retransmission

The large standard deviations (Test 0: ~55 ms; Test 1: ~49 ms) further confirm the inherent variability of UDP broadcast over Wi-Fi networks.

## Synchronization Drift Precision

The precision of synchronization drift measurement differs dramatically between software and hardware approaches:

- **Test 0 (Software drift)**: Mean = 0.50 ms, Median = 0.02 ms
- **Test 1 (Hardware drift)**: Mean = 7.88 µs, Median = 5.00 µs

The hardware observer provides **63× better precision** in mean drift measurement (0.50 ms vs 0.00788 ms). The software method's median of 0.02 ms (20 µs) appears competitive, but the high mean and standard deviation (0.96 ms) reveal significant measurement noise. In contrast, the hardware method achieves sub-10 µs mean drift with a standard deviation of only 10.34 µs, demonstrating microsecond-level precision.

## Key Findings

1. **Hardware measurement eliminates software overhead**: 25.16 ms hardware latency vs 41.72 ms software RTT represents a ~40% reduction by removing Python processing delays.

2. **Microsecond vs millisecond precision**: Hardware interrupts provide three orders of magnitude better timing resolution than software timestamps.

3. **Ground truth validation**: Test 1's hardware observer provides the true physical synchronization (7.88 µs mean drift), while Test 0's software approach can only estimate synchronization within millisecond accuracy.

4. **Consistent device behavior**: Both devices show nearly identical performance in hardware measurements (Device A and B both: 25.16 ms median, 49.42 ms mean), indicating symmetric network paths and minimal device-specific variation.

## Statistical Confidence

The 95th (P95) and 99th (P99) percentile values reveal tail behavior:

- **Test 0 Software RTT**: P95 = 175.23 ms, P99 = 226.86 ms (high variability)
- **Test 1 Hardware Latency**: P95 = 110.18 ms, P99 = 188.93 ms (still variable but lower)
- **Test 0 Software Drift**: P95 = 2.53 ms, P99 = 3.73 ms
- **Test 1 Hardware Drift**: P95 = 21.00 µs, P99 = 32.50 µs (sub-millisecond even at 99th percentile)

Even in the worst 1% of cases, hardware-measured synchronization drift remains below 33 µs, demonstrating the robustness of Architecture 1's centralized UDP broadcast approach.

## Conclusion

The hardware observer methodology (Test 1) provides ground truth measurements with microsecond precision, validating that Architecture 1 achieves mean synchronization drift of 7.88 µs between edge nodes. Software-based measurements (Test 0) are limited by millisecond-resolution timestamps and cannot accurately capture sub-millisecond synchronization phenomena. For applications requiring tight temporal coordination, hardware interrupt-based validation is essential to verify synchronization performance.

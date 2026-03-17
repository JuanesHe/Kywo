#!/usr/bin/env python3
"""
Analyze ping test CSV results and generate publication-quality figures.

Usage:
    python -m src.tests.analyze_results                             # analyze latest
    python -m src.tests.analyze_results test_results/ping_test_*.csv  # specific file(s)
    python -m src.tests.analyze_results --all                       # combine all CSVs

Generates:
    1. RTT time-series plot (latency over packet sequence)
    2. RTT histogram / distribution
    3. CDF (Cumulative Distribution Function)
    4. Box plot (for multi-device comparison)
    5. Summary statistics table (LaTeX-ready)
"""

import argparse
import csv
import glob
import os
import sys

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import numpy as np


def load_csv(filepath: str) -> dict[str, list[float]]:
    """Load a ping test or hardware latency test CSV. Returns {device_ip: [rtt_ms, ...]}."""
    data: dict[str, list[float]] = {}
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "device_ip" in row and "rtt_ms" in row:
                ip = row["device_ip"]
                rtt_ms = float(row["rtt_ms"])
            elif "latency_ms" in row:
                ip = "Hardware Observer"
                rtt_ms = float(row["latency_ms"])
            else:
                continue
            data.setdefault(ip, []).append(rtt_ms)
    return data


def compute_stats(rtts: list[float]) -> dict:
    """Compute statistics for a list of RTT values in ms."""
    arr = np.array(sorted(rtts))
    n = len(arr)
    return {
        "n": n,
        "min": float(arr[0]),
        "max": float(arr[-1]),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr)),
        "p5": float(np.percentile(arr, 5)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "jitter": float(np.std(arr)),
    }


def plot_timeseries(data: dict[str, list[float]], output_dir: str, title_suffix: str = ""):
    """Fig 1: RTT over packet sequence number."""
    fig, ax = plt.subplots(figsize=(10, 4))

    for ip, rtts in data.items():
        ax.plot(range(1, len(rtts) + 1), rtts, linewidth=0.8, alpha=0.8, label=ip)
        stats = compute_stats(rtts)
        ax.axhline(y=stats["mean"], linestyle="--", alpha=0.4, color="gray")

    ax.set_xlabel("Packet Sequence Number", fontsize=12)
    ax.set_ylabel("Round-Trip Time (ms)", fontsize=12)
    ax.set_title(f"UDP Round-Trip Latency Over Time{title_suffix}", fontsize=13, fontweight="bold")
    ax.legend(title="Device IP", loc="upper right")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)

    fig.tight_layout()
    path = os.path.join(output_dir, "fig1_rtt_timeseries.png")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"  [saved] {path}")
    return path


def plot_histogram(data: dict[str, list[float]], output_dir: str, title_suffix: str = ""):
    """Fig 2: RTT distribution histogram."""
    fig, ax = plt.subplots(figsize=(8, 5))

    for ip, rtts in data.items():
        ax.hist(rtts, bins=50, alpha=0.6, edgecolor="black", linewidth=0.5, label=ip)

    ax.set_xlabel("Round-Trip Time (ms)", fontsize=12)
    ax.set_ylabel("Frequency", fontsize=12)
    ax.set_title(f"RTT Distribution{title_suffix}", fontsize=13, fontweight="bold")
    ax.legend(title="Device IP")
    ax.grid(True, alpha=0.3, axis="y")

    fig.tight_layout()
    path = os.path.join(output_dir, "fig2_rtt_histogram.png")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"  [saved] {path}")
    return path


def plot_cdf(data: dict[str, list[float]], output_dir: str, title_suffix: str = ""):
    """Fig 3: Cumulative Distribution Function of RTT."""
    fig, ax = plt.subplots(figsize=(8, 5))

    for ip, rtts in data.items():
        sorted_rtts = np.sort(rtts)
        cdf = np.arange(1, len(sorted_rtts) + 1) / len(sorted_rtts)
        ax.plot(sorted_rtts, cdf, linewidth=2, label=ip)

    # Reference lines
    ax.axhline(y=0.50, linestyle=":", alpha=0.4, color="gray", label="P50")
    ax.axhline(y=0.95, linestyle=":", alpha=0.4, color="orange", label="P95")
    ax.axhline(y=0.99, linestyle=":", alpha=0.4, color="red", label="P99")

    ax.set_xlabel("Round-Trip Time (ms)", fontsize=12)
    ax.set_ylabel("Cumulative Probability", fontsize=12)
    ax.set_title(f"CDF of Round-Trip Latency{title_suffix}", fontsize=13, fontweight="bold")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1.02)

    fig.tight_layout()
    path = os.path.join(output_dir, "fig3_rtt_cdf.png")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"  [saved] {path}")
    return path


def plot_boxplot(data: dict[str, list[float]], output_dir: str, title_suffix: str = ""):
    """Fig 4: Box plot comparing devices."""
    fig, ax = plt.subplots(figsize=(6, 5))

    labels = list(data.keys())
    values = [data[ip] for ip in labels]

    bp = ax.boxplot(values, tick_labels=labels, patch_artist=True, showmeans=True,
                    meanprops=dict(marker="D", markerfacecolor="gold", markersize=6),
                    flierprops=dict(marker="o", markerfacecolor="red", markersize=4, alpha=0.5))

    colors = plt.cm.Set2(np.linspace(0, 1, len(labels)))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_xlabel("Device", fontsize=12)
    ax.set_ylabel("Round-Trip Time (ms)", fontsize=12)
    ax.set_title(f"RTT Distribution per Device{title_suffix}", fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3, axis="y")

    fig.tight_layout()
    path = os.path.join(output_dir, "fig4_rtt_boxplot.png")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"  [saved] {path}")
    return path


def generate_stats_table(data: dict[str, list[float]], output_dir: str):
    """Generate a summary statistics CSV and LaTeX table."""
    rows = []
    for ip, rtts in sorted(data.items()):
        s = compute_stats(rtts)
        rows.append({
            "Device": ip,
            "N": s["n"],
            "Min (ms)": f"{s['min']:.2f}",
            "Mean (ms)": f"{s['mean']:.2f}",
            "Median (ms)": f"{s['median']:.2f}",
            "P95 (ms)": f"{s['p95']:.2f}",
            "P99 (ms)": f"{s['p99']:.2f}",
            "Max (ms)": f"{s['max']:.2f}",
            "Jitter (ms)": f"{s['jitter']:.2f}",
        })

    # CSV
    csv_path = os.path.join(output_dir, "summary_statistics.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  [saved] {csv_path}")

    # LaTeX table
    tex_path = os.path.join(output_dir, "summary_table.tex")
    with open(tex_path, "w") as f:
        f.write("\\begin{table}[h]\n")
        f.write("\\centering\n")
        f.write("\\caption{UDP Round-Trip Latency Statistics (Architecture~1)}\n")
        f.write("\\label{tab:arch1_latency}\n")
        cols = "l" + "r" * (len(rows[0]) - 1)
        f.write(f"\\begin{{tabular}}{{{cols}}}\n")
        f.write("\\toprule\n")
        headers = list(rows[0].keys())
        f.write(" & ".join(headers) + " \\\\\n")
        f.write("\\midrule\n")
        for row in rows:
            f.write(" & ".join(str(v) for v in row.values()) + " \\\\\n")
        f.write("\\bottomrule\n")
        f.write("\\end{tabular}\n")
        f.write("\\end{table}\n")
    print(f"  [saved] {tex_path}")

    # Print to console
    print("\n  ┌─ Summary Statistics ─────────────────────────────────────────┐")
    for row in rows:
        print(f"  │ {row['Device']:>15} │ n={row['N']:>4} │ "
              f"min={row['Min (ms)']:>7} │ avg={row['Mean (ms)']:>7} │ "
              f"p95={row['P95 (ms)']:>7} │ max={row['Max (ms)']:>7} │ "
              f"jitter={row['Jitter (ms)']:>7} │")
    print("  └────────────────────────────────────────────────────────────────┘")


def main():
    parser = argparse.ArgumentParser(description="Analyze ping test results")
    parser.add_argument("files", nargs="*", help="CSV files to analyze")
    parser.add_argument("--all", action="store_true", help="Combine all CSVs in test_results/")
    parser.add_argument("--output", type=str, default="test_results/figures", help="Output directory")
    args = parser.parse_args()

    # Find CSV files
    if args.files:
        csv_files = args.files
    elif args.all:
        csv_files = sorted(glob.glob("test_results/*_test_*.csv"))
    else:
        # Latest file
        candidates = sorted(glob.glob("test_results/*_test_*.csv"))
        if not candidates:
            print("No CSV files found in test_results/. Run a ping or hardware test first.")
            sys.exit(1)
        csv_files = [candidates[-1]]

    print(f"\n{'='*60}")
    print(f"  Analyzing {len(csv_files)} file(s)")
    print(f"{'='*60}\n")

    # Load and merge data
    merged: dict[str, list[float]] = {}
    for f in csv_files:
        print(f"  Loading: {f}")
        file_data = load_csv(f)
        for ip, rtts in file_data.items():
            merged.setdefault(ip, []).extend(rtts)

    if not merged:
        print("  No data found in CSV files.")
        sys.exit(1)

    # Generate output
    os.makedirs(args.output, exist_ok=True)
    suffix = f" (n={sum(len(v) for v in merged.values())})"

    print(f"\n  Generating figures in {args.output}/\n")
    plot_timeseries(merged, args.output, suffix)
    plot_histogram(merged, args.output, suffix)
    plot_cdf(merged, args.output, suffix)
    plot_boxplot(merged, args.output, suffix)
    generate_stats_table(merged, args.output)

    print(f"\n{'='*60}")
    print(f"  Done! All figures saved to {args.output}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

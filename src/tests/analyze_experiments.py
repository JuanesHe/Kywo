import csv
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl

# Set Arial font for publication
mpl.rcParams['font.family'] = 'Arial'
mpl.rcParams['axes.titlesize'] = 14
mpl.rcParams['axes.labelsize'] = 12
mpl.rcParams['xtick.labelsize'] = 10
mpl.rcParams['ytick.labelsize'] = 10
mpl.rcParams['legend.fontsize'] = 11

def load_ping_data(filepath):
    seqs = []
    rtts = []
    ips = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            seqs.append(int(row['seq']))
            ips.append(row['device_ip'])
            rtts.append(float(row['rtt_ms']))
    return np.array(seqs), np.array(ips), np.array(rtts)

def load_sync_data(filepath):
    samples = []
    drifts = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples.append(int(row['sample']))
            drifts.append(float(row['drift_us']))
    return np.array(samples), np.array(drifts)

def main():
    # File paths
    base_dir = '/Users/juanes/Documents/Kywo/test_results'
    f_ping = os.path.join(base_dir, 'ping_test_20260316_104917.csv')
    f_arch1 = os.path.join(base_dir, 'arch1_latency_sync_test_20260316_104328')
    f_arch2 = os.path.join(base_dir, 'arch2_sync_test_20260316_132711.csv')
    
    output_dir = os.path.join(base_dir, 'publication_figures')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 1. Load Data
    p_seqs, p_ips, p_rtts = load_ping_data(f_ping)
    a1_samples, a1_drifts = load_sync_data(f_arch1)
    a2_samples, a2_drifts = load_sync_data(f_arch2)

    # 2. Figure 1: Architecture 1 - Software Ping-Pong Latency
    # 1:2 relationship (Height:Width) -> figsize=(12, 6)
    fig1, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))

    unique_ips = np.unique(p_ips)
    colors = ['#1f77b4', '#ff7f0e']
    
    for idx, ip in enumerate(unique_ips):
        mask = (p_ips == ip)
        
        # Plot Time Series
        ax1.plot(p_seqs[mask], p_rtts[mask], marker='o', linestyle='-', 
                 markersize=3, alpha=0.7, label=f'Edge Node ({ip})', color=colors[idx])
        
        # Plot Histogram
        ax2.hist(p_rtts[mask], bins=30, alpha=0.6, label=f'Edge Node ({ip})', color=colors[idx])

    ax1.set_title('Ping Round-Trip Latency Over Time')
    ax1.set_xlabel('Sequence Number')
    ax1.set_ylabel('Round-Trip Time (ms)')
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.legend()

    ax2.set_title('Ping Round-Trip Latency Distribution')
    ax2.set_xlabel('Round-Trip Time (ms)')
    ax2.set_ylabel('Frequency')
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax2.legend()

    plt.tight_layout()
    fig1_path = os.path.join(output_dir, 'fig1_ping_latency.png')
    fig1.savefig(fig1_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {fig1_path}")

    # 3. Figure 2: Architecture 1 vs Architecture 2 Synchronization Drift
    fig2, (ax3, ax4) = plt.subplots(1, 2, figsize=(12, 6))

    # Absolute drift arrays
    abs_drift_a1 = np.abs(a1_drifts)
    abs_drift_a2 = np.abs(a2_drifts)
    
    # Plot 1: Time Series comparison 
    ax3.plot(a1_samples, abs_drift_a1, marker='^', linestyle='-', 
             markersize=3, alpha=0.8, color='crimson', label='Architecture 1 (UDP)')
    ax3.plot(a2_samples, abs_drift_a2, marker='s', linestyle='-', 
             markersize=3, alpha=0.8, color='navy', label='Architecture 2 (ESP-NOW)')
             
    ax3.set_title('Absolute Synchronization Skew Over Time')
    ax3.set_xlabel('Pulse Sample Number')
    ax3.set_ylabel('Absolute Skew (µs)')
    ax3.grid(True, linestyle='--', alpha=0.5)
    ax3.legend()

    # Plot 2: Violin plot comparison
    data_to_plot = [abs_drift_a1, abs_drift_a2]
    parts = ax4.violinplot(data_to_plot, showmeans=True, showextrema=True, showmedians=True)
    
    parts['bodies'][0].set_facecolor('crimson')
    parts['bodies'][1].set_facecolor('navy')
    for pc in parts['bodies']:
        pc.set_edgecolor('black')
        pc.set_alpha(0.6)

    ax4.set_xticks([1, 2])
    ax4.set_xticklabels(['Arch 1 (UDP)', 'Arch 2 (ESP-NOW)'])
    ax4.set_title('Distribution of Synchronization Skew')
    ax4.set_ylabel('Absolute Skew (µs)')
    ax4.grid(True, axis='y', linestyle='--', alpha=0.5)

    plt.tight_layout()
    fig2_path = os.path.join(output_dir, 'fig2_sync_comparison.png')
    fig2.savefig(fig2_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {fig2_path}")

    # Calculate Summary Statistics for printing
    print("\n--- Summary Statistics ---")
    print(f"Arch 1 Avg Skew : {np.mean(abs_drift_a1):.2f} µs | Std: {np.std(abs_drift_a1):.2f} µs | Max: {np.max(abs_drift_a1):.0f} µs")
    print(f"Arch 2 Avg Skew : {np.mean(abs_drift_a2):.2f} µs | Std: {np.std(abs_drift_a2):.2f} µs | Max: {np.max(abs_drift_a2):.0f} µs")
    
if __name__ == '__main__':
    main()

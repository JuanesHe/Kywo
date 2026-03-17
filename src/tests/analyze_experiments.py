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

def load_hardware_latency_data(filepath):
    samples = []
    lat_a = []
    lat_b = []
    drifts = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if 'latency_a_us' in row and row['latency_a_us']:
                samples.append(int(row['sample']))
                lat_a.append(float(row['latency_a_us']))
                lat_b.append(float(row['latency_b_us']))
                if 'drift_us' in row:
                    drifts.append(float(row['drift_us']))
    return np.array(samples), np.array(lat_a), np.array(lat_b), np.array(drifts)

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
    base_dir = r'c:\Users\jehm\Documents\kywoSystem\test_results'
    f_ping = os.path.join(base_dir, 'ping_test_20260316_104917.csv')
    f_arch1 = os.path.join(base_dir, 'arch1_latency_sync_test_20260316_104328.csv')
    f_arch2 = os.path.join(base_dir, 'arch2_sync_test_20260316_132711.csv')
    
    output_dir = os.path.join(base_dir, 'publication_figures')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 1. Load Data
    p_seqs, p_ips, p_rtts = load_ping_data(f_ping)
    a1_samples, a1_drifts = load_sync_data(f_arch1)
    a2_samples, a2_drifts = load_sync_data(f_arch2)

    # 2. Figure 1: Architecture 1 - Software Ping-Pong Latency
    # 1:2 relationship (Height:Width) -> Subplots are 8x4 -> figsize=(16, 4)
    fig1, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 4))

    unique_ips = np.unique(p_ips)
    colors = ['crimson', 'navy']
    
    rtts_list = []
    labels_list = []
    
    for idx, ip in enumerate(unique_ips):
        mask = (p_ips == ip)
        
        device_label = 'Device A' if ip == '192.168.0.102' else 'Device B'
        
        # Plot Time Series
        ax1.plot(p_seqs[mask], p_rtts[mask], marker='o', linestyle='-', 
                 markersize=3, alpha=0.7, label=device_label, color=colors[idx])
        
        rtts_list.append(p_rtts[mask])
        labels_list.append(device_label)

    ax1.set_title('Ping Round-Trip Latency Over Time')
    ax1.set_xlabel('Sequence Number')
    ax1.set_ylabel('Round-Trip Time (ms)')
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.legend()

    # Plot Distribution (Boxplot without outliers)
    bp_1 = ax2.boxplot(rtts_list, patch_artist=True, showfliers=False, tick_labels=labels_list)
    
    for patch, color in zip(bp_1['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    ax2.set_title('Ping Latency Distribution (No Outliers)')
    ax2.set_ylabel('Round-Trip Time (ms)')
    ax2.grid(True, axis='y', linestyle='--', alpha=0.5)

    plt.tight_layout()
    fig1_path = os.path.join(output_dir, 'fig1_ping_latency.png')
    fig1.savefig(fig1_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {fig1_path}")

    # 3. Figure 2: Architecture 1 - Hardware Observer Latency
    h_samples, h_lat_a, h_lat_b, h_drifts = load_hardware_latency_data(f_arch1)
    
    fig2, (ax_h1, ax_h2) = plt.subplots(1, 2, figsize=(16, 4))

    # Plot Time Series
    ax_h1.plot(h_samples, h_lat_a / 1000.0, marker='o', linestyle='-', markersize=3, alpha=0.7, label='Device A', color='crimson')
    ax_h1.plot(h_samples, h_lat_b / 1000.0, marker='s', linestyle='-', markersize=3, alpha=0.7, label='Device B', color='navy')
    ax_h1.set_title('Hardware Observer Latency Over Time')
    ax_h1.set_xlabel('Sample Number')
    ax_h1.set_ylabel('Latency (ms)')
    ax_h1.grid(True, linestyle='--', alpha=0.5)
    ax_h1.legend()

    # Plot Distribution (Boxplot without outliers)
    bp_h = ax_h2.boxplot([h_lat_a / 1000.0, h_lat_b / 1000.0], patch_artist=True, showfliers=False, tick_labels=['Device A', 'Device B'])
    
    colors_h = ['crimson', 'navy']
    for patch, color in zip(bp_h['boxes'], colors_h):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
        
    ax_h2.set_title('Hardware Latency Distribution (No Outliers)')
    ax_h2.set_ylabel('Latency (ms)')
    ax_h2.grid(True, axis='y', linestyle='--', alpha=0.5)

    plt.tight_layout()
    fig2_path = os.path.join(output_dir, 'fig2_hardware_latency.png')
    fig2.savefig(fig2_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {fig2_path}")

    # 4. Figure 3: Architecture 1 vs Architecture 2 Synchronization Drift
    fig3, (ax3, ax4) = plt.subplots(1, 2, figsize=(16, 4))

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

    # Plot 2: Boxplot comparison without outliers instead of Violin plots
    data_to_plot = [abs_drift_a1, abs_drift_a2]
    bp = ax4.boxplot(data_to_plot, patch_artist=True, showfliers=False, tick_labels=['Arch 1 (UDP)', 'Arch 2 (ESP-NOW)'])
    
    colors = ['crimson', 'navy']
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    ax4.set_title('Distribution of Sync Skew (No Outliers)')
    ax4.set_ylabel('Absolute Skew (µs)')
    ax4.grid(True, axis='y', linestyle='--', alpha=0.5)

    plt.tight_layout()
    fig3_path = os.path.join(output_dir, 'fig3_sync_comparison.png')
    fig3.savefig(fig3_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {fig3_path}")

    # 5. Figure 4: Latency vs Sync Skew Scatter Plot (Architecture 1)
    fig4, ax5 = plt.subplots(figsize=(8, 6))
    
    # Calculate average latency between A and B
    avg_latency = (h_lat_a + h_lat_b) / 2.0 / 1000.0 # mostly for general latency scale (ms)
    abs_h_drifts = np.abs(h_drifts)
    
    scatter = ax5.scatter(avg_latency, abs_h_drifts, c=avg_latency, cmap='viridis', alpha=0.7, edgecolors='k')
    ax5.set_title('Average Hardware Latency vs. Synchronization Skew (Arch 1)')
    ax5.set_xlabel('Average Hardware Latency (ms)')
    ax5.set_ylabel('Absolute Synchronization Skew (µs)')
    ax5.grid(True, linestyle='--', alpha=0.5)
    
    cbar = fig4.colorbar(scatter, ax=ax5)
    cbar.set_label('Average Latency (ms)')
    
    plt.tight_layout()
    fig4_path = os.path.join(output_dir, 'fig4_latency_vs_skew_scatter.png')
    fig4.savefig(fig4_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {fig4_path}")

    # Calculate Summary Statistics and write to file
    tables_path = os.path.join(output_dir, 'latex_tables.txt')
    with open(tables_path, 'w') as f_out:
        f_out.write("% Table 1: Synchronization Drift Statistics\n")
        f_out.write("\\begin{table}[htpb]\n")
        f_out.write("\\centering\n")
        f_out.write("\\caption{Synchronization Drift Comparison (µs)}\n")
        f_out.write("\\begin{tabular}{|l|c|c|c|c|c|}\n")
        f_out.write("\\hline\n")
        f_out.write("\\textbf{Architecture} & \\textbf{Mean} & \\textbf{Median} & \\textbf{Std Dev} & \\textbf{Min} & \\textbf{Max} \\\\ \\hline\n")
        f_out.write(f"Arch 1 (UDP) & {np.mean(abs_drift_a1):.2f} & {np.median(abs_drift_a1):.2f} & {np.std(abs_drift_a1):.2f} & {np.min(abs_drift_a1):.0f} & {np.max(abs_drift_a1):.0f} \\\\ \\hline\n")
        f_out.write(f"Arch 2 (ESP-NOW) & {np.mean(abs_drift_a2):.2f} & {np.median(abs_drift_a2):.2f} & {np.std(abs_drift_a2):.2f} & {np.min(abs_drift_a2):.0f} & {np.max(abs_drift_a2):.0f} \\\\ \\hline\n")
        f_out.write("\\end{tabular}\n")
        f_out.write("\\label{tab:sync_drift}\n")
        f_out.write("\\end{table}\n\n")
        
        # --- Table 2: Hardware Latency Statistics ---
        lat_a_ms = h_lat_a / 1000.0
        lat_b_ms = h_lat_b / 1000.0
        
        f_out.write("% Table 2: Hardware Latency Statistics\n")
        f_out.write("\\begin{table}[htpb]\n")
        f_out.write("\\centering\n")
        f_out.write("\\caption{Hardware Latency Statistics for Architecture 1 (ms)}\n")
        f_out.write("\\begin{tabular}{|l|c|c|c|c|c|}\n")
        f_out.write("\\hline\n")
        f_out.write("\\textbf{Device} & \\textbf{Mean} & \\textbf{Median} & \\textbf{Std Dev} & \\textbf{Min} & \\textbf{Max} \\\\ \\hline\n")
        f_out.write(f"Device A & {np.mean(lat_a_ms):.2f} & {np.median(lat_a_ms):.2f} & {np.std(lat_a_ms):.2f} & {np.min(lat_a_ms):.2f} & {np.max(lat_a_ms):.2f} \\\\ \\hline\n")
        f_out.write(f"Device B & {np.mean(lat_b_ms):.2f} & {np.median(lat_b_ms):.2f} & {np.std(lat_b_ms):.2f} & {np.min(lat_b_ms):.2f} & {np.max(lat_b_ms):.2f} \\\\ \\hline\n")
        f_out.write("\\end{tabular}\n")
        f_out.write("\\label{tab:hw_latency}\n")
        f_out.write("\\end{table}\n\n")
        
        # --- Table 3: Ping Latency Statistics ---
        f_out.write("% Table 3: Ping Latency Statistics\n")
        f_out.write("\\begin{table}[htpb]\n")
        f_out.write("\\centering\n")
        f_out.write("\\caption{Software Ping Latency Statistics (ms)}\n")
        f_out.write("\\begin{tabular}{|l|c|c|c|c|c|}\n")
        f_out.write("\\hline\n")
        f_out.write("\\textbf{Device} & \\textbf{Mean} & \\textbf{Median} & \\textbf{Std Dev} & \\textbf{Min} & \\textbf{Max} \\\\ \\hline\n")
        for idx, ip in enumerate(unique_ips):
            mask = (p_ips == ip)
            dev_rtts = p_rtts[mask]
            device_label = 'Device A' if ip == '192.168.0.102' else 'Device B'
            f_out.write(f"{device_label} & {np.mean(dev_rtts):.2f} & {np.median(dev_rtts):.2f} & {np.std(dev_rtts):.2f} & {np.min(dev_rtts):.2f} & {np.max(dev_rtts):.2f} \\\\ \\hline\n")
        f_out.write("\\end{tabular}\n")
        f_out.write("\\label{tab:ping_latency}\n")
        f_out.write("\\end{table}\n")

    print(f"Saved LaTeX tables to: {tables_path}")
    
    # Generate Test Summary Tables in LaTeX Format
    summary_path = os.path.join(output_dir, 'test_summary_tables.tex')
    with open(summary_path, 'w', encoding='utf-8') as f_sum:
        f_sum.write("% KYWO SYSTEM - EXPERIMENTAL TEST SUMMARY TABLES\n")
        f_sum.write("% Date: March 16, 2026\n")
        f_sum.write("% Copy and paste these tables into your LaTeX document\n\n")
        
        # --- Test 0 Description and Results ---
        f_sum.write("% Test 0: Software Ping-Pong Description\n")
        f_sum.write("% This test measures round-trip latency and inter-device synchronization using\n")
        f_sum.write("% software timestamps. The PC broadcasts a UDP packet to both edge nodes simultaneously,\n")
        f_sum.write("% and each node responds with an acknowledgment. Software drift is calculated as the\n")
        f_sum.write("% timing difference between the two device responses, providing a software-based\n")
        f_sum.write("% estimate of synchronization quality.\n\n")
        
        # Calculate software drift statistics
        # Group by sequence number to find pairs
        unique_seqs = np.unique(p_seqs)
        software_drifts = []
        for seq in unique_seqs:
            mask = (p_seqs == seq)
            if np.sum(mask) == 2:  # Both devices responded
                times = p_rtts[mask]
                drift = np.abs(times[0] - times[1])
                software_drifts.append(drift)
        software_drifts = np.array(software_drifts)
        
        # Test 0 Enhanced Results Table with Drift
        f_sum.write("% Table: Test 0 - Software Ping-Pong Results (Architecture 1)\n")
        f_sum.write("\\begin{table}[htbp]\n")
        f_sum.write("\\centering\n")
        f_sum.write("\\caption{Test 0: Software Ping-Pong Round-Trip Latency and Drift}\n")
        f_sum.write("\\begin{tabular}{|l|c|c|c|c|c|c|}\n")
        f_sum.write("\\hline\n")
        f_sum.write("\\textbf{Metric} & \\textbf{Mean} & \\textbf{Median} & \\textbf{Std Dev} & \\textbf{Range} & \\textbf{P95} & \\textbf{P99} \\\\ \\hline\n")
        for idx, ip in enumerate(unique_ips):
            mask = (p_ips == ip)
            dev_rtts = p_rtts[mask]
            device_label = 'Device A RTT (ms)' if ip == '192.168.0.102' else 'Device B RTT (ms)'
            f_sum.write(f"{device_label} & {np.mean(dev_rtts):.2f} & {np.median(dev_rtts):.2f} & {np.std(dev_rtts):.2f} & {np.min(dev_rtts):.2f}--{np.max(dev_rtts):.2f} & {np.percentile(dev_rtts, 95):.2f} & {np.percentile(dev_rtts, 99):.2f} \\\\ \\hline\n")
        f_sum.write(f"Software Drift (ms) & {np.mean(software_drifts):.2f} & {np.median(software_drifts):.2f} & {np.std(software_drifts):.2f} & {np.min(software_drifts):.2f}--{np.max(software_drifts):.2f} & {np.percentile(software_drifts, 95):.2f} & {np.percentile(software_drifts, 99):.2f} \\\\ \\hline\n")
        f_sum.write("\\end{tabular}\n")
        f_sum.write("\\label{tab:test0_results}\n")
        f_sum.write("\\end{table}\n\n")
        
        # --- Test 1 Description and Combined Results ---
        f_sum.write("% Test 1: Hardware Observer - Architecture 1 Description\n")
        f_sum.write("% This test uses a hardware observer with microsecond-precision interrupts to measure\n")
        f_sum.write("% ground truth latency and synchronization. The PC triggers the observer and broadcasts\n")
        f_sum.write("% a UDP packet to both edge nodes. Each node responds by setting a GPIO pin HIGH, which\n")
        f_sum.write("% the observer captures via hardware interrupts. This eliminates software timestamp\n")
        f_sum.write("% inaccuracies and provides the true physical synchronization between devices.\n\n")
        
        # Test 1 Combined Results Table
        lat_a_ms = h_lat_a / 1000.0
        lat_b_ms = h_lat_b / 1000.0
        abs_h_drift = np.abs(h_drifts)
        
        f_sum.write("% Table: Test 1 - Complete Hardware Observer Results (Architecture 1)\n")
        f_sum.write("\\begin{table}[htbp]\n")
        f_sum.write("\\centering\n")
        f_sum.write("\\caption{Test 1: Hardware Observer Latency and Synchronization (Architecture 1)}\n")
        f_sum.write("\\begin{tabular}{|l|c|c|c|c|c|c|}\n")
        f_sum.write("\\hline\n")
        f_sum.write("\\textbf{Metric} & \\textbf{Mean} & \\textbf{Median} & \\textbf{Std Dev} & \\textbf{Range} & \\textbf{P95} & \\textbf{P99} \\\\ \\hline\n")
        f_sum.write(f"Device A Latency (ms) & {np.mean(lat_a_ms):.2f} & {np.median(lat_a_ms):.2f} & {np.std(lat_a_ms):.2f} & {np.min(lat_a_ms):.2f}--{np.max(lat_a_ms):.2f} & {np.percentile(lat_a_ms, 95):.2f} & {np.percentile(lat_a_ms, 99):.2f} \\\\ \\hline\n")
        f_sum.write(f"Device B Latency (ms) & {np.mean(lat_b_ms):.2f} & {np.median(lat_b_ms):.2f} & {np.std(lat_b_ms):.2f} & {np.min(lat_b_ms):.2f}--{np.max(lat_b_ms):.2f} & {np.percentile(lat_b_ms, 95):.2f} & {np.percentile(lat_b_ms, 99):.2f} \\\\ \\hline\n")
        f_sum.write(f"Sync Drift ($\\mu$s) & {np.mean(abs_h_drift):.2f} & {np.median(abs_h_drift):.2f} & {np.std(abs_h_drift):.2f} & {np.min(abs_h_drift):.0f}--{np.max(abs_h_drift):.0f} & {np.percentile(abs_h_drift, 95):.2f} & {np.percentile(abs_h_drift, 99):.2f} \\\\ \\hline\n")
        f_sum.write("\\end{tabular}\n")
        f_sum.write("\\label{tab:test1_results}\n")
        f_sum.write("\\end{table}\n\n")
        
        # --- Test 2 Description and Results ---
        f_sum.write("% Test 2: Hardware Observer - Architecture 2 Description\n")
        f_sum.write("% This test measures synchronization drift in autonomous operation. Two edge nodes run\n")
        f_sum.write("% independent state machines (grandmaster and follower) that execute sequences without\n")
        f_sum.write("% centralized control. The hardware observer passively monitors GPIO timing between the\n")
        f_sum.write("% two nodes. ESP-NOW clock synchronization occurs every 2000ms to correct for hardware\n")
        f_sum.write("% clock drift. This test reveals the long-term stability of distributed execution.\n\n")
        
        # Test 2 Results Table
        f_sum.write("% Table: Test 2 - Hardware Observer Results (Architecture 2)\n")
        f_sum.write("\\begin{table}[htbp]\n")
        f_sum.write("\\centering\n")
        f_sum.write("\\caption{Test 2: Synchronization Drift in Autonomous Execution (Architecture 2)}\n")
        f_sum.write("\\begin{tabular}{|l|c|c|c|c|c|c|}\n")
        f_sum.write("\\hline\n")
        f_sum.write("\\textbf{Metric} & \\textbf{Mean} & \\textbf{Median} & \\textbf{Std Dev} & \\textbf{Range} & \\textbf{P95} & \\textbf{P99} \\\\ \\hline\n")
        f_sum.write(f"Sync Drift ($\\mu$s) & {np.mean(abs_drift_a2):.2f} & {np.median(abs_drift_a2):.2f} & {np.std(abs_drift_a2):.2f} & {np.min(abs_drift_a2):.0f}--{np.max(abs_drift_a2):.0f} & {np.percentile(abs_drift_a2, 95):.2f} & {np.percentile(abs_drift_a2, 99):.2f} \\\\ \\hline\n")
        f_sum.write("\\end{tabular}\n")
        f_sum.write("\\label{tab:test2_results}\n")
        f_sum.write("\\end{table}\n\n")
        
        # --- Comparative Analysis Table ---
        f_sum.write("% Table: Comparative Analysis\n")
        f_sum.write("\\begin{table}[htbp]\n")
        f_sum.write("\\centering\n")
        f_sum.write("\\caption{Comparative Analysis: Architecture 1 vs Architecture 2 Synchronization Performance}\n")
        f_sum.write("\\begin{tabular}{|l|c|c|c|}\n")
        f_sum.write("\\hline\n")
        f_sum.write("\\textbf{Metric} & \\textbf{Arch 1 (UDP)} & \\textbf{Arch 2 (ESP-NOW)} & \\textbf{Ratio (A2/A1)} \\\\ \\hline\n")
        ratio_mean = np.mean(abs_drift_a2) / np.mean(abs_drift_a1)
        ratio_median = np.median(abs_drift_a2) / np.median(abs_drift_a1)
        ratio_std = np.std(abs_drift_a2) / np.std(abs_drift_a1)
        ratio_max = np.max(abs_drift_a2) / np.max(abs_drift_a1)
        ratio_p95 = np.percentile(abs_drift_a2, 95) / np.percentile(abs_drift_a1, 95)
        ratio_p99 = np.percentile(abs_drift_a2, 99) / np.percentile(abs_drift_a1, 99)
        f_sum.write(f"Mean Drift ($\\mu$s) & {np.mean(abs_drift_a1):.2f} & {np.mean(abs_drift_a2):.2f} & {ratio_mean:.1f}$\\times$ \\\\ \\hline\n")
        f_sum.write(f"Median Drift ($\\mu$s) & {np.median(abs_drift_a1):.2f} & {np.median(abs_drift_a2):.2f} & {ratio_median:.1f}$\\times$ \\\\ \\hline\n")
        f_sum.write(f"Std Dev ($\\mu$s) & {np.std(abs_drift_a1):.2f} & {np.std(abs_drift_a2):.2f} & {ratio_std:.1f}$\\times$ \\\\ \\hline\n")
        f_sum.write(f"Max Drift ($\\mu$s) & {np.max(abs_drift_a1):.0f} & {np.max(abs_drift_a2):.0f} & {ratio_max:.1f}$\\times$ \\\\ \\hline\n")
        f_sum.write(f"P95 Drift ($\\mu$s) & {np.percentile(abs_drift_a1, 95):.2f} & {np.percentile(abs_drift_a2, 95):.2f} & {ratio_p95:.1f}$\\times$ \\\\ \\hline\n")
        f_sum.write(f"P99 Drift ($\\mu$s) & {np.percentile(abs_drift_a1, 99):.2f} & {np.percentile(abs_drift_a2, 99):.2f} & {ratio_p99:.1f}$\\times$ \\\\ \\hline\n")
        f_sum.write("\\end{tabular}\n")
        f_sum.write("\\label{tab:comparative_analysis}\n")
        f_sum.write("\\end{table}\n\n")
        
        # Add conclusions as a text block
        f_sum.write("% Key Findings (use in document text):\n")
        f_sum.write("% Architecture 1 achieves " + f"{ratio_mean:.1f}" + "$\\times$ better mean synchronization\n")
        f_sum.write("% Architecture 1 has " + f"{ratio_std:.1f}" + "$\\times$ more stable timing (lower std dev)\n")
        f_sum.write("% Architecture 1 worst-case drift: " + f"{np.max(abs_drift_a1):.0f}" + " $\\mu$s\n")
        f_sum.write("% Architecture 2 worst-case drift: " + f"{np.max(abs_drift_a2):.0f}" + " $\\mu$s (" + f"{ratio_max:.1f}" + "$\\times$ worse)\n")
        
    print(f"Saved test summary tables (LaTeX format) to: {summary_path}")
    
if __name__ == '__main__':
    main()

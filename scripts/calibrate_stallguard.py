#!/usr/bin/env python3
# Stallguard calibration data graphing tool
#
# Copyright (C) 2024
# This file may be distributed under the terms of the GNU GPLv3 license.

import sys
import os
import argparse

# Optional plotly import for interactive HTML graphs
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


def load_csv(filename):
    times, sg_results, cs_actuals, velocities = [], [], [], []
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) >= 3:
                try:
                    times.append(float(parts[0]))
                    sg_results.append(int(parts[1]))
                    cs_actuals.append(int(parts[2]))
                    # Velocity column (backward compatible)
                    if len(parts) >= 4:
                        velocities.append(float(parts[3]))
                    else:
                        velocities.append(0.0)
                except ValueError:
                    continue
    return times, sg_results, cs_actuals, velocities


def generate_basic_graph(csv_file, output_file, times, sg_results, cs_actuals,
                         show=False):
    """Generate the original graph with SG result and CS actual subplots."""
    try:
        import matplotlib
        if output_file and not show:
            matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("Error: matplotlib not installed. "
              "Install with: pip install matplotlib")
        sys.exit(1)

    # Create figure with 2 subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    basename = os.path.basename(csv_file)
    if '_' in basename:
        stepper_name = basename.rsplit('_', 1)[0]
    else:
        stepper_name = basename.rsplit('.', 1)[0] if '.' in basename else basename
    fig.suptitle('Stallguard Measurement: %s' % stepper_name, fontsize=14)

    # Plot SG result
    ax1.plot(times, sg_results, 'b-', linewidth=0.5, alpha=0.7)
    ax1.set_ylabel('SG Result')
    ax1.set_title('Stallguard Value (higher = less load)')
    ax1.grid(True, alpha=0.3)

    # Add statistics
    sg_valid = [v for v in sg_results if v >= 0]
    if sg_valid:
        sg_min = min(sg_valid)
        sg_max = max(sg_valid)
        sg_avg = sum(sg_valid) / len(sg_valid)
        ax1.axhline(y=sg_avg, color='r', linestyle='--',
                    label='avg=%.1f (min=%d, max=%d)' % (sg_avg, sg_min, sg_max))
        ax1.legend(loc='upper right')
        # Set y-axis limits with some padding
        padding = (sg_max - sg_min) * 0.1 if sg_max != sg_min else 50
        ax1.set_ylim(max(0, sg_min - padding), sg_max + padding)

    # Plot CS actual
    ax2.plot(times, cs_actuals, 'g-', linewidth=0.5, alpha=0.7)
    ax2.set_ylabel('CS Actual')
    ax2.set_xlabel('Time (s)')
    ax2.set_title('Current Scale')
    ax2.grid(True, alpha=0.3)

    # Add CS statistics
    cs_valid = [v for v in cs_actuals if v >= 0]
    if cs_valid:
        cs_min = min(cs_valid)
        cs_max = max(cs_valid)
        cs_avg = sum(cs_valid) / len(cs_valid)
        ax2.axhline(y=cs_avg, color='r', linestyle='--',
                    label='avg=%.1f (min=%d, max=%d)' % (cs_avg, cs_min, cs_max))
        ax2.legend(loc='upper right')

    plt.tight_layout()

    if output_file:
        plt.savefig(output_file, dpi=150)
        print("Graph saved to: %s" % output_file)

    if show:
        plt.show()

    plt.close()


def generate_velocity_graph(csv_file, output_file, times, sg_results,
                            velocities, show=False):
    """Generate graph with SG result and velocity on second Y axis."""
    try:
        import matplotlib
        if output_file and not show:
            matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("Error: matplotlib not installed. "
              "Install with: pip install matplotlib")
        sys.exit(1)

    # Single plot with two Y axes
    fig, ax1 = plt.subplots(figsize=(12, 6))

    basename = os.path.basename(csv_file)
    if '_' in basename:
        stepper_name = basename.rsplit('_', 1)[0]
    else:
        stepper_name = basename.rsplit('.', 1)[0] if '.' in basename else basename
    fig.suptitle('Stallguard vs Velocity: %s' % stepper_name, fontsize=14)

    # Left Y axis: SG result (blue)
    color1 = 'tab:blue'
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('SG Result', color=color1)
    line1 = ax1.plot(times, sg_results, color=color1, linewidth=0.5,
                     alpha=0.7, label='SG Result')
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, alpha=0.3)

    # Add SG statistics
    sg_valid = [v for v in sg_results if v >= 0]
    if sg_valid:
        sg_avg = sum(sg_valid) / len(sg_valid)
        ax1.axhline(y=sg_avg, color=color1, linestyle='--', alpha=0.5)

    # Right Y axis: Velocity (red)
    ax2 = ax1.twinx()
    color2 = 'tab:red'
    ax2.set_ylabel('Velocity (mm/s)', color=color2)
    line2 = ax2.plot(times, velocities, color=color2, linewidth=0.5,
                     alpha=0.7, label='Velocity')
    ax2.tick_params(axis='y', labelcolor=color2)

    # Combined legend
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper right')

    plt.tight_layout()

    if output_file:
        plt.savefig(output_file, dpi=150)
        print("Graph saved to: %s" % output_file)

    if show:
        plt.show()

    plt.close()


def generate_html_graph(csv_file, output_file, times, sg_results, cs_actuals,
                        velocities):
    """Generate interactive HTML graph using Plotly."""
    if not PLOTLY_AVAILABLE:
        print("Warning: plotly not installed. Skipping HTML generation.")
        print("Install with: pip install plotly")
        return

    # Extract stepper name from filename
    basename = os.path.basename(csv_file)
    if '_' in basename:
        stepper_name = basename.rsplit('_', 1)[0]
    else:
        stepper_name = basename.rsplit('.', 1)[0] if '.' in basename else basename

    # Create figure with secondary Y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # SG Result trace (left Y-axis, blue)
    fig.add_trace(
        go.Scatter(x=times, y=sg_results, name="SG Result",
                   line=dict(color='#2196F3', width=1),
                   hovertemplate='Time: %{x:.3f}s<br>SG: %{y}<extra></extra>'),
        secondary_y=False)

    # CS Actual trace (left Y-axis, green)
    fig.add_trace(
        go.Scatter(x=times, y=cs_actuals, name="CS Actual",
                   line=dict(color='#4CAF50', width=1),
                   hovertemplate='Time: %{x:.3f}s<br>CS: %{y}<extra></extra>'),
        secondary_y=False)

    # Velocity trace (right Y-axis, red) - only if data exists
    if any(v != 0 for v in velocities):
        fig.add_trace(
            go.Scatter(x=times, y=velocities, name="Velocity",
                       line=dict(color='#F44336', width=1),
                       hovertemplate='Time: %{x:.3f}s<br>Vel: %{y:.1f} mm/s'
                                     '<extra></extra>'),
            secondary_y=True)

    # Calculate and show SG average line
    sg_valid = [v for v in sg_results if v >= 0]
    if sg_valid:
        sg_avg = sum(sg_valid) / len(sg_valid)
        fig.add_hline(y=sg_avg, line_dash="dash", line_color="#2196F3",
                      annotation_text="SG avg: %.1f" % sg_avg,
                      secondary_y=False)

    # Layout configuration
    fig.update_layout(
        title='Stallguard Measurement: %s' % stepper_name,
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        margin=dict(t=80)
    )
    fig.update_xaxes(title_text="Time (s)", showgrid=True)
    fig.update_yaxes(title_text="SG Result / CS Actual", secondary_y=False)
    fig.update_yaxes(title_text="Velocity (mm/s)", secondary_y=True)

    # Write HTML with CDN-hosted Plotly.js
    fig.write_html(output_file, include_plotlyjs='cdn')
    print("Interactive graph saved to: %s" % output_file)


def main():
    parser = argparse.ArgumentParser(
        description='Generate graphs from stallguard CSV data')
    parser.add_argument('csv_file', help='Input CSV file from MEASURE_STALLGUARD')
    parser.add_argument('-o', '--output', help='Output PNG file (base name)')
    parser.add_argument('--show', action='store_true',
                        help='Display graph interactively')
    parser.add_argument('--html', action='store_true',
                        help='Generate interactive HTML graph (requires plotly)')
    args = parser.parse_args()

    if not os.path.exists(args.csv_file):
        print("Error: File not found: %s" % args.csv_file)
        sys.exit(1)

    times, sg_results, cs_actuals, velocities = load_csv(args.csv_file)
    if not times:
        print("Error: No data in CSV file")
        sys.exit(1)

    # Normalize times to start at 0
    t0 = times[0]
    times = [t - t0 for t in times]

    # Determine output base name
    if args.output:
        base_output = args.output.rsplit('.', 1)[0]
    else:
        base_output = args.csv_file.rsplit('.', 1)[0]

    # Graph 1: Original (SG + CS)
    generate_basic_graph(args.csv_file, base_output + '.png',
                         times, sg_results, cs_actuals, args.show)

    # Graph 2: SG + Velocity (only if velocity data exists)
    if any(v != 0 for v in velocities):
        generate_velocity_graph(args.csv_file, base_output + '_velocity.png',
                                times, sg_results, velocities, args.show)

    # Graph 3: Interactive HTML (if requested)
    if args.html:
        generate_html_graph(args.csv_file, base_output + '.html',
                            times, sg_results, cs_actuals, velocities)


if __name__ == '__main__':
    main()

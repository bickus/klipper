#!/usr/bin/env python3
# Stallguard calibration data graphing tool
#
# Copyright (C) 2024
# This file may be distributed under the terms of the GNU GPLv3 license.

import sys
import os
import argparse


def load_csv(filename):
    times, sg_results, cs_actuals = [], [], []
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
                except ValueError:
                    continue
    return times, sg_results, cs_actuals


def generate_graph(csv_file, output_file=None, show=False):
    try:
        import matplotlib
        if output_file and not show:
            matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("Error: matplotlib not installed. "
              "Install with: pip install matplotlib")
        sys.exit(1)

    times, sg_results, cs_actuals = load_csv(csv_file)
    if not times:
        print("Error: No data in CSV file")
        sys.exit(1)

    # Normalize times to start at 0
    t0 = times[0]
    times = [t - t0 for t in times]

    # Create figure with 2 subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    stepper_name = os.path.basename(csv_file).rsplit('_', 1)[0]
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


def main():
    parser = argparse.ArgumentParser(
        description='Generate graphs from stallguard CSV data')
    parser.add_argument('csv_file', help='Input CSV file from MEASURE_STALLGUARD')
    parser.add_argument('-o', '--output', help='Output PNG file')
    parser.add_argument('--show', action='store_true',
                        help='Display graph interactively')
    args = parser.parse_args()

    if not os.path.exists(args.csv_file):
        print("Error: File not found: %s" % args.csv_file)
        sys.exit(1)

    output = args.output
    if not output and not args.show:
        output = args.csv_file.rsplit('.', 1)[0] + '.png'

    generate_graph(args.csv_file, output, args.show)


if __name__ == '__main__':
    main()

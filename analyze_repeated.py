#!/usr/bin/env python3
"""
analyze_repeated.py — aggregates repeated performance test results.

For each (n_robots, hz) combination:
  - Takes 12 runs
  - Removes 2 runs with highest e2e_avg_ms (outliers)
  - Computes mean and std of remaining 10 runs

Output:
  perf_results_aggregated.csv — aggregated results
  perf_fleet_final.png        — fleet axis charts
  perf_freq_final.png         — frequency axis charts
  perf_components_final.png   — component latency charts

Usage:
  python3 analyze_repeated.py
"""

import csv
import os
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from collections import defaultdict

INPUT_CSV  = Path.home() / "magisterka" / "perf_results_repeated.csv"
OUTPUT_CSV = Path.home() / "magisterka" / "perf_results_aggregated.csv"
OUT_DIR    = Path.home() / "magisterka"

REPETITIONS   = 12
OUTLIERS_DROP = 2
KEEP          = REPETITIONS - OUTLIERS_DROP  # 10


# ── Load data ─────────────────────────────────────────────────────────────────
def load_csv(path):
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            d = {}
            for k, v in row.items():
                if k == 'timestamp':
                    d[k] = v
                else:
                    try:
                        d[k] = float(v) if v not in ('', 'None') else None
                    except ValueError:
                        d[k] = v
            rows.append(d)
    return rows


# ── Aggregate ─────────────────────────────────────────────────────────────────
def aggregate(rows):
    # Group by (n_robots, hz)
    groups = defaultdict(list)
    for r in rows:
        key = (r['n_robots'], r['hz'])
        groups[key].append(r)

    aggregated = []
    for (n_robots, hz), runs in sorted(groups.items()):
        print(f"\n  {int(n_robots)} robots x {int(hz)} Hz — {len(runs)} runs")

        # Sort by e2e_avg_ms, remove 2 highest (outliers)
        valid = [r for r in runs if r.get('e2e_avg_ms') is not None]
        valid.sort(key=lambda r: r['e2e_avg_ms'])

        if len(valid) > OUTLIERS_DROP:
            kept   = valid[1:-1]
            dropped = [valid[0], valid[-1]]
            print(f"    Dropped outliers (highest e2e): "
                  f"{[round(r['e2e_avg_ms'], 1) for r in dropped]} ms")
        else:
            kept = valid
            print(f"    Warning: fewer than {OUTLIERS_DROP+1} valid runs")

        print(f"    Kept {len(kept)} runs: "
              f"e2e = {[round(r['e2e_avg_ms'], 1) for r in kept]} ms")

        def mean(key):
            vals = [r[key] for r in kept if r.get(key) is not None]
            return round(np.mean(vals), 3) if vals else None

        def std(key):
            vals = [r[key] for r in kept if r.get(key) is not None]
            return round(np.std(vals), 3) if vals else None

        agg = {
            'n_robots':              n_robots,
            'hz':                    hz,
            'n_runs_total':          len(runs),
            'n_runs_kept':           len(kept),
            'throughput_pub_mean':   mean('throughput_pub'),
            'throughput_pub_std':    std('throughput_pub'),
            'throughput_alert_mean': mean('throughput_alert'),
            'throughput_alert_std':  std('throughput_alert'),
            'broker_avg_ms_mean':    mean('broker_avg_ms'),
            'broker_avg_ms_std':     std('broker_avg_ms'),
            'nebula_avg_ms_mean':    mean('nebula_avg_ms'),
            'nebula_avg_ms_std':     std('nebula_avg_ms'),
            'e2e_avg_ms_mean':       mean('e2e_avg_ms'),
            'e2e_avg_ms_std':        std('e2e_avg_ms'),
            'e2e_p95_ms_mean':       mean('e2e_p95_ms'),
            'e2e_p95_ms_std':        std('e2e_p95_ms'),
        }
        aggregated.append(agg)
        print(f"    e2e mean={agg['e2e_avg_ms_mean']}ms "
              f"std={agg['e2e_avg_ms_std']}ms "
              f"broker={agg['broker_avg_ms_mean']}ms "
              f"nebula={agg['nebula_avg_ms_mean']}ms")

    return aggregated


# ── Save aggregated CSV ───────────────────────────────────────────────────────
def save_csv(aggregated, path):
    if not aggregated:
        return
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=aggregated[0].keys())
        writer.writeheader()
        writer.writerows(aggregated)
    print(f"\nAggregated results saved to: {path}")


# ── Charts ────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    'font.family':    'DejaVu Sans',
    'font.size':      11,
    'axes.titlesize': 13,
    'axes.labelsize': 11,
    'axes.grid':      True,
    'grid.alpha':     0.3,
    'lines.linewidth': 2,
    'lines.markersize': 7,
})

C_PUB    = '#2196F3'
C_ALERT  = '#F44336'
C_BROKER = '#FF9800'
C_NEBULA = '#9C27B0'
C_E2E    = '#4CAF50'
C_P95    = '#795548'


def vals(serie, key):
    return [r.get(key) for r in serie]


def errorbars(serie, mean_key, std_key):
    means = [r.get(mean_key) for r in serie]
    stds  = [r.get(std_key) or 0 for r in serie]
    return means, stds


def make_fleet_chart(fleet, out_path):
    xv = [int(r['n_robots']) for r in fleet]
    xl = [str(v) for v in xv]
    idx = list(range(len(xv)))
    w = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar([i - w/2 for i in idx], vals(fleet, 'throughput_pub_mean'),
           width=w, color=C_PUB, alpha=0.85, label='Input: GPS messages')
    ax.bar([i + w/2 for i in idx], vals(fleet, 'throughput_alert_mean'),
           width=w, color=C_ALERT, alpha=0.85, label='Output: alerts')
    ax.set_xlabel('Number of robots')
    ax.set_ylabel('Messages / second')
    ax.set_title('Fleet axis - Throughput (10 Hz)')
    ax.legend(fontsize=9)
    ax.set_xticks(idx)
    ax.set_xticklabels(xl)
    plt.tight_layout()
    p = str(out_path).replace('perf_fleet_final', 'perf_fleet_throughput_final')
    plt.savefig(p, dpi=150, bbox_inches='tight')
    print(f"Saved: {p}")
    plt.close()

    fig, ax = plt.subplots(figsize=(8, 5))
    means, stds = errorbars(fleet, 'e2e_avg_ms_mean', 'e2e_avg_ms_std')
    ax.errorbar(xv, means, yerr=stds, fmt='o-', color=C_E2E,
                capsize=4, label='avg +/- std (ms)')
    p95_means, p95_stds = errorbars(fleet, 'e2e_p95_ms_mean', 'e2e_p95_ms_std')
    ax.errorbar(xv, p95_means, yerr=p95_stds, fmt='s--', color=C_P95,
                capsize=4, label='p95 +/- std (ms)')
    ax.set_xlabel('Number of robots')
    ax.set_ylabel('Latency (ms)')
    ax.set_title('Fleet axis - End-to-end latency (10 Hz)')
    ax.legend(fontsize=9)
    ax.set_xticks(xv)
    plt.tight_layout()
    p = str(out_path).replace('perf_fleet_final', 'perf_fleet_latency_final')
    plt.savefig(p, dpi=150, bbox_inches='tight')
    print(f"Saved: {p}")
    plt.close()

    fig, ax = plt.subplots(figsize=(8, 5))
    broker_means, broker_stds = errorbars(fleet, 'broker_avg_ms_mean', 'broker_avg_ms_std')
    nebula_means, nebula_stds = errorbars(fleet, 'nebula_avg_ms_mean', 'nebula_avg_ms_std')
    ax.bar(xl, broker_means, yerr=broker_stds, label='Broker MQTT',
           color=C_BROKER, alpha=0.85, capsize=3)
    ax.bar(xl, nebula_means, yerr=nebula_stds, bottom=broker_means,
           label='NebulaStream', color=C_NEBULA, alpha=0.85, capsize=3)
    ax.set_xlabel('Number of robots')
    ax.set_ylabel('Latency avg (ms)')
    ax.set_title('Fleet axis - Latency breakdown per component (10 Hz)')
    ax.legend(fontsize=9)
    plt.tight_layout()
    p = str(out_path).replace('perf_fleet_final', 'perf_fleet_components_final')
    plt.savefig(p, dpi=150, bbox_inches='tight')
    print(f"Saved: {p}")
    plt.close()

def make_freq_chart(freq, out_path):
    xv = [int(r['hz']) for r in freq]
    xl = [str(v) for v in xv]
    idx = list(range(len(xv)))
    w = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar([i - w/2 for i in idx], vals(freq, 'throughput_pub_mean'),
           width=w, color=C_PUB, alpha=0.85, label='Input: GPS messages')
    ax.bar([i + w/2 for i in idx], vals(freq, 'throughput_alert_mean'),
           width=w, color=C_ALERT, alpha=0.85, label='Output: alerts')
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Messages / second')
    ax.set_title('Frequency axis - Throughput (3 robots)')
    ax.legend(fontsize=9)
    ax.set_xticks(idx)
    ax.set_xticklabels(xl)
    plt.tight_layout()
    p = str(out_path).replace('perf_freq_final', 'perf_freq_throughput_final')
    plt.savefig(p, dpi=150, bbox_inches='tight')
    print(f"Saved: {p}")
    plt.close()

    fig, ax = plt.subplots(figsize=(8, 5))
    means, stds = errorbars(freq, 'e2e_avg_ms_mean', 'e2e_avg_ms_std')
    ax.errorbar(xv, means, yerr=stds, fmt='o-', color=C_E2E,
                capsize=4, label='avg +/- std (ms)')
    p95_means, p95_stds = errorbars(freq, 'e2e_p95_ms_mean', 'e2e_p95_ms_std')
    ax.errorbar(xv, p95_means, yerr=p95_stds, fmt='s--', color=C_P95,
                capsize=4, label='p95 +/- std (ms)')
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Latency (ms)')
    ax.set_title('Frequency axis - End-to-end latency (3 robots)')
    ax.legend(fontsize=9)
    ax.set_xticks(xv)
    ax.set_xticklabels(xl)
    plt.tight_layout()
    p = str(out_path).replace('perf_freq_final', 'perf_freq_latency_final')
    plt.savefig(p, dpi=150, bbox_inches='tight')
    print(f"Saved: {p}")
    plt.close()

    fig, ax = plt.subplots(figsize=(8, 5))
    broker_means, broker_stds = errorbars(freq, 'broker_avg_ms_mean', 'broker_avg_ms_std')
    nebula_means, nebula_stds = errorbars(freq, 'nebula_avg_ms_mean', 'nebula_avg_ms_std')
    ax.bar(xl, broker_means, yerr=broker_stds, label='Broker MQTT',
           color=C_BROKER, alpha=0.85, capsize=3)
    ax.bar(xl, nebula_means, yerr=nebula_stds, bottom=broker_means,
           label='NebulaStream', color=C_NEBULA, alpha=0.85, capsize=3)
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Latency avg (ms)')
    ax.set_title('Frequency axis - Latency breakdown per component (3 robots)')
    ax.legend(fontsize=9)
    plt.tight_layout()
    p = str(out_path).replace('perf_freq_final', 'perf_freq_components_final')
    plt.savefig(p, dpi=150, bbox_inches='tight')
    print(f"Saved: {p}")
    plt.close()

def make_components_chart(fleet, freq, out_path):
    fig, ax = plt.subplots(figsize=(8, 5))
    xv = [int(r['n_robots']) for r in fleet]
    broker_m, broker_s = errorbars(fleet, 'broker_avg_ms_mean', 'broker_avg_ms_std')
    nebula_m, nebula_s = errorbars(fleet, 'nebula_avg_ms_mean', 'nebula_avg_ms_std')
    e2e_m,    e2e_s    = errorbars(fleet, 'e2e_avg_ms_mean',    'e2e_avg_ms_std')
    ax.errorbar(xv, broker_m, yerr=broker_s, fmt='o-',  color=C_BROKER,
                capsize=3, label='Broker MQTT')
    ax.errorbar(xv, nebula_m, yerr=nebula_s, fmt='s-',  color=C_NEBULA,
                capsize=3, label='NebulaStream')
    ax.errorbar(xv, e2e_m,    yerr=e2e_s,    fmt='^--', color=C_E2E,
                capsize=3, label='End-to-end')
    ax.set_xlabel('Number of robots')
    ax.set_ylabel('Latency avg (ms)')
    ax.set_title('Component contribution - Fleet axis (10 Hz)')
    ax.legend()
    ax.set_xticks(xv)
    plt.tight_layout()
    p = str(out_path).replace('perf_components_final', 'perf_components_fleet_final')
    plt.savefig(p, dpi=150, bbox_inches='tight')
    print(f"Saved: {p}")
    plt.close()

    fig, ax = plt.subplots(figsize=(8, 5))
    xv = [int(r['hz']) for r in freq]
    broker_m, broker_s = errorbars(freq, 'broker_avg_ms_mean', 'broker_avg_ms_std')
    nebula_m, nebula_s = errorbars(freq, 'nebula_avg_ms_mean', 'nebula_avg_ms_std')
    e2e_m,    e2e_s    = errorbars(freq, 'e2e_avg_ms_mean',    'e2e_avg_ms_std')
    ax.errorbar(xv, broker_m, yerr=broker_s, fmt='o-',  color=C_BROKER,
                capsize=3, label='Broker MQTT')
    ax.errorbar(xv, nebula_m, yerr=nebula_s, fmt='s-',  color=C_NEBULA,
                capsize=3, label='NebulaStream')
    ax.errorbar(xv, e2e_m,    yerr=e2e_s,    fmt='^--', color=C_E2E,
                capsize=3, label='End-to-end')
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Latency avg (ms)')
    ax.set_title('Component contribution - Frequency axis (3 robots)')
    ax.legend()
    ax.set_xticks(xv)
    ax.set_xticklabels([str(v) for v in xv])
    plt.tight_layout()
    p = str(out_path).replace('perf_components_final', 'perf_components_freq_final')
    plt.savefig(p, dpi=150, bbox_inches='tight')
    print(f"Saved: {p}")
    plt.close()

    plt.close()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"Loading: {INPUT_CSV}")
    rows = load_csv(INPUT_CSV)
    print(f"Total rows: {len(rows)}")

    print("\nAggregating results (removing 2 highest e2e outliers per combination)...")
    aggregated = aggregate(rows)

    save_csv(aggregated, OUTPUT_CSV)

    # Split into fleet and frequency series
    fleet = sorted([r for r in aggregated if r['hz'] == 10.0],
                   key=lambda r: r['n_robots'])
    freq  = sorted([r for r in aggregated if r['n_robots'] == 3.0],
                   key=lambda r: r['hz'])

    print(f"\nGenerating charts...")
    make_fleet_chart(fleet, OUT_DIR / "perf_fleet_final.png")
    make_freq_chart(freq,   OUT_DIR / "perf_freq_final.png")
    make_components_chart(fleet, freq, OUT_DIR / "perf_components_final.png")

    print("\nDone.")
    print(f"  {OUTPUT_CSV}")
    print(f"  {OUT_DIR}/perf_fleet_final.png")
    print(f"  {OUT_DIR}/perf_freq_final.png")
    print(f"  {OUT_DIR}/perf_components_final.png")


if __name__ == "__main__":
    main()

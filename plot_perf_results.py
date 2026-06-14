#!/usr/bin/env python3
"""
plot_perf_results.py — performance test charts.
Fleet axis: 1,3,10,20,30,40,50 robots @ 10 Hz
Frequency axis: 3 robots @ 1,10,20,40,60,80,100 Hz
  (10 Hz point comes from fleet axis)

Usage: python3 plot_perf_results.py
"""

import csv
import matplotlib.pyplot as plt
from pathlib import Path

CSV_PATH = Path.home() / "magisterka" / "perf_results.csv"
OUT_DIR  = Path.home() / "magisterka"

# ── Load data ───────────────────────────────────────────────────────────────────
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

all_rows = load_csv(CSV_PATH)

# Fleet axis: all points at 10 Hz
fleet = sorted([r for r in all_rows if r['hz'] == 10.0],
               key=lambda r: r['n_robots'])

# Frequency axis: all points at 3 robots
# (includes 10 Hz from fleet axis + remaining)
freq = sorted([r for r in all_rows if r['n_robots'] == 3.0],
              key=lambda r: r['hz'])

def vals(serie, key):
    return [r.get(key) for r in serie]

# ── Style ───────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    'font.family':   'DejaVu Sans',
    'font.size':     11,
    'axes.titlesize': 13,
    'axes.labelsize': 11,
    'axes.grid':     True,
    'grid.alpha':    0.3,
    'lines.linewidth': 2,
    'lines.markersize': 7,
})

C_PUB    = '#2196F3'
C_ALERT  = '#F44336'
C_BROKER = '#FF9800'
C_NEBULA = '#9C27B0'
C_E2E    = '#4CAF50'
C_P95    = '#795548'

# ══════════════════════════════════════════════════════════════════════════════
# Chart 1 — Fleet axis
# ══════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 3, figsize=(17, 5))
fig.suptitle('Fleet axis — impact of number of robots (fixed frequency: 10 Hz)',
             fontsize=14, fontweight='bold', y=1.02)

xv = [int(r['n_robots']) for r in fleet]
xl = [str(v) for v in xv]

# Panel 1: Throughput
ax = axes[0]
xl_idx = list(range(len(xv)))
w = 0.35
ax.bar([x - w/2 for x in xl_idx], vals(fleet, 'throughput_pub'),
       width=w, color=C_PUB, alpha=0.85, label='Published (msg/s)')
ax.bar([x + w/2 for x in xl_idx], vals(fleet, 'throughput_alert'),
       width=w, color=C_ALERT, alpha=0.85, label='NebulaStream alerts (alert/s)')
ax.set_xlabel('Number of robots')
ax.set_ylabel('Messages / second')
ax.set_title('Throughput')
ax.legend(fontsize=9)
ax.set_xticks(xl_idx)
ax.set_xticklabels(xl)

# Panel 2: End-to-end latency
ax = axes[1]
ax.plot(xv, vals(fleet, 'e2e_avg_ms'), 'o-',  color=C_E2E, label='avg (ms)')
ax.plot(xv, vals(fleet, 'e2e_p95_ms'), 's--', color=C_P95, label='p95 (ms)')
ax.set_xlabel('Number of robots')
ax.set_ylabel('Latency (ms)')
ax.set_title('End-to-end latency (pub→alert)')
ax.legend(fontsize=9)
ax.set_xticks(xv)

# Panel 3: Latency breakdown per component
ax = axes[2]
broker_ms = vals(fleet, 'broker_avg_ms')
nebula_ms = vals(fleet, 'nebula_avg_ms')
ax.bar(xl, broker_ms, label='Broker MQTT',  color=C_BROKER, alpha=0.85)
ax.bar(xl, nebula_ms, bottom=broker_ms,     label='NebulaStream', color=C_NEBULA, alpha=0.85)
ax.set_xlabel('Number of robots')
ax.set_ylabel('Latency avg (ms)')
ax.set_title('Latency breakdown per component')
ax.legend(fontsize=9)

plt.tight_layout()
out1 = OUT_DIR / "perf_fleet.png"
plt.savefig(out1, dpi=150, bbox_inches='tight')
print(f"Saved: {out1}")
plt.close()

# ══════════════════════════════════════════════════════════════════════════════
# Chart 2 — Frequency axis
# ══════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 3, figsize=(17, 5))
fig.suptitle('Frequency axis — impact of Hz per robot (fixed fleet: 3 robots)',
             fontsize=14, fontweight='bold', y=1.02)

xv = [int(r['hz']) for r in freq]
xl = [str(v) for v in xv]

# Panel 1: Throughput
ax = axes[0]
idx = list(range(len(xv)))
w = 0.35
ax.bar([i - w/2 for i in idx], vals(freq, 'throughput_pub'),
       width=w, color=C_PUB, alpha=0.85, label='Published (msg/s)')
ax.bar([i + w/2 for i in idx], vals(freq, 'throughput_alert'),
       width=w, color=C_ALERT, alpha=0.85, label='NebulaStream alerts (alert/s)')
ax.set_xticks(idx)
ax.set_xticklabels([str(v) for v in xv])
ax.set_xlabel('Frequency (Hz)')
ax.set_ylabel('Messages / second')
ax.set_title('Throughput')
ax.legend(fontsize=9)

# Panel 2: End-to-end latency
ax = axes[1]
ax.plot(xv, vals(freq, 'e2e_avg_ms'), 'o-',  color=C_E2E, label='avg (ms)')
ax.plot(xv, vals(freq, 'e2e_p95_ms'), 's--', color=C_P95, label='p95 (ms)')
ax.set_xlabel('Frequency (Hz)')
ax.set_ylabel('Latency (ms)')
ax.set_title('End-to-end latency (pub→alert)')
ax.legend(fontsize=9)
ax.set_xticks(xv)
ax.set_xticklabels(xl)

# Panel 3: Latency breakdown per component
ax = axes[2]
broker_ms = vals(freq, 'broker_avg_ms')
nebula_ms = vals(freq, 'nebula_avg_ms')
ax.bar(xl, broker_ms, label='Broker MQTT',  color=C_BROKER, alpha=0.85)
ax.bar(xl, nebula_ms, bottom=broker_ms,     label='NebulaStream', color=C_NEBULA, alpha=0.85)
ax.set_xlabel('Frequency (Hz)')
ax.set_ylabel('Latency avg (ms)')
ax.set_title('Latency breakdown per component')
ax.legend(fontsize=9)

plt.tight_layout()
out2 = OUT_DIR / "perf_freq.png"
plt.savefig(out2, dpi=150, bbox_inches='tight')
print(f"Saved: {out2}")
plt.close()

# ══════════════════════════════════════════════════════════════════════════════
# Chart 3 — Component latency contribution (line)
# ══════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle('Component contribution to end-to-end latency',
             fontsize=14, fontweight='bold', y=1.02)

# Left: fleet axis
ax = axes[0]
xv = [int(r['n_robots']) for r in fleet]
ax.plot(xv, vals(fleet, 'broker_avg_ms'), 'o-',  color=C_BROKER, label='Broker MQTT')
ax.plot(xv, vals(fleet, 'nebula_avg_ms'), 's-',  color=C_NEBULA, label='NebulaStream')
ax.plot(xv, vals(fleet, 'e2e_avg_ms'),    '^--', color=C_E2E,    label='End-to-end')
ax.set_xlabel('Number of robots')
ax.set_ylabel('Latency avg (ms)')
ax.set_title('Fleet axis (10 Hz)')
ax.legend()
ax.set_xticks(xv)

# Right: frequency axis
ax = axes[1]
xv = [int(r['hz']) for r in freq]
ax.plot(xv, vals(freq, 'broker_avg_ms'), 'o-',  color=C_BROKER, label='Broker MQTT')
ax.plot(xv, vals(freq, 'nebula_avg_ms'), 's-',  color=C_NEBULA, label='NebulaStream')
ax.plot(xv, vals(freq, 'e2e_avg_ms'),    '^--', color=C_E2E,    label='End-to-end')
ax.set_xlabel('Frequency (Hz)')
ax.set_ylabel('Latency avg (ms)')
ax.set_title('Frequency axis (3 robots)')
ax.legend()
ax.set_xticks(xv)
ax.set_xticklabels([str(v) for v in xv])

plt.tight_layout()
out3 = OUT_DIR / "perf_components.png"
plt.savefig(out3, dpi=150, bbox_inches='tight')
print(f"Saved: {out3}")
plt.close()

print("\nAll charts generated:")
print(f"  {out1}  — fleet axis")
print(f"  {out2}  — frequency axis")
print(f"  {out3}  — component contribution")

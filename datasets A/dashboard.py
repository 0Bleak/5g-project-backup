#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

files = {
    'Scenario A  10 MHz  3 Physical UEs': 'scen_A_20260526_1646.csv',
    'Scenario A  5 MHz  3 Physical UEs': 'scenario_A_3physical_UEs_low_density_5MHz.csv',
}

COLORS = {
    'CRITICAL':    '#c0392b',
    'PERFORMANCE': '#2980b9',
    'BUSINESS':    '#27ae60'
}

for title, fname in files.items():
    df = pd.read_csv(fname)
    df = df[df['slice_name'].isin(['CRITICAL', 'PERFORMANCE', 'BUSINESS'])]
    df['t'] = pd.to_numeric(df['timestamp'])
    df['t'] = df['t'] - df['t'].min()
    df['dl_mbps'] = df['dl_brate_bps'] / 1e6

    fig = plt.figure(figsize=(18, 10))
    fig.suptitle(title, fontsize=15, fontweight='bold', y=0.99)
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.42, wspace=0.32)

    ax1 = fig.add_subplot(gs[0, :2])
    for sl, grp in df.groupby('slice_name'):
        ax1.plot(grp['t'], grp['cqi'],
                 label=sl, color=COLORS[sl], alpha=0.75, linewidth=0.9)
    ax1.set_title('CQI per slice over time')
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('CQI')
    ax1.set_ylim(0, 16)
    ax1.legend()
    ax1.grid(True, alpha=0.25)

    ax2 = fig.add_subplot(gs[1, :2])
    for sl, grp in df.groupby('slice_name'):
        ax2.plot(grp['t'], grp['prb_max'],
                 label=sl, color=COLORS[sl], alpha=0.75, linewidth=0.9)
    ax2.set_title('Allocated PRB max per slice over time')
    ax2.set_xlabel('Time (s)')
    ax2.set_ylabel('PRB max (%)')
    ax2.set_ylim(0, 105)
    ax2.legend()
    ax2.grid(True, alpha=0.25)

    ax3 = fig.add_subplot(gs[0, 2])
    for sl in ['CRITICAL', 'PERFORMANCE', 'BUSINESS']:
        d = df[df['slice_name'] == sl]['cqi']
        ax3.hist(d, bins=15, alpha=0.6, label=sl,
                 color=COLORS[sl], density=True)
    ax3.set_title('CQI distribution')
    ax3.set_xlabel('CQI')
    ax3.set_ylabel('Density')
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.25)

    ax4 = fig.add_subplot(gs[1, 2])
    ax4.axis('off')
    stats = []
    for sl in ['CRITICAL', 'PERFORMANCE', 'BUSINESS']:
        d = df[df['slice_name'] == sl]
        stats.append([
            sl,
            str(len(d)),
            f"{d['cqi'].mean():.1f}",
            f"{d['dl_mbps'].mean():.2f}",
            f"{d['prb_max'].mean():.1f}"
        ])
    table = ax4.table(
        cellText=stats,
        colLabels=['Slice', 'Samples', 'Avg CQI', 'Avg DL (Mbps)', 'Avg PRB max'],
        cellLoc='center',
        loc='center',
        bbox=[0, 0.05, 1, 0.88]
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    for (r, c), cell in table.get_celld().items():
        if r == 0:
            cell.set_facecolor('#2c3e50')
            cell.set_text_props(color='white', fontweight='bold')
        elif r > 0:
            sl = stats[r - 1][0]
            cell.set_facecolor(COLORS[sl] + '30')
    ax4.set_title('Summary statistics', pad=8)

    out = fname.replace('.csv', '_dashboard.png')
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f'Saved: {out}')
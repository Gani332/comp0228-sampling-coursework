"""Render the report's worked Hamming example, checked against the implementation."""
import os
os.environ.setdefault('MPLCONFIGDIR', '/private/tmp/comp0228-mpl')
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import numpy as np
from optical_link.protocol import encode_body, decode_body

ROOT = Path(__file__).resolve().parents[1]
data = np.array([1, 0, 1, 1], dtype=np.uint8)
sent = encode_body(data, 'hamming74')
assert sent.tolist() == [0, 1, 1, 0, 0, 1, 1]
received = sent.copy()
received[4] ^= 1
checks = [[0, 2, 4, 6], [1, 2, 5, 6], [3, 4, 5, 6]]
failures = [int(received[idx].sum() % 2) for idx in checks]
assert failures == [1, 0, 1]
assert decode_body(received, 'hamming74').tolist() == data.tolist()

plt.rcParams.update({'pdf.fonttype': 42, 'ps.fonttype': 42, 'font.size': 8})
fig, ax = plt.subplots(figsize=(3.45, 1.12))
fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
colours = ['#0072b2', '#d55e00', '#008768']
for xy, colour in zip([(-.55, .35), (.55, .35), (0, -.60)], colours):
    ax.add_patch(Circle(xy, .95, facecolor=colour, edgecolor=colour, alpha=.16, lw=1))
    ax.add_patch(Circle(xy, .95, fill=False, edgecolor=colour, lw=.8))
for x, y, label, colour in [(-1.03, 1.45, '$P_1$', colours[0]),
                           (1.03, 1.45, '$P_2$', colours[1]),
                           (0, -1.77, '$P_4$', colours[2])]:
    ax.text(x, y, label, color=colour, ha='center', va='center')
for x, y, label in [(-1.02, .48, '1'), (1.02, .48, '2'), (0, -1.16, '4'),
                     (0, .79, '3'), (-.58, -.43, '5'), (.58, -.43, '6'), (0, -.02, '7')]:
    ax.text(x, y, label, ha='center', va='center',
            bbox=dict(boxstyle='round,pad=.13', facecolor='white', edgecolor=colours[1]) if label == '5' else None)
ax.text(1.98, 1.23, 'Data: 1011\nSent: 0110011\nBit 5 flips: 0110111\nChecks 1 and 4 fail.\n1 + 4 = 5: flip bit 5 back.\nRead 3, 5, 6, 7: 1011.',
        va='top', ha='left', linespacing=1.15)
ax.set(xlim=(-1.65, 8.95), ylim=(-1.98, 1.62), aspect='equal')
ax.axis('off')
fig.savefig(ROOT / 'report_figures/campaign_hamming.pdf')
fig.savefig('/private/tmp/comp0228-hamming-example.png', dpi=260)
print('Verified 1011 -> 0110011 -> bit-5 error -> 1011; parity failures [1, 0, 1].')

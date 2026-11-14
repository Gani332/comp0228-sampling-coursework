"""Explain spatial averaging beside the recorded, fixed receiver geometry.

The numerical example is schematic; the photograph and its region coordinates
come from the existing analysis. No measurements or decoding are changed.
"""
import os
os.environ.setdefault('MPLCONFIGDIR', '/private/tmp/comp0228-mpl')
from pathlib import Path
import json
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / 'data/analysis/physical_campaign_2026-11-08'
FIG = PROJECT / 'report_figures'
raw = Image.open(OUT / 'diagnostics/setup_frame_native.png')
assert raw.size == (1920, 1080)
picture = np.rot90(np.asarray(raw), -1)
geometry = json.loads((OUT / 'features/Video19.json').read_text())
primary = json.loads((OUT / 'evidence/Video19_trace.json').read_text())['rois_stored_xywh']['patch']

def upright(box):
    x, y, w, h = box
    return 1080-y-h, x, h, w

plt.rcParams.update({'font.size': 8, 'pdf.fonttype': 42, 'ps.fonttype': 42})
fig = plt.figure(figsize=(3.45, 2.30))
ax = fig.add_axes([0, .28, 1, .72])
ax.imshow(picture)
ax.set(xlim=(0, 1080), ylim=(1050, 365))
ax.axis('off')
regions = [geometry['regions_xywh'][0], primary, *geometry['regions_xywh'][1:]]
colours = ['#e69f00', '#21c8ff', '#fb6280', '#fb6280']
for box, colour in zip(regions, colours):
    x, y, w, h = upright(box)
    ax.add_patch(Rectangle((x, y), w, h, fill=False, edgecolor=colour, lw=1.2))
x, y, w, h = upright(regions[0])
for j in range(1, 4):
    ax.plot([x+j*w/4]*2, [y, y+h], color=colours[0], lw=.45, alpha=.7)
    ax.plot([x, x+w], [y+j*h/4]*2, color=colours[0], lw=.45, alpha=.7)
for label, xy, where, colour in [
    ('Black reference', (104, 700), (120, 420), colours[2]),
    ('Central ROI', (537, 705), (540, 450), colours[1]),
    ('White reference', (968, 700), (925, 420), colours[3]),
    ('Larger patch / 4 × 4 tiles', (765, 855), (570, 990), colours[0]),
]:
    ax.annotate(label, xy=xy, xytext=where, ha='center', va='center', fontsize=7.3,
                bbox=dict(boxstyle='round,pad=.15', fc='white', ec='none', alpha=.96),
                arrowprops=dict(arrowstyle='->', color=colour, lw=.9))

example = fig.add_axes([.02, .005, .96, .25])
example.set(xlim=(0, 10), ylim=(0, 1.7))
example.axis('off')
values = [20, 20, 20, 100]
assert sum(values)/len(values) == 40
for i, value in enumerate(values):
    x, y = (i % 2)*.55+.05, .62-(i//2)*.55
    example.add_patch(Rectangle((x, y), .55, .55, facecolor=str(value/255), edgecolor='white', lw=.7))
    example.text(x+.275, y+.275, str(value), ha='center', va='center', color='white', fontsize=7)
example.text(.6, 1.43, '4 pixels', ha='center', va='center', fontsize=7.5)
example.annotate('', xy=(2.0, .61), xytext=(1.3, .61), arrowprops=dict(arrowstyle='->', lw=.9))
example.text(2.15, 1.28, 'Patch mean = average pixel brightness', va='center', fontsize=7.5)
example.text(2.15, .67, '(20 + 20 + 20 + 100) / 4 = 40', va='center', fontsize=8)
example.text(2.15, .08, 'One brightness value per video frame', va='center', fontsize=7.5)
fig.savefig(FIG / 'campaign_setup.pdf')
fig.savefig(OUT / 'diagnostics/campaign_setup.png', dpi=240)
plt.close(fig)
print('Rendered recorded geometry and illustrative four-pixel mean (40).')

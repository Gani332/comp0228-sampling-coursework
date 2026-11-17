// Numbers transcribed from the group report: ../report.tex and ../report_figures/*.tex.

export const headline = [
  { value: '82', label: 'transmissions recorded', sub: 'in 21 phone videos' },
  { value: '16/16', label: 'clean pilot recovered', sub: '0 errors in 3,840 bits' },
  { value: '35/54', label: 'main trials recovered', sub: 'all 54 were detected' },
  { value: '0/6', label: 'with glare on the start', sub: 'never detected' },
];

// Blockage, six packets per configuration (campaign_coding_table.tex)
export const codes = [
  { code: 'Uncoded', il: false, ok: 1, errors: 6, bits: 480, ber: 1.25, goodput: 0.152 },
  { code: 'Repetition ×3', il: false, ok: 3, errors: 9, bits: 1440, ber: 0.62, goodput: 0.476 },
  { code: 'Repetition ×5', il: false, ok: 5, errors: 10, bits: 2400, ber: 0.42, goodput: 0.538 },
  { code: 'Hamming (7,4)', il: false, ok: 4, errors: 9, bits: 840, ber: 1.07, goodput: 1.13 },
  { code: 'Hamming (7,4)', il: true, ok: 6, errors: 11, bits: 840, ber: 1.31, goodput: 1.356 },
  { code: 'Reed–Solomon', il: false, ok: 6, errors: 12, bits: 672, ber: 1.79, goodput: 1.538 },
  { code: 'Reed–Solomon', il: true, ok: 2, errors: 21, bits: 672, ber: 3.12, goodput: 0.513 },
];

// Receiver front-ends on identical frames (campaign_frontends_table.tex)
export const receivers = [
  { method: 'Central patch', note: 'baseline', glare: 8, glareErr: 18, block: 27, blockErr: 78 },
  { method: 'Larger-patch mean', glare: 12, glareErr: 0, block: 29, blockErr: 75 },
  { method: 'Reference compensation', glare: 12, glareErr: 0, block: 33, blockErr: 72 },
  { method: 'Spatial quartile', glare: 12, glareErr: 0, block: 29, blockErr: 78 },
  { method: 'Combined', glare: 12, glareErr: 0, block: 33, blockErr: 73 },
  { method: 'EWMA filter', glare: 12, glareErr: 0, block: 30, blockErr: 71 },
  { method: 'Kalman filter', glare: 12, glareErr: 0, block: 29, blockErr: 75 },
];

// Simulated change in recovery from interleaving, correlated flips, rho = 0.05
export const interleaveSim = [
  { label: 'Hamming · L=4', pp: 39.0, lo: 36.9, hi: 41.2 },
  { label: 'Hamming · L=16', pp: 11.7, lo: 10.4, hi: 13.2 },
  { label: 'RS · L=4', pp: -30.75 },
  { label: 'RS · L=16', pp: -13.85 },
];

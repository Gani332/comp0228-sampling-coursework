import { codes, headline, interleaveSim, receivers } from '../data/results';

const Dots = ({ n, of }: { n: number; of: number }) => (
  <span className={`dots${n <= of / 3 ? ' low' : ''}`} aria-label={`${n} of ${of}`}>
    {Array.from({ length: of }, (_, i) => <i key={i} className={i < n ? 'on' : ''} />)}
  </span>
);
const Meter = ({ v, max, ok }: { v: number; max: number; ok?: boolean }) => (
  <div className={`meter${ok ? ' ok' : ''}`}><i style={{ width: `${(v / max) * 100}%` }} /></div>
);

function InterleaveChart() {
  const W = 460, rowH = 40, top = 8, left = 120, right = 56, H = top + rowH * interleaveSim.length + 28;
  const min = -40, max = 45, x = (v: number) => left + ((v - min) / (max - min)) * (W - left - right);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Change in simulated recovery from interleaving, in percentage points">
      {[-40, -20, 0, 20, 40].map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={top} y2={top + rowH * interleaveSim.length} stroke="var(--line)" strokeWidth={t === 0 ? 1.5 : 1} />
          <text x={x(t)} y={H - 8} textAnchor="middle">{t > 0 ? `+${t}` : t}</text>
        </g>
      ))}
      {interleaveSim.map((r, i) => {
        const y = top + i * rowH + 10, h = 20, pos = r.pp > 0, col = pos ? 'var(--ok)' : 'var(--bad)';
        const end = pos ? x(r.hi ?? r.pp) + 8 : x(0) + 8;
        return (
          <g key={r.label}>
            <text x={left - 10} y={y + 14} textAnchor="end">{r.label}</text>
            <rect x={Math.min(x(0), x(r.pp))} y={y} width={Math.abs(x(r.pp) - x(0))} height={h} rx={4} fill={col} opacity={0.9} />
            {r.lo !== undefined && r.hi !== undefined && (
              <g stroke="var(--text)" strokeWidth={1.5}>
                <line x1={x(r.lo)} x2={x(r.hi)} y1={y + h / 2} y2={y + h / 2} />
                <line x1={x(r.lo)} x2={x(r.lo)} y1={y + 5} y2={y + h - 5} />
                <line x1={x(r.hi)} x2={x(r.hi)} y1={y + 5} y2={y + h - 5} />
              </g>
            )}
            <text x={end} y={y + 14} textAnchor="start" style={{ fill: 'var(--text)' }}>{pos ? '+' : ''}{r.pp}</text>
          </g>
        );
      })}
    </svg>
  );
}

export default function Results() {
  const maxG = 1.6;
  return (
    <>
      <div className="stats" style={{ marginTop: 24 }}>
        {headline.map((h) => <div className="stat" key={h.label}><span>{h.label}</span><b>{h.value}</b><span>{h.sub}</span></div>)}
      </div>

      <section className="section">
        <div className="section-head">
          <div className="eyebrow">Codes under blockage · 6 packets each</div>
          <h2>Reed–Solomon delivered the most, fastest</h2>
          <p>Success means the exact message with a valid CRC. Goodput counts failures as zero.</p>
        </div>
        <div className="card scroll">
          <table className="table">
            <thead><tr><th>Code</th><th>Recovered</th><th>BER before fixing</th><th>Goodput</th><th /></tr></thead>
            <tbody>
              {codes.map((c) => (
                <tr key={c.code + c.il}>
                  <td>{c.code}{c.il && <span className="tag">interleaved</span>}</td>
                  <td><div className="row"><Dots n={c.ok} of={6} /><span className="mono" style={{ fontFamily: 'var(--mono)', fontSize: 13 }}>{c.ok}/6</span></div></td>
                  <td className="mono">{c.ber.toFixed(2)}%</td>
                  <td className="mono">{c.goodput.toFixed(3)} bit/s</td>
                  <td style={{ width: '22%' }}><Meter v={c.goodput} max={maxG} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="hint">Each configuration faced different hand-made disturbances, so this shows what happened, not a controlled ranking.</p>
      </section>

      <section className="section">
        <div className="section-head">
          <div className="eyebrow">What the noise looked like</div>
          <h2>Errors are one-directional and clustered</h2>
        </div>
        <div className="grid-2">
          <div className="card" style={{ display: 'grid', gap: 12 }}>
            <div className="big">18 <small>wrong bits under glare · 1.36%</small></div>
            <div className="split"><span style={{ flex: 1, background: 'var(--accent)' }}>all 0 → 1</span></div>
            <div className="big" style={{ marginTop: 8 }}>78 <small>wrong bits under blockage · 1.06%</small></div>
            <div className="split"><span style={{ flex: 34, background: 'var(--accent)' }}>34 × 0→1</span><span style={{ flex: 44, background: 'var(--sky)' }}>44 × 1→0</span></div>
          </div>
          <div className="card" style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
            <p style={{ color: 'var(--muted)' }}>Share of wrong bits that sit in a run of two or more</p>
            <div><div className="label" style={{ marginBottom: 6 }}>Glare <b>78%</b></div><Meter v={78} max={100} /></div>
            <div><div className="label" style={{ marginBottom: 6 }}>Blockage <b>56%</b></div><Meter v={56} max={100} /></div>
            <p className="hint">Clusters can land several errors in one codeword, beyond what Hamming or repetition can repair, even when the overall error rate is low.</p>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div className="eyebrow">Extension 1 · receiver processing · identical frames</div>
          <h2>Measure a bigger area first</h2>
          <p>Every method decodes the same recorded frames, so the differences come from the receiver alone.</p>
        </div>
        <div className="card scroll">
          <table className="table">
            <thead><tr><th>Method</th><th>Glare</th><th /><th>Blockage</th><th /></tr></thead>
            <tbody>
              {receivers.map((r) => (
                <tr key={r.method}>
                  <td>{r.method}{r.note && <span className="tag">{r.note}</span>}</td>
                  <td className="mono">{r.glare}/12</td><td style={{ width: '20%' }}><Meter v={r.glare} max={12} ok={r.glare === 12} /></td>
                  <td className="mono">{r.block}/42</td><td style={{ width: '20%' }}><Meter v={r.block} max={42} ok={r.block >= 33} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="hint">Some blockages also covered the reference strips, so the reference gains are not proof the compensation was right. All methods share packet detection, so early-glare failures remain.</p>
      </section>

      <section className="section">
        <div className="section-head">
          <div className="eyebrow">Extension 2 · interleaving at depth 8</div>
          <h2>Spreading a burst helps Hamming and hurts Reed–Solomon</h2>
          <p>Hamming repairs 1 bit per word, so spreading errors across words helps. Reed–Solomon repairs 2 whole bytes, so spreading errors across more bytes hurts.</p>
        </div>
        <div className="grid-2">
          <div className="card" style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
            <div className="eyebrow">Recorded blockage trials</div>
            <div className="row" style={{ justifyContent: 'space-between' }}><span>Hamming</span><span className="row"><Dots n={4} of={6} /> → <Dots n={6} of={6} /></span></div>
            <div className="row" style={{ justifyContent: 'space-between' }}><span>Reed–Solomon</span><span className="row"><Dots n={6} of={6} /> → <Dots n={2} of={6} /></span></div>
            <p className="hint">The four interleaved Reed–Solomon failures damaged 3, 7, 3 and 4 bytes. It can repair only 2.</p>
          </div>
          <div className="card chart" style={{ display: 'grid', gap: 10 }}>
            <div className="eyebrow">Simulated change in recovery, percentage points</div>
            <InterleaveChart />
            <p className="hint">480,000 simulated decodes, burst flips at ρ = 0.05. Bars with whiskers show 95% intervals.</p>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head"><div className="eyebrow">Takeaways</div><h2>What the evidence supports</h2></div>
        <div className="card takeaways">
          <p className="takeaway">Fewer errors don't mean more messages: repetition ×5 had the lowest BER but recovered fewer messages than Reed–Solomon, at a third of the goodput.</p>
          <p className="takeaway">Measuring a larger screen area fixed every glare packet (8/12 → 12/12) with no extra filtering.</p>
          <p className="takeaway">Choose the code and bit order together: interleaving helps codes that fix bits and harms codes that fix bytes.</p>
          <p className="takeaway">The next fix is detection: all six packets with glare on the start pattern failed before any code could help.</p>
        </div>
        <p className="hint">Limits: six packets per configuration with hand-made disturbances. Using the earliest completed takes drops recovery from 35/54 to 30/54. Simulations assume perfect detection.</p>
      </section>
    </>
  );
}

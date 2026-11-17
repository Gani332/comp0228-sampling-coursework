import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BIT_MS, CODECS, makePacket, receive, segmentOf,
  type Bits, type Codec, type Packet, type Reception, type Segment,
} from '../link/protocol';

type Noise = 'clean' | 'burst' | 'glare' | 'block' | 'random';
interface State { msg: string; codec: Codec; depth: number; noise: Noise; start: number; len: number; rate: number; seed: number }

const NOISE: { id: Noise; label: string; hint: string }[] = [
  { id: 'clean', label: 'Clean', hint: 'Nothing gets in the way.' },
  { id: 'burst', label: 'Burst', hint: 'Every bit in the window is flipped.' },
  { id: 'glare', label: 'Glare', hint: 'Dark bits read as bright (0 → 1).' },
  { id: 'block', label: 'Block', hint: 'Bright bits read as dark (1 → 0).' },
  { id: 'random', label: 'Random', hint: 'Each bit flips independently.' },
];
const SEG_COLOR: Record<Segment, string> = { guard: 'var(--faint)', preamble: 'var(--pre)', header: 'var(--head)', body: 'var(--body)' };
const SEG_LABEL: Record<Segment, string> = { guard: 'Guard', preamble: 'Start pattern', header: 'Header', body: 'Message' };

const BASE: State = { msg: 'A7k2M9q4', codec: 'hamming74', depth: 1, noise: 'burst', start: 0, len: 3, rate: 2, seed: 7 };
const build = (s: State) => makePacket(s.msg || ' ', s.codec, 3, s.depth);

interface Example { id: string; label: string; good: boolean; state: Partial<State>; at: (p: Packet) => number }
const EXAMPLES: Example[] = [
  { id: 'ham', label: 'Burst breaks Hamming', good: false, state: { codec: 'hamming74', depth: 1, noise: 'burst', len: 3 }, at: (p) => p.seg.body[0] + 8 },
  { id: 'ham8', label: 'Interleaving saves Hamming', good: true, state: { codec: 'hamming74', depth: 8, noise: 'burst', len: 3 }, at: (p) => p.seg.body[0] + 8 },
  { id: 'rs', label: 'RS absorbs a burst', good: true, state: { codec: 'rs4', depth: 1, noise: 'burst', len: 8 }, at: (p) => p.seg.body[0] + 16 },
  { id: 'rs8', label: 'Interleaving breaks RS', good: false, state: { codec: 'rs4', depth: 8, noise: 'burst', len: 8 }, at: (p) => p.seg.body[0] + 16 },
  { id: 'glare', label: 'Glare on the start', good: false, state: { codec: 'hamming74', depth: 1, noise: 'glare', len: 8 }, at: (p) => p.seg.preamble[0] },
];

function rng(seed: number) {
  return () => { seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

export default function Simulator() {
  const [s, setS] = useState<State>(() => ({ ...BASE, start: build(BASE).seg.body[0] + 8 }));
  const [manual, setManual] = useState<Set<number>>(new Set());
  const [example, setExample] = useState<string | null>('ham');
  const [tab, setTab] = useState<'wire' | 'decode'>('decode');
  const [cursor, setCursor] = useState<number | null>(null);
  const timer = useRef<number | null>(null);

  const update = (patch: Partial<State>) => { setS((o) => ({ ...o, ...patch })); setExample(null); };
  const pkt = useMemo(() => { try { return build(s); } catch { return null; } }, [s.msg, s.codec, s.depth]);
  useEffect(() => setManual(new Set()), [s.msg, s.codec, s.depth]);

  const { rx, errs, zone } = useMemo(() => {
    if (!pkt) return { rx: [] as Bits, errs: new Set<number>(), zone: new Set<number>() };
    const r = pkt.bits.slice(), z = new Set<number>();
    const start = Math.min(s.start, r.length - 1);
    if (s.noise === 'burst' || s.noise === 'glare' || s.noise === 'block') {
      for (let i = start; i < Math.min(r.length, start + s.len); i++) { z.add(i); r[i] = s.noise === 'burst' ? 1 - r[i] : s.noise === 'glare' ? 1 : 0; }
    } else if (s.noise === 'random') {
      const R = rng(s.seed); for (let i = 0; i < r.length; i++) if (R() < s.rate / 100) r[i] = 1 - r[i];
    }
    manual.forEach((i) => { if (i < r.length) r[i] = 1 - r[i]; });
    const e = new Set<number>(); r.forEach((b, i) => { if (b !== pkt.bits[i]) e.add(i); });
    return { rx: r, errs: e, zone: z };
  }, [pkt, s.noise, s.start, s.len, s.rate, s.seed, manual]);

  const res: Reception | null = pkt ? receive(pkt, rx) : null;

  const stop = () => { if (timer.current) window.clearInterval(timer.current); timer.current = null; setCursor(null); };
  useEffect(() => stop, []);
  useEffect(() => { stop(); }, [s.msg, s.codec, s.depth]);
  const play = () => {
    if (timer.current) return stop();
    let i = 0; setCursor(0); setTab('wire');
    timer.current = window.setInterval(() => { i++; if (i >= rx.length) stop(); else setCursor(i); }, BIT_MS / 4);
  };

  const loadExample = (ex: Example) => {
    stop(); setManual(new Set());
    const next = { ...BASE, ...ex.state };
    setS({ ...next, start: ex.at(build(next)) });
    setExample(ex.id);
  };
  const flip = (i: number) => setManual((m) => { const n = new Set(m); if (n.has(i)) n.delete(i); else n.add(i); return n; });

  const airtime = pkt ? (pkt.bits.length * BIT_MS) / 1000 : 0;
  const payloadBits = pkt ? pkt.payload.length * 8 : 0;
  const patchOn = cursor !== null && rx[cursor] === 1;
  const inZone = cursor !== null && zone.has(cursor);
  const windowed = s.noise === 'burst' || s.noise === 'glare' || s.noise === 'block';
  const noise = NOISE.find((n) => n.id === s.noise)!;

  return (
    <div className="sim">
      <div className="examples" role="group" aria-label="Examples">
        <span className="examples-label">Try</span>
        {EXAMPLES.map((ex) => (
          <button key={ex.id} className="example" aria-pressed={example === ex.id} onClick={() => loadExample(ex)}>
            <span className="dot" style={{ background: ex.good ? 'var(--ok)' : 'var(--bad)' }} />{ex.label}
          </button>
        ))}
      </div>

      <div className="flow">
        {/* 1 · SEND */}
        <section className="stage">
          <header className="stage-head"><span className="stage-n">1</span><h2>Send</h2></header>
          <input id="msg" aria-label="Message" className="text-input big-input" value={s.msg} maxLength={24} spellCheck={false} autoComplete="off" onChange={(e) => update({ msg: e.target.value })} />
          <div className="seg" role="group" aria-label="Error correction">
            {CODECS.map((c) => <button key={c.id} aria-pressed={s.codec === c.id} onClick={() => update({ codec: c.id })}>{c.short}</button>)}
          </div>
          <button className="switch" role="switch" aria-checked={s.depth > 1} onClick={() => update({ depth: s.depth > 1 ? 1 : 8 })}>
            <span>Interleave</span><span className="knob" />
          </button>
          <div className="stage-foot">
            <div className="mini-screen" aria-hidden="true">
              <div className={`patch${patchOn ? ' on' : ''}`} />
              {inZone && s.noise === 'glare' && <div className="glare" />}
              {inZone && s.noise === 'block' && <div className="card-block" />}
            </div>
            <div className="foot-text">
              <b>{pkt ? `${pkt.bits.length} bits` : '—'}</b>
              <span>{airtime.toFixed(1)} s on air</span>
            </div>
            <button className="btn primary" onClick={play} disabled={!pkt}>{cursor !== null ? 'Stop playback' : 'Play transmission'}</button>
          </div>
        </section>

        <div className="arrow" aria-hidden="true" />

        {/* 2 · CHANNEL */}
        <section className="stage">
          <header className="stage-head"><span className="stage-n">2</span><h2>Channel</h2></header>
          <div className="seg" role="group" aria-label="Disturbance">
            {NOISE.map((n) => <button key={n.id} aria-pressed={s.noise === n.id} onClick={() => update({ noise: n.id })}>{n.label}</button>)}
          </div>
          <p className="hint">{noise.hint}</p>
          {pkt && windowed && (
            <>
              <label className="slider" htmlFor="start"><span>Where</span><b>{SEG_LABEL[segmentOf(pkt, Math.min(s.start, pkt.bits.length - 1))]} · bit {s.start}</b></label>
              <input id="start" type="range" min={0} max={pkt.bits.length - 1} value={Math.min(s.start, pkt.bits.length - 1)} onChange={(e) => update({ start: +e.target.value })} />
              <label className="slider" htmlFor="len"><span>How long</span><b>{s.len} bits · {(s.len * 0.2).toFixed(1)} s</b></label>
              <input id="len" type="range" min={1} max={32} value={s.len} onChange={(e) => update({ len: +e.target.value })} />
            </>
          )}
          {s.noise === 'random' && (
            <>
              <label className="slider" htmlFor="rate"><span>Chance per bit</span><b>{s.rate}%</b></label>
              <input id="rate" type="range" min={0} max={10} step={0.5} value={s.rate} onChange={(e) => update({ rate: +e.target.value })} />
              <button className="btn" onClick={() => update({ seed: (s.seed * 1103515245 + 12345) >>> 0 })}>Draw new noise</button>
            </>
          )}
          <div className="stage-foot">
            <div className="foot-text">
              <b className={errs.size ? 'bad-text' : undefined}>{errs.size} wrong bit{errs.size === 1 ? '' : 's'}</b>
              <span>{manual.size ? `${manual.size} flipped by hand` : 'click bits below to flip'}</span>
            </div>
            {manual.size > 0 && <button className="btn" onClick={() => setManual(new Set())}>Clear flips</button>}
          </div>
        </section>

        <div className="arrow" aria-hidden="true" />

        {/* 3 · RECEIVE */}
        {pkt && res ? <Outcome res={res} original={s.msg} goodput={res.stage === 'ok' ? payloadBits / airtime : 0} />
          : <section className="stage"><header className="stage-head"><span className="stage-n">3</span><h2>Receive</h2></header><p className="hint">Type 1 to 24 characters.</p></section>}
      </div>

      {pkt && res && (
        <section className="detail card">
          <div className="detail-tabs" role="tablist">
            <button role="tab" aria-selected={tab === 'decode'} onClick={() => setTab('decode')}>Error correction</button>
            <button role="tab" aria-selected={tab === 'wire'} onClick={() => setTab('wire')}>Bits on the wire</button>
          </div>
          {tab === 'wire' ? <Wire pkt={pkt} rx={rx} errs={errs} zone={zone} cursor={cursor ?? -1} onFlip={flip} /> : <Decode pkt={pkt} res={res} />}
        </section>
      )}
    </div>
  );
}

function Outcome({ res, original, goodput }: { res: Reception; original: string; goodput: number }) {
  const tone = res.stage === 'ok' ? 'ok' : res.stage === 'undetected' ? 'warn' : 'bad';
  const title = { ok: 'Recovered', acquisition: 'Not detected', header: 'Header lost', decode: 'Uncorrectable', crc: 'Rejected', undetected: 'Undetected error' }[res.stage];
  const chars = res.text !== undefined ? Array.from(res.text) : null;
  const orig = Array.from(original);
  return (
    <section className={`stage outcome ${tone}`} aria-live="polite">
      <header className="stage-head"><span className="stage-n">3</span><h2>Receive</h2><span className="status"><i />{title}</span></header>
      <div className={`received${chars ? '' : ' none'}`}>
        {chars ? chars.map((c, i) => <span key={i} className={c !== orig[i] ? 'diff' : undefined}>{c}</span>) : '—'}
      </div>
      <p className="reason">{res.reason}</p>
      <div className="stage-foot">
        <div className="foot-text"><b>{goodput.toFixed(2)} bit/s</b><span>useful data rate</span></div>
      </div>
    </section>
  );
}

function Wire({ pkt, rx, errs, zone, cursor, onFlip }: { pkt: Packet; rx: Bits; errs: Set<number>; zone: Set<number>; cursor: number; onFlip: (i: number) => void }) {
  const cols = useCoarsePointer() ? 16 : 64;
  const rows: number[][] = [];
  for (let i = 0; i < rx.length; i += cols) rows.push(Array.from({ length: Math.min(cols, rx.length - i) }, (_, k) => i + k));
  return (
    <>
      <div className="legend">
        {(['preamble', 'header', 'body'] as Segment[]).map((g) => <span key={g}><i style={{ background: SEG_COLOR[g] }} />{SEG_LABEL[g]}</span>)}
        <span><i style={{ background: 'var(--bad)', borderRadius: '50%' }} />Read wrong</span>
        <span className="legend-hint">Click a bit to flip it</span>
      </div>
      <div className="dump" style={{ ['--cols' as string]: cols }}>
        {rows.map((r) => (
          <div className="dump-row" key={r[0]}>
            <span className="offset">{String(r[0]).padStart(3, '0')}</span>
            <div className="bits">
              {r.map((i) => (
                <button key={i} className={`bit${rx[i] ? ' v1' : ''}${errs.has(i) ? ' err' : ''}${zone.has(i) ? ' zone' : ''}${cursor === i ? ' now' : ''}`}
                  style={{ ['--seg' as string]: SEG_COLOR[segmentOf(pkt, i)] }}
                  aria-label={`Bit ${i}, ${SEG_LABEL[segmentOf(pkt, i)]}, read as ${rx[i]}${errs.has(i) ? ', wrong' : ''}`}
                  onClick={() => onFlip(i)} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function Decode({ pkt, res }: { pkt: Packet; res: Reception }) {
  const d = res.decode;
  if (!d || !res.bodyRx) {
    return <div className="empty">{res.stage === 'acquisition' ? 'The packet was never found, so there is nothing to correct.' : 'The header was lost, so the receiver does not know how to decode the message.'}</div>;
  }
  const damaged = d.units.filter((u) => u.errors > 0);
  const fixed = damaged.filter((u) => u.ok).length;
  const coded = pkt.codec !== 'none';
  return (
    <>
      <p className="decode-summary">
        {d.units.length} {d.unit}s · <b>{damaged.length}</b> damaged
        {coded && <> · <b className="ok-text">{fixed}</b> repaired · <b className={damaged.length - fixed ? 'bad-text' : undefined}>{damaged.length - fixed}</b> not</>}
        <span className="hint"> — {d.limit.toLowerCase()}{pkt.depth > 1 ? ', after restoring the original bit order' : ''}</span>
      </p>
      <div className="units">
        {d.units.map((u, k) => (
          <div key={k} className={`unit${u.errors > 0 ? (u.ok && coded ? ' fix' : ' fail') : ''}`}>
            {Array.from({ length: u.end - u.start }, (_, j) => {
              const i = u.start + j;
              return <i key={j} className={`${res.bodyRx![i] ? 'v1' : ''}${res.bodyRx![i] !== pkt.body[i] ? ' x' : ''}`} />;
            })}
          </div>
        ))}
      </div>
      <div className="legend" style={{ marginTop: 14, marginBottom: 0 }}>
        <span><i style={{ background: 'var(--ok)' }} />Repaired</span>
        <span><i style={{ background: 'var(--bad)' }} />Not repaired</span>
      </div>
    </>
  );
}

function useCoarsePointer() {
  const q = '(pointer: coarse)';
  const [coarse, setCoarse] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const m = window.matchMedia(q), on = () => setCoarse(m.matches);
    m.addEventListener('change', on);
    return () => m.removeEventListener('change', on);
  }, []);
  return coarse;
}

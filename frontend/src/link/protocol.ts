// TypeScript port of code/optical_link/protocol.py and the interleaver in
// code/optical_link/coding_experiments.py. Checked against Python by protocol.test.ts.

export type Codec = 'none' | 'repeat3' | 'repeat5' | 'hamming74' | 'rs4';
export type Bits = number[];

export const CODECS: { id: Codec; label: string; short: string }[] = [
  { id: 'none', label: 'Uncoded', short: 'None' },
  { id: 'repeat3', label: 'Repetition ×3', short: 'Rep ×3' },
  { id: 'repeat5', label: 'Repetition ×5', short: 'Rep ×5' },
  { id: 'hamming74', label: 'Hamming (7,4)', short: 'Hamming' },
  { id: 'rs4', label: 'Reed–Solomon', short: 'RS' },
];
const CODEC_ID: Record<Codec, number> = { none: 0, repeat3: 1, repeat5: 2, hamming74: 3, rs4: 4 };

// ---------- GF(256): primitive 0x11d, generator 2, fcr 0, four parity bytes ----------
const EXP = new Uint8Array(512);
const LOG = new Uint8Array(256);
{
  let x = 1;
  for (let i = 0; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 0x100) x ^= 0x11d; }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
}
const mul = (a: number, b: number) => (a && b ? EXP[LOG[a] + LOG[b]] : 0);
const div = (a: number, b: number) => (a ? EXP[(LOG[a] + 255 - LOG[b]) % 255] : 0);
const pow = (x: number, p: number) => EXP[((((LOG[x] * p) % 255) + 255) % 255)];
const inv = (x: number) => EXP[255 - LOG[x]];
const pScale = (p: number[], x: number) => p.map((c) => mul(c, x));
const pAdd = (p: number[], q: number[]) => {
  const n = Math.max(p.length, q.length), r = new Array<number>(n).fill(0);
  p.forEach((c, i) => (r[i + n - p.length] = c));
  q.forEach((c, i) => (r[i + n - q.length] ^= c));
  return r;
};
const pMul = (p: number[], q: number[]) => {
  const r = new Array<number>(p.length + q.length - 1).fill(0);
  for (let j = 0; j < q.length; j++) for (let i = 0; i < p.length; i++) r[i + j] ^= mul(p[i], q[j]);
  return r;
};
const pEval = (p: number[], x: number) => { let y = p[0]; for (let i = 1; i < p.length; i++) y = mul(y, x) ^ p[i]; return y; };
const pDiv = (dividend: number[], divisor: number[]): [number[], number[]] => {
  const out = dividend.slice();
  for (let i = 0; i < dividend.length - (divisor.length - 1); i++) {
    const c = out[i];
    if (c) for (let j = 1; j < divisor.length; j++) if (divisor[j]) out[i + j] ^= mul(divisor[j], c);
  }
  const s = out.length - (divisor.length - 1);
  return [out.slice(0, s), out.slice(s)];
};
const NSYM = 4;
let GEN = [1];
for (let i = 0; i < NSYM; i++) GEN = pMul(GEN, [1, pow(2, i)]);

export function rsEncode(msg: number[]): number[] {
  return msg.concat(pDiv(msg.concat(new Array(NSYM).fill(0)), GEN)[1]);
}
const syndromes = (m: number[]) => { const s = [0]; for (let i = 0; i < NSYM; i++) s.push(pEval(m, pow(2, i))); return s; };

export function rsDecode(input: number[]): { data: number[]; positions: number[] } {
  let m = input.slice();
  const synd = syndromes(m);
  if (Math.max(...synd) === 0) return { data: m.slice(0, -NSYM), positions: [] };
  let errLoc = [1], oldLoc = [1];
  for (let i = 0; i < NSYM; i++) {
    const K = i + 1;
    let delta = synd[K];
    for (let j = 1; j < errLoc.length; j++) delta ^= mul(errLoc[errLoc.length - 1 - j], synd[K - j]);
    oldLoc = oldLoc.concat([0]);
    if (delta) {
      if (oldLoc.length > errLoc.length) { const nl = pScale(oldLoc, delta); oldLoc = pScale(errLoc, inv(delta)); errLoc = nl; }
      errLoc = pAdd(errLoc, pScale(oldLoc, delta));
    }
  }
  while (errLoc.length && errLoc[0] === 0) errLoc.shift();
  const errs = errLoc.length - 1;
  if (errs * 2 > NSYM) throw new Error('too many byte errors');
  const rev = errLoc.slice().reverse(), n = m.length, pos: number[] = [];
  for (let i = 0; i < n; i++) if (pEval(rev, pow(2, i)) === 0) pos.push(n - 1 - i);
  if (pos.length !== errs) throw new Error('could not locate errors');
  const coef = pos.map((p) => n - 1 - p);
  let eLoc = [1];
  for (const c of coef) eLoc = pMul(eLoc, pAdd([1], [pow(2, c), 0]));
  const rem = pDiv(pMul(synd.slice().reverse(), eLoc), [1].concat(new Array(eLoc.length).fill(0)))[1];
  const errEval = rem.slice().reverse();
  const X = coef.map((c) => pow(2, -(255 - c)));
  const E = new Array<number>(n).fill(0);
  X.forEach((Xi, i) => {
    const Xinv = inv(Xi);
    let prime = 1;
    X.forEach((Xj, j) => { if (j !== i) prime = mul(prime, 1 ^ mul(Xinv, Xj)); });
    const y = mul(Xi, pEval(errEval.slice().reverse(), Xinv));
    E[pos[i]] = div(y, prime);
  });
  m = pAdd(m, E);
  if (Math.max(...syndromes(m)) > 0) throw new Error('could not correct');
  return { data: m.slice(0, -NSYM), positions: pos.sort((a, b) => a - b) };
}

// ---------- bits and CRC-16/CCITT (binascii.crc_hqx, init 0xFFFF) ----------
export const toBits = (bytes: number[]): Bits => bytes.flatMap((x) => [7, 6, 5, 4, 3, 2, 1, 0].map((i) => (x >> i) & 1));
export const toBytes = (bits: Bits): number[] => {
  const o: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) { let v = 0; for (let j = 0; j < 8; j++) v = (v << 1) | bits[i + j]; o.push(v); }
  return o;
};
export function crc16(bytes: number[]): [number, number] {
  let c = 0xffff;
  for (const b of bytes) {
    c ^= b << 8;
    for (let i = 0; i < 8; i++) c = c & 0x8000 ? ((c << 1) ^ 0x1021) & 0xffff : (c << 1) & 0xffff;
  }
  return [c >> 8, c & 0xff];
}

// ---------- codecs ----------
export function encodeBody(bits: Bits, codec: Codec): Bits {
  if (codec === 'none') return bits.slice();
  if (codec === 'repeat3' || codec === 'repeat5') { const r = +codec.slice(-1); return bits.flatMap((b) => new Array(r).fill(b)); }
  if (codec === 'rs4') return toBits(rsEncode(toBytes(bits)));
  const out: Bits = [];
  for (let i = 0; i < bits.length; i += 4) {
    const [d0, d1, d2, d3] = bits.slice(i, i + 4);
    out.push(d0 ^ d1 ^ d3, d0 ^ d2 ^ d3, d0, d1 ^ d2 ^ d3, d1, d2, d3); // Lab 2 even-parity layout
  }
  return out;
}

export interface Unit { start: number; end: number; errors: number; ok: boolean }
export interface BodyDecode { bits: Bits | null; units: Unit[]; unit: string; limit: string }

export function decodeBody(bits: Bits, codec: Codec, sent: Bits): BodyDecode {
  const units: Unit[] = [];
  if (codec === 'none') {
    bits.forEach((b, i) => units.push({ start: i, end: i + 1, errors: +(b !== sent[i]), ok: b === sent[i] }));
    return { bits: bits.slice(), units, unit: 'bit', limit: 'No correction' };
  }
  if (codec === 'repeat3' || codec === 'repeat5') {
    const r = +codec.slice(-1), out: Bits = [];
    for (let i = 0; i < bits.length; i += r) {
      const blk = bits.slice(i, i + r), v = blk.reduce((a, b) => a + b, 0) > r / 2 ? 1 : 0;
      let e = 0; for (let j = 0; j < r; j++) e += +(blk[j] !== sent[i + j]);
      out.push(v); units.push({ start: i, end: i + r, errors: e, ok: v === sent[i] });
    }
    return { bits: out, units, unit: `${r}-bit block`, limit: `Majority vote fixes ${Math.floor(r / 2)} per block` };
  }
  if (codec === 'hamming74') {
    const out: Bits = [];
    for (let i = 0; i < bits.length; i += 7) {
      const c = bits.slice(i, i + 7);
      const s = (c[0] ^ c[2] ^ c[4] ^ c[6]) + 2 * (c[1] ^ c[2] ^ c[5] ^ c[6]) + 4 * (c[3] ^ c[4] ^ c[5] ^ c[6]);
      if (s) c[s - 1] ^= 1;
      let e = 0; for (let j = 0; j < 7; j++) e += +(bits[i + j] !== sent[i + j]);
      const d = [c[2], c[4], c[5], c[6]], truth = [sent[i + 2], sent[i + 4], sent[i + 5], sent[i + 6]];
      out.push(...d); units.push({ start: i, end: i + 7, errors: e, ok: d.every((v, k) => v === truth[k]) });
    }
    return { bits: out, units, unit: '7-bit word', limit: 'Fixes 1 bit per word' };
  }
  const rx = toBytes(bits), tx = toBytes(sent);
  rx.forEach((b, i) => units.push({ start: 8 * i, end: 8 * i + 8, errors: toBits([b ^ tx[i]]).reduce((a, x) => a + x, 0), ok: b === tx[i] }));
  try {
    const r = rsDecode(rx);
    units.forEach((u, i) => { if (r.positions.includes(i)) u.ok = true; });
    return { bits: toBits(r.data), units, unit: 'byte', limit: 'Fixes any 2 bytes' };
  } catch {
    return { bits: null, units, unit: 'byte', limit: 'Fixes any 2 bytes' };
  }
}

// ---------- block interleaver: write 8 rows, read columns, skip empty cells ----------
export function interleaverOrder(len: number, depth: number): number[] {
  const rows = Math.min(depth, len), cols = Math.ceil(len / rows), o: number[] = [];
  for (let c = 0; c < cols; c++) for (let r = 0; r < rows; r++) { const k = r * cols + c; if (k < len) o.push(k); }
  return o;
}
export const interleave = (bits: Bits, d: number) => (d <= 1 ? bits.slice() : interleaverOrder(bits.length, d).map((k) => bits[k]));
export const deinterleave = (bits: Bits, d: number) => {
  if (d <= 1) return bits.slice();
  const r = new Array<number>(bits.length);
  interleaverOrder(bits.length, d).forEach((k, j) => (r[k] = bits[j]));
  return r;
};

// ---------- packet ----------
export const BIT_MS = 200;
const PREAMBLE = [...Array.from({ length: 16 }, (_, i) => (i % 2 ? 0 : 1)), ...toBits([0xd3, 0x91])];
const GUARD = 8, HEADER = 48;
export type Segment = 'guard' | 'preamble' | 'header' | 'body';

export interface Packet {
  payload: number[]; codec: Codec; depth: number; header: number[];
  body: Bits; wireBody: Bits; bits: Bits;
  seg: Record<'preamble' | 'header' | 'body', [number, number]>;
}

export function makePacket(text: string, codec: Codec, seq = 3, depth = 1): Packet {
  const payload = Array.from(new TextEncoder().encode(text));
  if (payload.length < 1 || payload.length > 64) throw new Error('Use 1 to 64 bytes of text.');
  const header = [1, CODEC_ID[codec], payload.length, seq];
  const body = encodeBody(toBits(payload.concat(crc16(header.concat(payload)))), codec);
  const wireBody = interleave(body, depth);
  const bits = [...new Array(GUARD).fill(0), ...PREAMBLE, ...toBits(header.concat(crc16(header))), ...wireBody, ...new Array(GUARD).fill(0)];
  const p0 = GUARD, h0 = p0 + PREAMBLE.length, b0 = h0 + HEADER;
  return { payload, codec, depth, header, body, wireBody, bits, seg: { preamble: [p0, h0], header: [h0, b0], body: [b0, b0 + body.length] } };
}

export function segmentOf(p: Packet, i: number): Segment {
  if (i < p.seg.preamble[0] || i >= p.seg.body[1]) return 'guard';
  if (i < p.seg.header[0]) return 'preamble';
  if (i < p.seg.body[0]) return 'header';
  return 'body';
}

export type Stage = 'ok' | 'acquisition' | 'header' | 'decode' | 'crc' | 'undetected';
export interface Reception {
  stage: Stage; reason: string; text?: string;
  bodyRx?: Bits; decode?: BodyDecode; wireErrors: number;
}

export function receive(p: Packet, rx: Bits): Reception {
  const wireErrors = rx.reduce((a, b, i) => a + +(b !== p.bits[i]), 0);
  const preErr = rx.slice(...p.seg.preamble).reduce((a, b, i) => a + +(b !== p.bits[p.seg.preamble[0] + i]), 0);
  if (preErr > 2) return { stage: 'acquisition', wireErrors, reason: 'The start pattern was too damaged to lock on to, so the packet was never found.' };
  const hb = toBytes(rx.slice(...p.seg.header)), hc = crc16(hb.slice(0, 4));
  if (hc[0] !== hb[4] || hc[1] !== hb[5]) return { stage: 'header', wireErrors, reason: 'The header failed its CRC, so the receiver cannot trust the length or code.' };
  const bodyRx = deinterleave(rx.slice(...p.seg.body), p.depth);
  const decode = decodeBody(bodyRx, p.codec, p.body);
  if (!decode.bits) return { stage: 'decode', wireErrors, bodyRx, decode, reason: 'More than 2 bytes were damaged. Reed–Solomon cannot repair it.' };
  const data = toBytes(decode.bits), pl = data.slice(0, -2), c = crc16(p.header.concat(pl));
  const crcOk = c[0] === data[data.length - 2] && c[1] === data[data.length - 1];
  const text = new TextDecoder().decode(new Uint8Array(pl));
  const exact = pl.length === p.payload.length && pl.every((b, i) => b === p.payload[i]);
  const failed = decode.units.filter((u) => !u.ok).length;
  if (!crcOk) return { stage: 'crc', wireErrors, bodyRx, decode, text, reason: `${count(failed, decode.unit)} could not be repaired, so the CRC check rejected the message.` };
  if (!exact) return { stage: 'undetected', wireErrors, bodyRx, decode, text, reason: 'A wrong message passed the CRC. This is an undetected error.' };
  const fixed = decode.units.filter((u) => u.errors > 0).length;
  return { stage: 'ok', wireErrors, bodyRx, decode, text, reason: wireErrors === 0 ? 'Clean channel. Nothing to repair.' : fixed ? `Repaired ${count(fixed, 'damaged ' + decode.unit).toLowerCase()}. CRC valid.` : 'Errors fell outside the message body. CRC valid.' };
}

const WORDS = ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten'];
function count(n: number, unit: string) {
  return `${WORDS[n] ?? n} ${unit}${n === 1 ? '' : 's'}`;
}

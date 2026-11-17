import { describe, expect, it } from 'vitest';
import vectors from './vectors.json';
import { makePacket, receive, rsDecode, type Codec } from './protocol';

describe('matches the Python implementation', () => {
  it('builds bit-identical wire packets', () => {
    for (const [msg, codec, depth, bits] of vectors.packets as [string, Codec, number, string][]) {
      const p = makePacket(msg, codec, 3, depth);
      expect(p.bits.join(''), `${msg} ${codec} d${depth}`).toBe(bits);
      expect(receive(p, p.bits.slice()).stage).toBe('ok');
    }
  });

  it('agrees with reedsolo on corrupted codewords', () => {
    for (const [cw, expected] of vectors.rs as [number[], string | null][]) {
      let got: string | null;
      try { got = rsDecode(cw).data.map((b) => b.toString(16).padStart(2, '0')).join(''); } catch { got = null; }
      expect(got).toBe(expected);
    }
  });
});

describe('scenarios behave as reported', () => {
  const burst = (codec: Codec, depth: number, offset: number, len: number) => {
    const p = makePacket('A7k2M9q4', codec, 3, depth);
    const rx = p.bits.slice();
    for (let i = p.seg.body[0] + offset; i < p.seg.body[0] + offset + len; i++) rx[i] ^= 1;
    return receive(p, rx).stage;
  };
  it('interleaving rescues Hamming', () => {
    expect(burst('hamming74', 1, 8, 3)).toBe('crc');
    expect(burst('hamming74', 8, 8, 3)).toBe('ok');
  });
  it('interleaving breaks Reed–Solomon', () => {
    expect(burst('rs4', 1, 16, 8)).toBe('ok');
    expect(burst('rs4', 8, 16, 8)).toBe('decode');
  });
});

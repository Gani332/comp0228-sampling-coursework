# Optical Link frontend

An interactive simulator of the screen-to-camera link, plus the study's results.

```sh
cd frontend
npm install
npm run dev        # http://localhost:5173
npm test           # checks the TypeScript protocol against the Python implementation
npm run build      # static site in dist/
```

- `src/link/protocol.ts` is a port of `code/optical_link/protocol.py` (packet format, CRC-16, repetition, Hamming (7,4), Reed–Solomon with 4 parity bytes, depth-8 interleaver).
- `src/link/vectors.json` holds reference outputs from the Python code. Regenerate it with `npm run vectors` (needs Python and the repo's `code/` folder).
- `src/data/results.ts` holds figures transcribed from `report.tex` and `report_figures/`.

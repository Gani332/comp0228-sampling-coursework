# Original receiver compatibility snapshot

`receiver_layers_original.py` preserves the bytes of
`code/optical_link/receiver_layers.py` before the recording-comparison extension.
`snapshot.json` records its attribution and SHA-256, which matches the historical
frozen configuration. This is a compatibility reference, not a new historical
result. Do not update frozen study hashes to match experimental additions.

The original five receiver paths remain unchanged. The strict historical runner
still rejects modified source honestly; use the original git revision/worktree
for an exact frozen rerun. See `code/tools/recording_comparison.md` for the new
runner's evidence semantics and validation.

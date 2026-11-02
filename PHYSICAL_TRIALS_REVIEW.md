# Recording workflow review handoff

This branch adds an unexecuted LCD-to-phone recording workflow on top of dev. It does not contain new physical results. Start with Record_Physical_Trials.ipynb and PHYSICAL_TRIALS_GUIDE.md.

Scope: 82 transmissions, 21 videos, approximately 83 minutes of nominal footage. Main comparisons use RIYAADH, ADRIAN, OMAR, LARA, MANUNITED and PLEASEWORK, each with seven card-occlusion configurations and two glare configurations. Processing methods reuse the same video. Pilot and calibration are development data; acquisition challenges use frozen settings.

Please review with your agent before merging:

- Compatibility with current protocol/device/receiver code and matching encoder/decoder settings.
- Actual transmitted interleaving, CRC/sequence association, and inverse permutation before decoding.
- Timing assumptions, preservation of failures/retakes, and video-to-session association.
- Scientific scope: six matched message blocks, fixed disturbance duration per message, actual disturbance annotation, no synthetic or filter-output pseudoreplication.
- Pilot/calibration review before main collection; this branch provides recording and a trace-level pilot decoder, not a complete validated full-video analysis pipeline.

The USB transmitter and phone setup have not been operated for validation of this branch. The first four clean videos are required before physical readiness can be established. There is no request to merge automatically.

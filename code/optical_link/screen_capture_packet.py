"""Additive screen capture plans; the public wire header is unchanged."""
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
import uuid
from .protocol import CODECS, GUARD_BITS, HEADER_BITS, PREAMBLE, make_packet
from .coding_experiments import interleave

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / 'data/screen'


def positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Expected a finite positive duration.')
    return value


def bit_duration(value):
    if isinstance(value, bool) or int(value) != float(value) or not 200 <= int(value) <= 1000:
        raise ValueError('bit-ms must be an integer in 200..1000.')
    return int(value)


def identifier():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ') + '_' + uuid.uuid4().hex[:8]


def slug(message):
    # Prefix avoids Windows reserved device names, even for CON/NUL.
    return 'msg-' + (re.sub('[^A-Za-z0-9_-]', '_', message)[:24] or 'bytes')


def save_json(path, data):
    path = Path(path)
    if os.name == 'nt':
        # Atomic sidecars can exceed MAX_PATH in deeply nested checkouts.
        # Extended paths must be absolute; UNC shares use a separate prefix.
        absolute = str(path.resolve())
        if not absolute.startswith('\\\\?\\'):
            absolute = ('\\\\?\\UNC\\' + absolute[2:] if absolute.startswith('\\\\')
                        else '\\\\?\\' + absolute)
        path = Path(absolute)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def new_session(output, kind, message='capture'):
    parent = Path(output).expanduser().resolve()
    if parent.exists() and not parent.is_dir():
        raise ValueError('Output must be a directory.')
    name = identifier() + '__' + slug(message) + '__' + hashlib.sha256(message.encode()).hexdigest()[:12]
    folder = parent / kind / name
    folder.mkdir(parents=True, exist_ok=False)
    return folder


@dataclass
class PreparedTransmission:
    packet: object
    wire_bits: object
    depth: int
    bit_ms: int

    def record(self, ordinal):
        p = self.packet
        return dict(schema_version=1, ordinal=ordinal, payload_hex=p.payload.hex(),
                    payload_utf8=p.payload.decode('utf-8'), codec=p.codec, sequence=p.sequence,
                    interleaving=self.depth != 1, depth=self.depth, bit_ms=self.bit_ms,
                    packet_bits=len(self.wire_bits), body_length=len(p.body_bits),
                    body_bits=p.body_bits.tolist(), wire_bits=self.wire_bits.tolist(),
                    expected_airtime_seconds=len(self.wire_bits)*self.bit_ms/1000,
                    status='not_sent', slots=[])


def prepare(message, codec, sequence=1, interleaving=False, bit_ms=200):
    bit_ms = bit_duration(bit_ms)
    p = make_packet(message, codec, sequence)
    depth = 8 if interleaving else 1
    wire = p.bits.copy()
    first = GUARD_BITS + len(PREAMBLE) + HEADER_BITS
    wire[first:first+len(p.body_bits)] = interleave(p.body_bits, depth)
    return PreparedTransmission(p, wire, depth, bit_ms)


def batch_plan(message, bit_ms=200, sequence=1):
    if not isinstance(sequence, int) or sequence < 0 or sequence+9 > 255:
        raise ValueError('Batch sequence range must fit 0..255.')
    return [prepare(message, codec, sequence+i, on, bit_ms)
            for i, (codec, on) in enumerate((c, on) for c in CODECS for on in (False, True))]


def duration(plan, gap=8, countdown=5):
    positive(gap)
    positive(countdown)
    channel = sum(len(p.wire_bits)*p.bit_ms/1000 for p in plan)
    total = channel + (len(plan)-1)*gap + countdown
    return dict(channel_seconds=channel, total_seconds=total,
                recommended_timeout_after_first_seconds=math.ceil(total*1.1+60))

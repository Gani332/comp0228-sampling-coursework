"""Public optical packet format, framing, and Lab 2 coding conventions.

All bytes are sent most-significant bit first. Header is deliberately uncoded
for this first milestone; header failures must count as failed packets later.
"""
from dataclasses import dataclass
from binascii import crc_hqx
import numpy as np

PREAMBLE = np.array([1, 0]*8 + [int(b) for b in f'{0xD391:016b}'], dtype=np.uint8)
GUARD_BITS = 8
HEADER_BITS = 48  # version, codec, payload byte count, sequence, CRC16(header)
CODECS = {'none': 0, 'repeat3': 1, 'repeat5': 2, 'hamming74': 3, 'rs4': 4}
MAX_PAYLOAD = 64


def _rs_codec():
    # Pinned upstream implementation; see _vendor/README.txt and LICENSE.
    # Byte-symbol GF(256), four parity bytes, shortened to this packet length.
    from ._vendor.reedsolo import RSCodec
    return RSCodec(4, nsize=255, fcr=0, prim=0x11d, generator=2, c_exp=8)


def bits_array(bits):
    a = np.asarray(bits)
    if a.ndim != 1 or not np.all((a == 0) | (a == 1)):
        raise ValueError('Expected a one-dimensional binary sequence.')
    return a.astype(np.uint8)


def to_bits(data):
    return np.unpackbits(np.frombuffer(bytes(data), dtype=np.uint8))


def to_bytes(bits):
    a = bits_array(bits)
    if len(a) % 8:
        raise ValueError('Byte conversion needs a multiple of eight bits.')
    return np.packbits(a).tobytes()


def checksum(data):
    return crc_hqx(bytes(data), 0xFFFF).to_bytes(2, 'big')


def encode_body(bits, codec):
    a = bits_array(bits)
    if codec == 'none':
        return a.copy()
    if codec in ('repeat3', 'repeat5'):
        return np.repeat(a, int(codec[-1]))
    if codec == 'rs4':
        return to_bits(_rs_codec().encode(to_bytes(a)))
    if codec != 'hamming74' or len(a) % 4:
        raise ValueError('Unknown codec or incomplete Hamming data word.')
    # Same even-parity layout as Week 2/Lab 2/lab2_reference.py.
    d = a.reshape(-1, 4)
    c = np.zeros((len(d), 7), dtype=np.uint8)
    c[:, [2, 4, 5, 6]] = d
    c[:, 0] = d[:, 0] ^ d[:, 1] ^ d[:, 3]
    c[:, 1] = d[:, 0] ^ d[:, 2] ^ d[:, 3]
    c[:, 3] = d[:, 1] ^ d[:, 2] ^ d[:, 3]
    return c.ravel()


def decode_body(bits, codec):
    a = bits_array(bits)
    if codec == 'none':
        return a.copy()
    if codec in ('repeat3', 'repeat5'):
        r = int(codec[-1])
        if len(a) % r:
            raise ValueError('Incomplete repetition block.')
        return (a.reshape(-1, r).sum(axis=1) > r//2).astype(np.uint8)
    if codec == 'rs4':
        from ._vendor.reedsolo import ReedSolomonError
        data = to_bytes(a)
        if len(data) <= 4:
            raise ValueError('Incomplete Reed-Solomon codeword.')
        try:
            corrected, _, _ = _rs_codec().decode(data)
        except ReedSolomonError as exc:
            raise ValueError('Reed-Solomon could not correct this codeword.') from exc
        return to_bits(corrected)
    if codec != 'hamming74' or len(a) % 7:
        raise ValueError('Unknown codec or incomplete Hamming codeword.')
    c = a.reshape(-1, 7).copy()
    s1 = c[:, 0] ^ c[:, 2] ^ c[:, 4] ^ c[:, 6]
    s2 = c[:, 1] ^ c[:, 2] ^ c[:, 5] ^ c[:, 6]
    s4 = c[:, 3] ^ c[:, 4] ^ c[:, 5] ^ c[:, 6]
    syndrome = s1 + 2*s2 + 4*s4
    rows = np.flatnonzero(syndrome)
    c[rows, syndrome[rows]-1] ^= 1
    return c[:, [2, 4, 5, 6]].ravel()


def body_length(payload_bytes, codec):
    raw = (payload_bytes + 2)*8  # Data plus payload CRC16.
    if codec == 'none': return raw
    if codec in ('repeat3', 'repeat5'): return raw*int(codec[-1])
    if codec == 'hamming74': return raw//4*7
    if codec == 'rs4': return raw+32
    raise ValueError('Unknown codec.')


def parse_header(bits):
    if len(bits) != HEADER_BITS:
        raise ValueError('Incomplete header.')
    h = to_bytes(bits)
    if checksum(h[:4]) != h[4:]:
        raise ValueError('Header CRC failed; length and coding cannot be trusted.')
    version, code, n, sequence = h[:4]
    names = {v: k for k, v in CODECS.items()}
    if version != 1 or code not in names or not 1 <= n <= MAX_PAYLOAD:
        raise ValueError('Unsupported packet header.')
    return {'codec': names[code], 'payload_bytes': n, 'sequence': sequence, 'header': h[:4]}


@dataclass
class Packet:
    payload: bytes
    codec: str
    sequence: int
    bits: np.ndarray
    body_bits: np.ndarray


def make_packet(message='HI', codec='none', sequence=0):
    payload = message.encode('utf-8') if isinstance(message, str) else bytes(message)
    if not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError(f'Use 1..{MAX_PAYLOAD} UTF-8 bytes; start with HI.')
    if codec not in CODECS or not isinstance(sequence, int) or not 0 <= sequence <= 255:
        raise ValueError('Choose a supported codec and a sequence from 0 to 255.')
    h = bytes([1, CODECS[codec], len(payload), sequence])
    body = encode_body(to_bits(payload + checksum(h + payload)), codec)
    bits = np.concatenate([np.zeros(GUARD_BITS, np.uint8), PREAMBLE,
                           to_bits(h + checksum(h)), body,
                           np.zeros(GUARD_BITS, np.uint8)])
    if len(bits) > 4096:
        raise ValueError('Packet exceeds the controller buffer.')
    return Packet(payload, codec, sequence, bits, body)


def unpack_body(header, received):
    if len(received) != body_length(header['payload_bytes'], header['codec']):
        raise ValueError('Incomplete packet body.')
    decoded = decode_body(received, header['codec'])
    data = to_bytes(decoded)
    valid = checksum(header['header'] + data[:-2]) == data[-2:]
    return {'payload': data[:-2], 'crc_ok': valid, 'decoded_bits': decoded,
            'body_bits': bits_array(received), 'codec': header['codec'],
            'sequence': header['sequence']}

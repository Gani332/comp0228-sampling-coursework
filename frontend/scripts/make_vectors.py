"""Reference vectors from the Python implementation, used by the frontend tests."""
import json, random
from optical_link.protocol import _rs_codec
from optical_link.physical_campaign import wire_packet

random.seed(1)
out = {'packets': [], 'rs': []}
for msg in ['A7k2', 'A7k2M9q4', 'A7k2M9q4R6v8', 'MANUNITED', 'é ok']:
    for codec in ['none', 'repeat3', 'repeat5', 'hamming74', 'rs4']:
        for d in (1, 8):
            _, w = wire_packet({'payload_hex': msg.encode().hex(), 'codec': codec,
                                'sequence': '3', 'interleave_depth': str(d)})
            out['packets'].append([msg, codec, d, ''.join(map(str, w.bits))])
rs = _rs_codec()
for _ in range(400):
    n = random.randint(3, 20)
    cw = bytearray(rs.encode(bytes(random.randrange(256) for _ in range(n))))
    for p in random.sample(range(len(cw)), random.choice([0, 1, 2, 2, 3, 4])):
        cw[p] ^= random.randrange(1, 256)
    try:
        r = rs.decode(bytes(cw))[0].hex()
    except Exception:
        r = None
    out['rs'].append([list(cw), r])
print(json.dumps(out))

import itertools
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from optical_link.protocol import (make_packet, checksum, encode_body, decode_body,
                                   parse_header, unpack_body, GUARD_BITS, PREAMBLE, HEADER_BITS)
from optical_link.receiver import decode_trace, synthetic_trace
from optical_link.video import extract_trace, preview


class ProtocolTests(unittest.TestCase):
    def test_crc_standard_check_vector(self):
        self.assertEqual(checksum(b'123456789'), bytes.fromhex('29b1'))

    def test_all_hamming_words_and_single_bit_errors(self):
        for word in itertools.product([0, 1], repeat=4):
            encoded = encode_body(word, 'hamming74')
            for position in range(7):
                corrupted = encoded.copy()
                corrupted[position] ^= 1
                np.testing.assert_array_equal(decode_body(corrupted, 'hamming74'), word)

    def test_majority_code(self):
        for codec, r in [('repeat3', 3), ('repeat5', 5)]:
            for bit in [0, 1]:
                for errors in itertools.combinations(range(r), r//2):
                    encoded = encode_body([bit], codec)
                    encoded[list(errors)] ^= 1
                    np.testing.assert_array_equal(decode_body(encoded, codec), [bit])

    def test_header_and_body_error_detection(self):
        p = make_packet(b'HELLO')
        offset = GUARD_BITS+len(PREAMBLE)
        hb = p.bits[offset:offset+HEADER_BITS]
        header = parse_header(hb)
        bad_header = hb.copy()
        bad_header[10] ^= 1
        with self.assertRaisesRegex(ValueError, 'Header CRC'):
            parse_header(bad_header)
        bad_body = p.body_bits.copy()
        bad_body[3] ^= 1
        self.assertFalse(unpack_body(header, bad_body)['crc_ok'])


class ReceiverTests(unittest.TestCase):
    def test_all_codecs_with_jitter_and_dropped_frames(self):
        for codec in ['none', 'repeat3', 'repeat5', 'hamming74']:
            for seed in range(10):
                packet = make_packet('HI', codec, sequence=27)
                t, y = synthetic_trace(packet, seed=seed, noise=8, drop_fraction=0)
                # Isolated dropped frames leave samples in every bit. Losing a
                # whole slot is a distinct, expected failure tested below.
                keep = (np.arange(len(t))+seed) % 19 != 0
                t, y = t[keep], y[keep]
                r = decode_trace(t, y)
                self.assertTrue(r['crc_ok'], (codec, seed))
                self.assertEqual(r['payload'], b'HI')
                self.assertEqual(r['sequence'], 27)

    def test_longer_message_and_different_clock(self):
        p = make_packet('ROBOT', 'hamming74')
        t, y = synthetic_trace(p, bit_ms=400, fps=24, seed=22)
        r = decode_trace(t, y, bit_ms=400)
        self.assertTrue(r['crc_ok'])
        self.assertEqual(r['payload'], b'ROBOT')

    def test_truncated_and_low_contrast_recordings(self):
        p = make_packet()
        t, y = synthetic_trace(p, drop_fraction=0)
        with self.assertRaises(ValueError):
            decode_trace(t[:500], y[:500])
        with self.assertRaisesRegex(ValueError, 'contrast'):
            decode_trace(t, np.full_like(y, 40))

    def test_missing_whole_bit_is_not_interpolated_away(self):
        p = make_packet()
        t, y = synthetic_trace(p, drop_fraction=0)
        centre = 2.015+(GUARD_BITS+len(PREAMBLE)+HEADER_BITS+5.5)*.2
        keep = abs(t-centre) > .12
        with self.assertRaisesRegex(ValueError, 'Missing camera samples'):
            decode_trace(t[keep], y[keep])

    def test_real_video_pipeline_with_synthetic_pixels(self):
        # Exercises video decoding and FFprobe timestamp alignment, not hardware.
        p = make_packet()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'generated_test.avi'
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 30, (160, 120))
            self.assertTrue(writer.isOpened())
            for i in range(round((len(p.bits)*.2+4)*30)):
                index = int(np.floor((i/30-2)/.2))
                bit = p.bits[index] if 0 <= index < len(p.bits) else 0
                image = np.full((120, 160, 3), 15, np.uint8)
                image[25:95, 40:120] = 220 if bit else 25
                writer.write(image)
            writer.release()
            t, y, meta = extract_trace(path, (50, 35, 60, 50))
            self.assertEqual(preview(path).shape, (120, 160, 3))
            self.assertEqual(meta['frames'], len(t))
            decoded = decode_trace(t, y)
            self.assertTrue(decoded['crc_ok'])
            self.assertEqual(decoded['payload'], b'HI')


if __name__ == '__main__':
    unittest.main()

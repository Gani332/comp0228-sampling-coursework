"""Serial transport regressions: no hardware or real-time waits."""
import unittest
from unittest.mock import patch
from optical_link.device import Transmitter


class DeviceTests(unittest.TestCase):
    def test_long_command_survives_bounded_rx_queue(self):
        class BoundedUSB:
            def __init__(self):
                self.queue = bytearray()
                self.received = bytearray()
                self.dropped = 0
            def write(self, data):
                available = 256-len(self.queue)
                self.queue.extend(data[:available])
                self.dropped += max(0, len(data)-available)
                return len(data)  # USB accepted bytes even if firmware lost them.
            def drain(self, seconds):
                self.received.extend(self.queue)
                self.queue.clear()
        command = 'SEND 200 '+'101'*1365
        bulk = BoundedUSB()
        bulk.write((command+'\n').encode())
        self.assertGreater(bulk.dropped, 0)
        tx = Transmitter('fake'); tx.serial = BoundedUSB()
        with patch('optical_link.device.time.sleep', side_effect=tx.serial.drain):
            tx._write_command(command)
        tx.serial.drain(.01)
        self.assertEqual(tx.serial.dropped, 0)
        self.assertEqual(tx.serial.received, (command+'\n').encode())

    def test_missing_start_fails_without_waiting_for_packet_duration(self):
        clock = [0.0]
        class SilentUSB:
            def write(self, data): return len(data)
            def readline(self):
                clock[0] += .1
                return b''
        tx = Transmitter('fake'); tx.serial = SilentUSB()
        with patch('optical_link.device.time.monotonic', side_effect=lambda: clock[0]):
            with self.assertRaisesRegex(TimeoutError, 'No START acknowledgment'):
                tx.run('SEND 200 1', seconds=77, completed='DONE')
        self.assertLess(clock[0], 3.2)

    def test_mismatched_start_cannot_trigger_cue(self):
        class WrongUSB:
            def write(self, data): return len(data)
            def readline(self): return b'START bits=12 bit_ms=200\n'
        tx = Transmitter('fake'); tx.serial = WrongUSB()
        seen = []
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            tx.run('SEND 200 111', completed='DONE',
                   expected_start={'bits':3, 'bit_ms':200},
                   on_progress=lambda *args:seen.append(args))
        self.assertEqual(seen, [])

    def test_failed_stop_does_not_mask_original_error_and_closes_port(self):
        class DisconnectedUSB:
            closed = False
            def write(self, data): raise OSError('unplugged')
            def close(self): self.closed = True
        tx = Transmitter('fake'); tx.serial = DisconnectedUSB()
        tx.__exit__(TimeoutError, TimeoutError('original'), None)
        self.assertTrue(tx.serial.closed)

    def test_partial_write_is_an_error(self):
        class ShortUSB:
            def write(self, data): return len(data)-1
        tx = Transmitter('fake'); tx.serial = ShortUSB()
        with self.assertRaisesRegex(IOError, 'Incomplete serial'):
            tx._write_command('ID?')


if __name__ == '__main__':
    unittest.main()

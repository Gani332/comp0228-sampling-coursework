"""Explicit serial control. Importing this module never opens the controller."""
import json
import time
from pathlib import Path
import serial
from serial.tools import list_ports
from .protocol import bits_array


def ports():
    return [{'port': p.device, 'description': p.description,
             'vid': p.vid, 'pid': p.pid} for p in list_ports.comports()]


class Transmitter:
    def __init__(self, port):
        self.port = port
        self.serial = None

    def __enter__(self):
        self.serial = serial.Serial()
        self.serial.port = self.port
        self.serial.baudrate = 115200
        self.serial.timeout = 0.1
        self.serial.write_timeout = 3
        self.serial.dtr = False
        self.serial.rts = False
        self.serial.open()
        try:
            time.sleep(0.5)
            self.serial.reset_input_buffer()
            self.serial.write(b'ID?\n')
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                line = self.serial.readline().decode(errors='replace').strip()
                if line.startswith('OPTICAL:1 board=ESP32-S3'):
                    if 'busy=1' in line:
                        raise RuntimeError('Transmitter is busy; wait for it to finish.')
                    self.identity = line
                    return self
            raise RuntimeError('Optical firmware did not answer. Check the port and firmware.')
        except BaseException:
            self.serial.close()
            raise

    def __exit__(self, *exc):
        try:
            if exc[0] is not None:
                # Finish any truncated input before requesting STOP. Never mask
                # the original error if the USB cable was disconnected.
                try:
                    self.serial.write(b'\nSTOP\n')
                except Exception:
                    pass
        finally:
            self.serial.close()

    def _write_command(self, command):
        if '\n' in command or '\r' in command:
            raise ValueError('Send one command at a time.')
        data = (command+'\n').encode('ascii')
        # ESP32 native USB defaults to a 256-byte RX queue. A whole coded
        # packet can overflow it before loop() drains it, losing the newline.
        for offset in range(0, len(data), 64):
            chunk = data[offset:offset+64]
            if self.serial.write(chunk) != len(chunk):
                raise IOError('Incomplete serial command upload.')
            if offset+64 < len(data):
                time.sleep(0.01)

    def run(self, command, seconds=3, completed='OK', on_progress=None,
            expected_start=None):
        self.last_responses = []
        self._write_command(command)
        deadline = time.monotonic() + seconds
        start_deadline = time.monotonic() + 3
        needs_start = completed == 'DONE'
        lines = self.last_responses
        acknowledged_at = None
        while time.monotonic() < deadline:
            if needs_start and acknowledged_at is None and time.monotonic() >= start_deadline:
                raise TimeoutError('No START acknowledgment within 3 seconds of command upload. '
                                   'Transmission was not confirmed; check the USB connection.')
            line = self.serial.readline().decode(errors='replace').strip()
            if line:
                lines.append(line)
            if line.startswith(('ERR', 'STOPPED')):
                raise RuntimeError('\n'.join(lines))
            if line.startswith('START ') and acknowledged_at is None:
                if expected_start is not None:
                    fields = dict(part.split('=', 1) for part in line.split()[1:] if '=' in part)
                    if any(fields.get(key) != str(value) for key, value in expected_start.items()):
                        raise RuntimeError('START acknowledgment does not match the requested packet: '+line)
                acknowledged_at = time.monotonic()
                deadline = acknowledged_at + seconds
            if acknowledged_at is not None and on_progress is not None:
                on_progress(time.monotonic()-acknowledged_at, line)
            if not line:
                continue
            if line.startswith(completed):
                if needs_start and acknowledged_at is None:
                    raise RuntimeError('Received DONE without a START acknowledgment.')
                return lines
        raise TimeoutError('No completion received: ' + '\n'.join(lines))

    def blink(self):
        return self.run('BLINK', seconds=10, completed='DONE')

    def light(self, white):
        return self.run('WHITE' if white else 'BLACK')

    def transmit(self, packet, bit_ms=200, log_path=None, on_progress=None):
        if not isinstance(bit_ms, int) or not 200 <= bit_ms <= 1000:
            raise ValueError('Use an integer bit duration from 200 to 1000 ms.')
        bits = ''.join(map(str, bits_array(packet.bits)))
        log = {'port': self.port, 'identity': self.identity, 'bit_ms': bit_ms,
               'payload_hex': packet.payload.hex(), 'codec': packet.codec,
               'sequence': packet.sequence, 'transmitted_bits': bits,
               'scheduled_channel_seconds': len(bits)*bit_ms/1000,
               'host_started_unix': time.time(), 'status': 'started'}
        path = Path(log_path) if log_path else None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Never overwrite an earlier attempt, including a failed attempt.
            with path.open('x') as f:
                json.dump(log, f, indent=2)
        started = time.monotonic()
        try:
            log['serial_responses'] = self.run(f'SEND {bit_ms} {bits}',
                                            seconds=len(bits)*bit_ms/1000+5,
                                            completed='DONE', on_progress=on_progress,
                                            expected_start={'bits':len(bits), 'bit_ms':bit_ms})
            log['status'] = 'controller_completed'
        except BaseException as e:
            log['status'] = 'failed_or_interrupted'
            log['error'] = type(e).__name__ + ': ' + str(e)
            log['serial_responses'] = getattr(self, 'last_responses', []).copy()
            raise
        finally:
            log['host_elapsed_seconds'] = time.monotonic()-started
            if path:
                path.write_text(json.dumps(log, indent=2)+'\n')
        return log

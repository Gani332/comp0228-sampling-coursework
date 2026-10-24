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
        if exc[0] is not None:
            self.serial.write(b'STOP\n')
            self.serial.flush()
        self.serial.close()

    def run(self, command, seconds=3, completed='OK'):
        self.serial.write((command+'\n').encode('ascii'))
        self.serial.flush()
        deadline = time.monotonic() + seconds
        lines = []
        while time.monotonic() < deadline:
            line = self.serial.readline().decode(errors='replace').strip()
            if not line:
                continue
            lines.append(line)
            if line.startswith(('ERR', 'STOPPED')):
                raise RuntimeError('\n'.join(lines))
            if line.startswith(completed):
                return lines
        raise TimeoutError('No completion received: ' + '\n'.join(lines))

    def blink(self):
        return self.run('BLINK', seconds=10, completed='DONE')

    def light(self, white):
        return self.run('WHITE' if white else 'BLACK')

    def transmit(self, packet, bit_ms=200, log_path=None):
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
                                            completed='DONE')
            log['status'] = 'controller_completed'
        except BaseException as e:
            log['status'] = 'failed_or_interrupted'
            log['error'] = str(e)
            raise
        finally:
            log['host_elapsed_seconds'] = time.monotonic()-started
            if path:
                path.write_text(json.dumps(log, indent=2)+'\n')
        return log

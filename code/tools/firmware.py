"""Build, back up, install, or restore this ESP32-S3 prototype explicitly.

Run from a terminal, e.g. python tools/firmware.py build. No operation on import.
Flash writes only the app slot, after matching the original bootloader/layout.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT.parent/'.archive/evidence'
BACKUP = ROOT.parent/'.archive/backup'
FQBN = 'esp32:esp32:esp32s3:CDCOnBoot=cdc,USBMode=hwcdc'
CLI = '/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli'
ESPTOOL = Path.home()/'Library/Arduino15/packages/esp32/tools/esptool_py/5.0.dev1/esptool'


def run_logged(command, name, timeout=600):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    log = '\n'.join(line for line in (result.stdout+'\n'+result.stderr).splitlines()
                    if not line.startswith('MAC:'))
    (EVIDENCE/name).write_text(log+'\n')
    print(log[-3500:])
    if result.returncode:
        raise RuntimeError(f'Operation failed; see {EVIDENCE/name}.')


def device(port):
    matches = [p for p in list_ports.comports()
               if p.vid == 0x303a and p.pid == 0x1001 and p.device.startswith('/dev/cu.')
               and (port is None or p.device == port)]
    if len(matches) != 1:
        raise ValueError('Expected one native ESP32 USB device; specify its --port.')
    return matches[0]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hardware(args):
    p = device(args.port)
    esptool = Path(args.esptool).expanduser()
    executable = [sys.executable, str(esptool)] if esptool.suffix == '.py' else [str(esptool)]
    command = executable + ['--chip', 'esp32s3', '--port', p.device, '--baud', '921600']
    backup_dir = BACKUP
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = backup_dir/'manifest.json'
    fingerprint = hashlib.sha256((p.serial_number or '').encode()).hexdigest()
    if args.action == 'backup':
        if manifest_file.exists():
            raise ValueError('An original backup already exists; it will not be replaced.')
        backup = backup_dir/'original_esp32_flash.bin'
        if backup.exists():
            raise ValueError('A backup file already exists; inspect it before making another.')
        run_logged(command+['read_flash', '0', '0x800000', str(backup)], 'flash_backup.log')
        if backup.stat().st_size != 0x800000:
            raise ValueError('Backup is not the expected 8 MiB.')
        manifest_file.write_text(json.dumps({'file': backup.name, 'bytes': backup.stat().st_size,
            'sha256': sha(backup), 'usb_serial_sha256': fingerprint, 'chip': 'ESP32-S3'}, indent=2)+'\n')
        return
    manifest = json.loads(manifest_file.read_text())
    backup = backup_dir/manifest['file']
    if backup.stat().st_size != 0x800000 or sha(backup) != manifest['sha256']:
        raise ValueError('Original flash backup is missing or has changed.')
    if fingerprint != manifest['usb_serial_sha256']:
        raise ValueError('This is not the USB device associated with the backup.')
    if args.action == 'restore':
        run_logged(command+['write_flash', '--flash_mode', 'keep', '--flash_freq', 'keep',
                            '--flash_size', 'keep', '0', str(backup)], 'restore.log')
        return
    build = Path(args.build_dir).resolve()
    original = backup.read_bytes()
    for suffix, offset in [('bootloader', 0), ('partitions', 0x8000)]:
        new = (build/f'optical_tx.ino.{suffix}.bin').read_bytes()
        if original[offset:offset+len(new)] != new:
            raise ValueError(f'{suffix} differs from the actual backup; app-only upload is not appropriate.')
    app = build/'optical_tx.ino.bin'
    if not 0 < app.stat().st_size <= 0x140000:
        raise ValueError('Application does not fit the existing app partition.')
    run_logged(command+['write_flash', '0x10000', str(app)], 'upload.log')
    print('Application installed. Full original flash remains in', BACKUP)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'backup', 'flash', 'restore'])
    parser.add_argument('--port')
    parser.add_argument('--cli', default=CLI)
    parser.add_argument('--esptool', default=str(ESPTOOL))
    parser.add_argument('--build-dir', default=str(ROOT/'firmware/prebuilt'))
    args = parser.parse_args()
    if args.action != 'build':
        hardware(args)
        return
    build = ROOT/'build'
    config = ROOT/'arduino-cli.local.yaml'
    # Matches this Mac's installed Arduino 3.2.1 core; teammates can override CLI
    # or use Arduino IDE with the bundled library and documented board settings.
    config.write_text('directories:\n  data: '+json.dumps(str(Path.home()/'Library/Arduino15'))+
                      '\n  user: '+json.dumps(str(ROOT))+
                      '\n  downloads: '+json.dumps(str(ROOT/'.arduino-downloads'))+'\n')
    run_logged([args.cli, '--config-file', str(config), 'compile', '--fqbn', FQBN,
                '--library', str(ROOT/'vendor/LovyanGFX'), '--build-path', str(build),
                '--build-cache-path', str(ROOT/'cache'), str(ROOT/'firmware/optical_tx')], 'build.log')
    out = ROOT/'firmware/prebuilt'
    out.mkdir(exist_ok=True, parents=True)
    for suffix in ['bin', 'bootloader.bin', 'partitions.bin']:
        shutil.copy2(build/f'optical_tx.ino.{suffix}', out)


if __name__ == '__main__':
    main()

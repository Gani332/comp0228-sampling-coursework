"""Restore optional original videos from the pinned dataset release.

The main notebook runs from the tracked feature caches without these videos.
Only paths and SHA-256 digests listed in data/recordings_manifest.json are used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def destination(root, relative):
    p = PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] != 'data':
        raise ValueError('Invalid recording path: ' + relative)
    root = Path(root).resolve()
    target = root.joinpath(*p.parts)
    if not target.resolve().is_relative_to(root / 'data'):
        raise ValueError('Recording path leaves the data directory: ' + relative)
    return target


def verified_existing(root, item):
    path = destination(root, item['path'])
    if not path.exists():
        return False
    if not path.is_file() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
        raise ValueError('Existing file differs; it was not overwritten: ' + str(path))
    return True


def restore_archive(root, archive, group):
    archive = Path(archive)
    if archive.stat().st_size != group['bytes'] or digest(archive) != group['sha256']:
        raise ValueError('Archive size or SHA-256 does not match: ' + archive.name)
    expected = {x['path']: x for x in group['recordings']}
    if len(expected) != len(group['recordings']):
        raise ValueError('Duplicate paths in recording manifest.')
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) != len(expected) or {x.filename for x in members} != set(expected):
            raise ValueError('Archive members differ from the recording manifest.')
        # Validate every path and declared member size before writing anything.
        for member in members:
            item = expected[member.filename]
            destination(root, member.filename)
            mode = member.external_attr >> 16
            if member.is_dir() or stat.S_ISLNK(mode) or member.file_size != item['bytes']:
                raise ValueError('Invalid archive member: ' + member.filename)
            verified_existing(root, item)
        restored = 0
        for member in members:
            item = expected[member.filename]
            if verified_existing(root, item):
                continue
            target = destination(root, member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            # Verify a temporary file before placing it at the expected path.
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.restore-', delete=False) as out:
                    temp_path = Path(out.name)
                    with bundle.open(member) as source:
                        shutil.copyfileobj(source, out, length=4 * 1024 * 1024)
                if digest(temp_path) != item['sha256']:
                    raise ValueError('Recording SHA-256 does not match: ' + member.filename)
                # Never replace an existing file, including one created during download.
                try:
                    os.link(temp_path, target)
                    restored += 1
                except FileExistsError:
                    verified_existing(root, item)
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
        return restored


def download(url, target):
    request = urllib.request.Request(url, headers={'User-Agent': 'COMP0228-recordings/1.0'})
    with urllib.request.urlopen(request, timeout=120) as source, Path(target).open('wb') as out:
        shutil.copyfileobj(source, out, length=4 * 1024 * 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='List optional video groups; do not download.')
    parser.add_argument('--group', nargs='+', help='Restore selected group IDs; default: all four groups.')
    parser.add_argument('--from-dir', type=Path, help='Use already downloaded release ZIPs instead of the network.')
    parser.add_argument('--verify-only', action='store_true', help='Check existing original videos without downloading.')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'data/recordings_manifest.json').read_text())
    groups = manifest['groups']
    if args.list:
        for group in groups:
            print(f"{group['id']}: {len(group['recordings'])} videos, {group['bytes']/1024**2:.1f} MiB")
        print('No video download is required for normal notebook execution.')
        return
    selected = set(args.group or [g['id'] for g in groups])
    unknown = selected - {g['id'] for g in groups}
    if unknown:
        parser.error('Unknown group(s): ' + ', '.join(sorted(unknown)))
    missing = []
    for group in groups:
        if group['id'] not in selected:
            continue
        absent = [x for x in group['recordings'] if not verified_existing(ROOT, x)]
        if not absent:
            print(group['id'] + ': all original videos already match their hashes.')
            continue
        if args.verify_only:
            missing.extend(x['path'] for x in absent)
            continue
        print(f"{group['id']}: restoring {len(absent)} missing videos; archive {group['bytes']/1024**2:.1f} MiB", flush=True)
        if args.from_dir:
            count = restore_archive(ROOT, args.from_dir / group['asset'], group)
        else:
            with tempfile.TemporaryDirectory(prefix='comp0228-videos-') as temp:
                archive = Path(temp) / group['asset']
                download(group['url'], archive)
                count = restore_archive(ROOT, archive, group)
        print(f"{group['id']}: {count} restored; SHA-256 checks passed.", flush=True)
    if missing:
        raise SystemExit('Missing original videos:\n' + '\n'.join(missing))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Read-only source check. Does not edit files, read secrets or call Docker."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

bundle = Path(__file__).resolve().parent
root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
manifest = json.loads((bundle / 'manifest.json').read_text())
patch = bundle / 'market-io.patch'
sha = lambda value: hashlib.sha256(value).hexdigest()
if sha(patch.read_bytes()) != manifest['patch_sha256']:
    raise SystemExit('STOP: patch checksum mismatch')
unknown, before, after = [], 0, 0
for entry in manifest['files']:
    path = root / entry['path']
    value = sha(path.read_bytes()) if path.is_file() else None
    if value in entry['after_sha256']:
        after += 1
    elif value in entry['before_sha256'] or (entry['new_file'] and value is None and not path.exists()):
        before += 1
    else:
        unknown.append(entry['path'])
if unknown:
    print('STOP: source differs from both reviewed local baselines; rebase and retest against actual server source:')
    print('\n'.join(unknown))
    raise SystemExit(1)
if after == len(manifest['files']):
    print('All patch files already match a reviewed patched version.')
    raise SystemExit(0)
if after:
    raise SystemExit('STOP: partially applied patch; inspect source before continuing')
result = subprocess.run(['git', 'apply', '--check', str(patch)], cwd=root)
if result.returncode:
    raise SystemExit(result.returncode)
head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, capture_output=True)
print('Source fingerprints and git apply --check passed. Server HEAD:', head.stdout.strip() or '(no git HEAD)')
print('This verifies touched source only. Review effective Compose config and run tests before deployment.')

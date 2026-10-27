#!/usr/bin/env python3
"""Read-only Google-only candidate/source verification. No database/network access."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

bundle = Path(__file__).resolve().parent
root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
manifest = json.loads((bundle / 'manifest.json').read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
patch = bundle / 'google-only.patch'
if sha(patch.read_bytes()) != manifest['patch_sha256']:
    raise SystemExit('STOP: patch checksum mismatch')
for entry in manifest['prerequisites']:
    path = root / entry['path']
    if not path.is_file() or sha(path.read_bytes()) != entry['sha256']:
        raise SystemExit('STOP: prerequisite differs or is missing: ' + entry['path'])
before = after = 0
unknown = []
for entry in manifest['files']:
    path = root / entry['path']
    value = sha(path.read_bytes()) if path.is_file() else None
    if value == entry['after_sha256']:
        after += 1
    elif value == entry['before_sha256'] and (value is not None or not path.exists()):
        before += 1
    else:
        unknown.append(entry['path'])
if unknown:
    print('STOP: rebase/review against actual server source before release:')
    print('\n'.join(unknown))
    raise SystemExit(1)
if after == len(manifest['files']):
    print('All scoped files match the reviewed patched version. Database schema/runtime still require separate verification.')
    raise SystemExit(0)
if after:
    raise SystemExit('STOP: partially applied patch; inspect before continuing')
subprocess.run(['git', 'apply', '--check', str(patch)], cwd=root, check=True)
print('Reviewed pre-task source fingerprints and git apply --check passed.')
print('Candidate only: this does not verify server database, Google Console, images, environment or Compose.')

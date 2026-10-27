#!/usr/bin/env python3
"""Read effective compose JSON from stdin, never print credentials."""
import json
import sys
from urllib.parse import urlparse

config = json.load(sys.stdin)
backend = config.get('services', {}).get('backend', {})
env = backend.get('environment', {})
if isinstance(env, list):
    env = dict(item.split('=', 1) for item in env if '=' in item)
if str(env.get('DEBUG', '')).lower() not in {'false', '0'}:
    raise SystemExit('STOP: effective backend DEBUG must be false')
if str(env.get('APP_ENV', '')).lower() not in {'production', 'prod', 'staging'}:
    raise SystemExit('STOP: review effective backend APP_ENV')
host = (urlparse(env.get('DATABASE_URL', '')).hostname or '').lower()
if not (host.endswith('.supabase.co') or host.endswith('.supabase.com')):
    raise SystemExit('STOP: DATABASE_URL is not a recognizable Supabase endpoint; verify configuration manually. No changes made.')
print('Effective DEBUG=false; APP_ENV checked; DATABASE_URL targets Supabase. No credentials printed.')
print('Only explicitly selected backend/frontend may be updated with --no-deps.')

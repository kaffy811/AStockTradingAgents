# Frontend npm ci Lockfile Audit

- Phase: 6V-P1.6.4
- Base acceptance SHA: `6938a3908d019423fcc1a7252efb53b3e9dd13d0`
- Node: `v22.15.0`
- npm: `10.9.2`
- package manager field: not declared
- package-lock lockfileVersion: `3`

## Initial failure

`npm ci` failed in a clean frontend because `package-lock.json` was missing:

- `node_modules/vitest/node_modules/@esbuild/linux-s390x`
- version: `0.28.1`
- type: optional platform package

## Root cause

The lockfile was incomplete for Vitest's nested esbuild optional platform set. The missing entry is an optional Linux s390x package under Vitest's nested dependency tree, not a normal runtime dependency.

## Fix

Ran `npm install --package-lock-only --no-audit --no-fund` in the p164 clean clone and reviewed the diff. The only lockfile change is the optional `@esbuild/linux-s390x@0.28.1` entry under `node_modules/vitest/node_modules/`.

No dependency was added to `package.json`, and no optional dependency was moved into normal dependencies.

## Verification

- `npm ci --no-audit --no-fund --loglevel=verbose`: passed after lockfile update.
- `npm ci --include=optional --os=darwin --cpu=arm64 --no-audit --no-fund`: passed and installed `@rolldown/binding-darwin-arm64`.
- Plain `npm ci --no-audit --no-fund` from no `node_modules`: passed after cache/native binding hydration.
- Repeated plain `npm ci --no-audit --no-fund` from no `node_modules`: passed.
- `npm test`: `679 passed`.
- `npm run build`: passed.

## Notes

Verbose npm output reported skipped optional packages for non-current platforms. That is expected for optional native packages. The current Darwin ARM64 native binding was verified present after the successful clean install.

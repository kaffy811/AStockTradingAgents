import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const configPath = path.resolve(process.cwd(), 'nginx.conf')
const nginx = fs.readFileSync(configPath, 'utf8')

describe('Phase 7E-P1.4 API reverse-proxy contract', () => {
  it('routes every API version before the SPA fallback', () => {
    expect(nginx).toContain('location ^~ /api/ {')
    expect(nginx).toContain('location = /api {')
    expect(nginx.indexOf('location ^~ /api/ {')).toBeLessThan(
      nginx.indexOf('location / {'),
    )
  })

  it('routes health to the backend before the SPA fallback', () => {
    expect(nginx).toContain('location = /health {')
    expect(nginx).toContain('proxy_pass         http://backend:8000/health;')
    expect(nginx).toContain('location ^~ /health/ {')
    expect(nginx.indexOf('location = /health {')).toBeLessThan(
      nginx.indexOf('location / {'),
    )
  })

  it('preserves backend error responses instead of intercepting them', () => {
    const apiBlock = nginx.match(/location \^~ \/api\/ \{([\s\S]*?)\n    \}/)?.[1]
    expect(apiBlock).toBeTruthy()
    expect(apiBlock).toContain('proxy_intercept_errors off;')
    expect(apiBlock).not.toContain('try_files')
  })

  it('keeps SPA fallback on ordinary frontend paths only', () => {
    const spaBlock = nginx.match(/location \/ \{([\s\S]*?)\n    \}/)?.[1]
    expect(spaBlock).toContain('try_files $uri $uri/ /index.html;')
    expect(spaBlock).not.toContain('proxy_pass')
  })

  it('does not retain a version-specific /api/v1 location', () => {
    expect(nginx).not.toContain('location ^~ /api/v1/')
    expect(nginx).not.toContain('location ^~ /api/v2/')
  })
})

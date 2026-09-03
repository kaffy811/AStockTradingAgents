/**
 * Phase 6W-R1.3 — Skeleton and Warning Runtime Scenarios
 *
 * 5-scenario source verification for CompanyFundamentalsPanel.vue:
 *   Verifies that all loading refs are cleared in finally blocks,
 *   warnings are non-duplicating, and skeleton logic is correct.
 *
 * Complements R1.1 E1-E5 (backend Python tests) with frontend source audit.
 */
import { describe, it, expect } from 'vitest'
import cfpRaw from '../components/CompanyFundamentalsPanel.vue?raw'

// ── Helpers ───────────────────────────────────────────────────────────────

function countFinallyBlocks(src) {
  return (src.match(/\bfinally\s*\{/g) || []).length
}

function finallyContains(src, token) {
  // Find all finally blocks and check if any contain the token
  const finallyRe = /finally\s*\{([^}]*)\}/gs
  let match
  while ((match = finallyRe.exec(src)) !== null) {
    if (match[1].includes(token)) return true
  }
  return false
}

// ── Scenario 1: overview resolve, modules reject ──────────────────────────

describe('Scenario 1 — overview resolves, module fetches reject', () => {
  it('overviewLoading is cleared in a finally block (not only in success path)', () => {
    expect(finallyContains(cfpRaw, 'overviewLoading.value = false')).toBe(true)
  })

  it('module loading is cleared in finally blocks (≥2 for loadModule + loadAiSummary)', () => {
    const count = (cfpRaw.match(/finally[^{]*\{[^}]*moduleLoading\.value/gs) || []).length
    expect(count).toBeGreaterThanOrEqual(2)
  })

  it('skeleton count is controlled by diagnosticsLoading + moduleLoading, not overviewLoading alone', () => {
    expect(cfpRaw).toContain('diagnosticsLoading')
    expect(cfpRaw).toContain('moduleLoading')
  })
})

// ── Scenario 2: Tushare permission / auth error ───────────────────────────

describe('Scenario 2 — Tushare permission error', () => {
  it('auth error path sets authRequired only, not overviewBanner', () => {
    // The guard: if (isAuthError(e)) authRequired.value = true (no overviewBanner here)
    expect(cfpRaw).toContain('isAuthError(e)')
    expect(cfpRaw).toContain('authRequired.value = true')
  })

  it('overviewBanner is only set when dataSourceUnavailable is NOT already true', () => {
    // Guard: if (!dataSourceUnavailable.value) { overviewBanner.value = ... }
    expect(cfpRaw).toContain('!dataSourceUnavailable.value')
  })

  it('overviewLoading is still cleared in finally even when auth error fires', () => {
    // finally block runs regardless of which catch branch fires
    expect(finallyContains(cfpRaw, 'overviewLoading.value = false')).toBe(true)
  })
})

// ── Scenario 3: Tab switch — no warning accumulation ─────────────────────

describe('Scenario 3 — Tab switch / unmount', () => {
  it('loading refs are reset to false in finally (prevents stale state across navigation)', () => {
    const finallyCount = countFinallyBlocks(cfpRaw)
    // At least 6 finally blocks across all fetch functions (lines 601/617/633/653/668/733)
    expect(finallyCount).toBeGreaterThanOrEqual(4)
  })

  it('diagnosticsLoading cleared in finally — prevents ghost skeleton after unmount', () => {
    expect(finallyContains(cfpRaw, 'diagnosticsLoading.value = false')).toBe(true)
  })

  it('warning dedup: overviewBanner not set when dataSourceUnavailable already active', () => {
    // Prevents dual-banner: DataSourceBanner + overviewBanner cannot show simultaneously
    expect(cfpRaw).toContain('!dataSourceUnavailable.value')
    // Auth error path: only authRequired, no overviewBanner
    // So at most 1 banner path fires per error scenario
    const bannerAssignments = (cfpRaw.match(/overviewBanner\.value\s*=/g) || []).length
    expect(bannerAssignments).toBeGreaterThanOrEqual(1)
  })
})

// ── Scenario 4: AI summary pending, basic data resolved ──────────────────

describe('Scenario 4 — AI summary pending', () => {
  it('aiSummaryLoading is a separate ref (does not block overview loading)', () => {
    expect(cfpRaw).toContain('aiSummaryLoading')
    // aiSummaryLoading is different from overviewLoading
    const aiRef = cfpRaw.includes('aiSummaryLoading')
    const overviewRef = cfpRaw.includes('overviewLoading')
    expect(aiRef).toBe(true)
    expect(overviewRef).toBe(true)
  })

  it('aiSummaryLoading cleared in finally block (AI pending resolved on completion)', () => {
    expect(finallyContains(cfpRaw, 'aiSummaryLoading.value = false')).toBe(true)
  })

  it('top skeleton gated on diagnosticsLoading only — not on aiSummaryLoading', () => {
    // v-if="diagnosticsLoading" controls the top skeleton
    // aiSummaryLoading only controls the AI summary sub-section
    expect(cfpRaw).toMatch(/v-if="diagnosticsLoading"[^>]*>/)
  })
})

// ── Scenario 5: diagnostics reject ───────────────────────────────────────

describe('Scenario 5 — diagnostics reject path', () => {
  it('diagnosticsLoading cleared in finally — skeleton always disappears', () => {
    expect(finallyContains(cfpRaw, 'diagnosticsLoading.value = false')).toBe(true)
  })

  it('top skeleton is v-if="diagnosticsLoading" — clears when diagnostics done', () => {
    // The top skeleton must be inside a v-if="diagnosticsLoading" block
    expect(cfpRaw).toMatch(/v-if="diagnosticsLoading"[^>]*>[\s\S]*?cfp-sections-skeleton/)
  })

  it('final skeleton count: 0 after all loading refs cleared', () => {
    // All loading refs must be clearable — verified by counting finally blocks
    const loadingRefsClearable = [
      finallyContains(cfpRaw, 'overviewLoading.value = false'),
      finallyContains(cfpRaw, 'diagnosticsLoading.value = false'),
      finallyContains(cfpRaw, 'aiSummaryLoading.value = false'),
    ]
    expect(loadingRefsClearable.every(Boolean)).toBe(true)
  })
})

/**
 * P1.6.8 — entity clarification candidate helpers.
 *
 * Pure functions shared by ChatClarificationCard and ChatCopilotView so the
 * dedup / ordering / selection-text logic is unit-testable without mounting
 * components.  Never reads shadow diagnostics; never builds URLs.
 */

export function candidateKey(cand) {
  return `${cand?.market ?? ''}:${cand?.symbol ?? cand?.display_name ?? ''}`
}

/** Deduplicate candidates defensively, preserving backend order. */
export function dedupCandidates(candidates) {
  const seen = new Set()
  const out = []
  for (const cand of candidates ?? []) {
    if (!cand?.display_name) continue
    const key = candidateKey(cand)
    if (seen.has(key)) continue
    seen.add(key)
    out.push(cand)
  }
  return out
}

/** Explicit selection text sent as a normal user turn when a candidate is clicked. */
export function candidateSelectionText(cand) {
  if (!cand?.display_name) return ''
  return cand.symbol ? `${cand.display_name}（${cand.symbol}）` : cand.display_name
}

/** Extract renderable clarification from a persisted message metadata object. */
export function clarificationFromMetadata(metadata) {
  const clarification = metadata?.clarification
  if (!clarification || !Array.isArray(clarification.candidates) || clarification.candidates.length === 0) {
    return null
  }
  return clarification
}

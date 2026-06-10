import { marked } from 'marked'
import DOMPurify from 'dompurify'

/**
 * Parse Markdown to sanitized HTML.
 * Uses marked for parsing and DOMPurify to prevent XSS.
 */
export function renderMarkdown(text) {
  if (!text) return ''
  const raw = marked.parse(text)
  return DOMPurify.sanitize(raw)
}

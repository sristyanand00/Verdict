// Turns an API error into a short title plus the server's own text.
// The server writes its "detail" for people (402, 429, 503 and 504 include "You were not charged"),
// so that text is always shown as it is, under a short title.

import { ApiError } from './api'

export function describeError(e: unknown, fallbackTitle = 'Could not check this question'): { title: string; text: string } {
  const text = e instanceof Error ? e.message : 'Something went wrong.'
  if (e instanceof ApiError) {
    if (e.status === 401) return { title: 'Please log in again', text }
    if (e.status === 402) return { title: 'No credits left', text }
    if (e.status === 403) return { title: 'Not allowed', text }
    if (e.status === 429) return { title: 'Too many requests at once', text }
    if (e.status === 503) return { title: 'The model is not available right now', text }
    if (e.status === 504) return { title: 'This question took too long', text }
    if (e.status >= 500) return { title: 'The server could not finish this', text }
  }
  if (e instanceof TypeError) return { title: 'Could not reach the server', text: 'Check that the Verdict server is running, then try again.' }
  return { title: fallbackTitle, text }
}

export function errorText(e: unknown, fallback = 'Something went wrong.'): string {
  return e instanceof Error && e.message ? e.message : fallback
}

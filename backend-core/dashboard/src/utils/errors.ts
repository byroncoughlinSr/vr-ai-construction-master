/** The message to show for a failed API call: FastAPI's `detail` (a string, or
 * a list of validation errors), else the error's own message. */
export function errorMessage(err: unknown, fallback = 'Something went wrong'): string {
  const e = err as { response?: { status?: number; data?: { detail?: unknown } }; message?: string }
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map(d => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d)))
      .join('; ')
  }
  if (e?.response?.status === 429) return 'Too many requests — wait a minute and try again'
  return e?.message || fallback
}

// Display helpers shared by every page. Dates from the API are ISO strings; a
// date-only string ("2026-11-02") is a calendar day, so it is read as local
// midnight rather than UTC (which would show the day before west of Greenwich).

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null
  if (DATE_ONLY.test(value)) {
    const [y, m, d] = value.split('-').map(Number)
    return new Date(y, m - 1, d)
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** Today as "YYYY-MM-DD" in local time (for date inputs). */
export function todayIso(offsetDays = 0): string {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const compactCurrency = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1
})

export function formatCurrency(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : currency.format(value)
}

export function formatCompactCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Math.abs(value) < 10000 ? currency.format(value) : compactCurrency.format(value)
}

/** A performance index (CPI/SPI): two decimals, or a dash when there is no data yet. */
export function formatIndex(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toFixed(2)
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined ? '—' : `${value.toFixed(digits)}%`
}

export function formatDate(value: string | null | undefined): string {
  const date = parseDate(value)
  return date ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'
}

export function formatShortDate(value: string | null | undefined): string {
  const date = parseDate(value)
  return date ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'
}

export function formatDateTime(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return '—'
  return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

/** "today", "tomorrow", "in 5 days", "3 days ago" (by calendar day). */
export function formatRelativeDay(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return '—'
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((start(date) - start(new Date())) / 86_400_000)
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days === -1) return 'yesterday'
  return days > 0 ? `in ${days} days` : `${-days} days ago`
}

export function isPastDay(value: string | null | undefined): boolean {
  const date = parseDate(value)
  if (!date) return false
  const today = new Date()
  return date < new Date(today.getFullYear(), today.getMonth(), today.getDate())
}

export function initials(name: string | null | undefined): string {
  const parts = (name ?? '').trim().split(/\s+/).filter(p => /^[\p{L}\p{N}]/u.test(p))
  if (!parts.length) return '?'
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}

export function titleCase(value: string | null | undefined): string {
  return (value ?? '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

// Badge colors for the statuses the backend uses, so every page shows them alike.

const colors: Record<string, Record<string, string>> = {
  task: { pending: 'blue-grey-5', in_progress: 'primary', completed: 'positive', blocked: 'negative' },
  phase: { pending: 'blue-grey-5', in_progress: 'primary', completed: 'positive', delayed: 'negative' },
  priority: { low: 'blue-grey-5', medium: 'primary', high: 'warning', critical: 'negative' },
  changeOrder: { draft: 'blue-grey-5', submitted: 'warning', approved: 'positive', rejected: 'negative' },
  permit: { applied: 'info', approved: 'teal', issued: 'positive', expired: 'negative', rejected: 'negative' },
  punch: { open: 'warning', in_progress: 'primary', ready: 'info', closed: 'positive' },
  inspection: { scheduled: 'info', passed: 'positive', failed: 'negative', cancelled: 'blue-grey-5' },
  equipment: { available: 'positive', in_use: 'primary', maintenance: 'warning', out_of_service: 'negative' },
  bom: { available: 'blue-grey-5', ordered: 'warning', delivered: 'teal', used: 'positive' },
  expense: { pending: 'warning', paid: 'positive' },
  project: { planning: 'info', active: 'primary', paused: 'warning', completed: 'positive' },
  severity: { high: 'negative', medium: 'warning', low: 'info' }
}

export type StatusKind = keyof typeof colors

export function statusColor(kind: StatusKind, status: string | null | undefined): string {
  return colors[kind][status ?? ''] ?? 'blue-grey-5'
}

export const TASK_STATUS_OPTIONS = [
  { value: 'pending', label: 'Not started' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'completed', label: 'Completed' },
  { value: 'blocked', label: 'Blocked' }
]

export const PUNCH_STATUS_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'ready', label: 'Ready for sign-off' },
  { value: 'closed', label: 'Closed' }
]

export const PRIORITY_OPTIONS = ['low', 'medium', 'high', 'critical'].map(v => ({
  value: v, label: v.charAt(0).toUpperCase() + v.slice(1)
}))

export const PROJECT_STATUS_OPTIONS = [
  { value: 'planning', label: 'Planning' },
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'completed', label: 'Completed' }
]

/** CPI/SPI: ≥ 1 on track, ≥ 0.9 watch, below that a problem; null = no data. */
export function indexColor(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'blue-grey-5'
  if (value >= 1) return 'positive'
  if (value >= 0.9) return 'warning'
  return 'negative'
}

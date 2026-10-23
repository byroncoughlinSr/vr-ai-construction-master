// Shapes returned by the backend's project-controls, resources and materials
// routes (app/api/v1/project_controls.py, resources.py, materials.py). Dates are
// ISO strings ("2026-11-02"); money is USD.

export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'blocked' | 'cancelled'
export type TaskPriority = 'low' | 'medium' | 'high' | 'critical'

export interface ScheduleTask {
  id: number
  phase_id: number
  name: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  task_order: number | null
  duration_days: number
  planned_start: string | null
  planned_end: string | null
  actual_start: string | null
  actual_end: string | null
  budgeted_cost: number
  actual_cost: number
  // An inspection task can't be completed until its inspection passes.
  requires_inspection: boolean
  kind: 'task' | 'approval' | 'milestone' | 'inspection' | 'permit'
  roles: string[]
  assignee: string | null
  late: boolean
}

export interface SchedulePhase {
  id: number
  name: string
  description: string | null
  phase_order: number
  status: 'pending' | 'in_progress' | 'completed' | 'delayed'
  progress: number
  duration_days: number
  planned_start: string | null
  planned_end: string | null
  actual_start: string | null
  actual_end: string | null
  budgeted_cost: number
  actual_cost: number
  late: boolean
  tasks: ScheduleTask[]
}

export interface ScheduleSummary {
  progress: number
  baselined: boolean
  planned_start: string | null
  planned_finish: string | null
  total_days: number
  phase_count: number
  current_phase: { id: number; name: string } | null
  tasks: { total: number; completed: number; in_progress: number; blocked: number; late: number }
}

export interface Schedule extends ScheduleSummary {
  project_id: number
  // The plan lives in pm-mcp; this is its project there.
  pm_project_id: number | null
  pm_available: boolean
  phases: SchedulePhase[]
}

// A pm-mcp construction plan template (GET /projects/{id}/construction-templates).
export interface ConstructionTemplate {
  key: string
  name: string
  description: string
  source: 'builtin' | 'custom'
  project_type: string | null
  phases: string[]
  task_count: number
  roles: string[]
}

export interface BudgetSummary {
  target_budget: number | null
  baseline: number
  approved_change_orders: number
  pending_change_orders: number
  bac: number
  planned_value: number | null
  earned_value: number
  actual_cost: number
  unpaid: number
  cost_variance: number
  schedule_variance: number | null
  cpi: number | null
  spi: number | null
  eac: number
  etc: number
  vac: number
  percent_spent: number
  materials_cost: number
  by_phase: Array<{ phase_id: number; name: string; budgeted: number; earned: number; actual: number }>
  by_category: Array<{ category: ExpenseCategory; actual: number }>
}

export type ExpenseCategory = 'labor' | 'materials' | 'equipment' | 'subcontract' | 'permits' | 'other'

export interface Expense {
  id: number
  vendor: string
  description: string | null
  category: ExpenseCategory
  amount: number
  status: 'pending' | 'paid'
  date: string | null
  invoice_number: string | null
  phase_id: number | null
  phase_name: string | null
  created_at: string | null
}

export type ChangeOrderStatus = 'draft' | 'submitted' | 'approved' | 'rejected' | 'void'

export interface ChangeOrder {
  id: number
  project_id: number
  number: number
  code: string
  title: string
  description: string | null
  cost_impact: number
  schedule_impact_days: number
  status: ChangeOrderStatus
  requested_by: string | null
  floor_plan_version: number | null
  decided_at: string | null
  created_at: string | null
}

export type PermitStatus =
  'not_applied' | 'applied' | 'in_review' | 'corrections_required' | 'approved' | 'rejected' | 'expired'

export interface Permit {
  id: number
  project_id: number
  title: string
  permit_number: string | null
  permit_type: string
  description: string | null
  jurisdiction: string | null
  status: PermitStatus
  application_date: string | null
  issued_date: string | null
  expiration_date: string | null
  permit_fee: number
  conditions: string | null
  contact_name: string | null
  contact_phone: string | null
  contact_email: string | null
  // The plan's permit task that waits on this permit, if any.
  task_id: number | null
}

export type InspectionStatus = 'not_scheduled' | 'scheduled' | 'passed' | 'failed' | 'partial' | 'cancelled'

export interface InspectionAttempt {
  date: string
  result: 'passed' | 'failed' | 'partial'
  notes: string
  inspector: string | null
}

export interface Inspection {
  id: number
  project_id: number
  title: string
  permit_id: number | null
  permit_number: string | null
  task_id: number | null
  inspection_type: string
  description: string | null
  inspector_name: string | null
  scheduled_date: string | null
  actual_date: string | null
  status: InspectionStatus
  result_details: string | null
  critical_findings: string | null
  requires_followup: boolean
  attempts: InspectionAttempt[]
  // Set on the response to recording a result: the task it completed, or the
  // correction task it added.
  completed_task?: number
  correction_task?: number
}

export interface ComplianceSummary {
  permits_total: number
  permits_active: number
  inspections_upcoming: number
  inspections_passed: number
  inspections_failed: number
  pass_rate: number | null
}

export interface AttentionItem {
  kind: string
  severity: 'high' | 'medium' | 'low'
  title: string
  detail: string
  route: string
}

export interface FloorPlanBrief {
  id: number
  version: number
  name: string
  rooms: string[]
  footprint_ft: [number, number] | null
  image_url: string | null
  change_note: string | null
  created_at: string | null
}

export interface ProjectOverview {
  project_id: number
  pm_project_id: number | null
  pm_available: boolean
  floor_plan: FloorPlanBrief | null
  schedule: ScheduleSummary
  budget: BudgetSummary
  compliance: ComplianceSummary
  punch_list: PunchSummary
  clients: Array<{ id: number; name: string; stage: string }>
  materials: { count: number; ordered: number; delivered: number }
  attention: AttentionItem[]
}

export interface CrewMember {
  id: number
  name: string
  role: string
  email: string | null
  phone: string | null
  hourly_rate: number
  max_hours_per_week: number
  is_available: boolean
  project_id: number | null
  project_name: string | null
}

export type EquipmentStatus = 'available' | 'in_use' | 'maintenance' | 'out_of_service'

export interface EquipmentItem {
  id: number
  name: string
  description: string | null
  equipment_type: string
  model: string | null
  serial_number: string | null
  owned: boolean
  rental_company: string | null
  daily_rate: number
  status: EquipmentStatus
  next_maintenance_date: string | null
  location: string | null
  project_id: number | null
  project_name: string | null
}

export type BomStatus = 'available' | 'ordered' | 'delivered' | 'used'

// A row of the bill of materials (backend `materials` table).
export interface BomItem {
  id: number
  project_id: number
  name: string
  description: string | null
  material_type: string | null
  unit: string | null
  unit_cost: number
  quantity_needed: number
  quantity_available: number
  supplier_name: string | null
  supplier_contact: string | null
  status: BomStatus
  total_cost: number
}

export type PunchStatus = 'open' | 'in_progress' | 'ready' | 'closed'

export interface PunchItem {
  id: number
  project_id: number
  number: number
  code: string
  title: string
  description: string | null
  room: string | null
  trade: string
  priority: TaskPriority
  status: PunchStatus
  assignee: string | null
  due_date: string | null
  phase_id: number | null
  phase_name: string | null
  overdue: boolean
  closed_at: string | null
  created_at: string | null
}

export interface PunchSummary {
  total: number
  open: number
  in_progress: number
  ready: number
  closed: number
  overdue: number
  high_priority_open: number
  percent_closed: number | null
  open_by_room: Array<{ room: string; open: number }>
}

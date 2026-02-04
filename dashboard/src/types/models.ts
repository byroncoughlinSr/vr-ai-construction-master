// Project Management Types
export interface Project {
  id: number
  name: string
  description: string
  project_type: 'house' | 'building' | 'dog_house' | 'garage' | 'addition'
  location: string
  address: string
  lot_size: number
  climate_zone: string
  total_square_footage: number
  number_of_floors: number
  building_height: number
  target_budget: number
  target_completion_days: number
  status: 'draft' | 'planning' | 'in_progress' | 'completed' | 'on_hold'
  progress_percentage: number
  created_at: string
  updated_at: string
  started_at?: string
  completed_at?: string
  metadata?: Record<string, any>
}

export interface ProjectSummary extends Project {
  total_spent: number
  spent_percentage: number
  material_count: number
  task_count: number
  completed_tasks: number
}

// Material Management Types
export interface Material {
  id: number
  name: string
  description?: string
  category: string
  unit: string
  unit_cost: number
  supplier?: string
  sku?: string
  specifications?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface ProjectMaterial {
  id: number
  project_id: number
  material_id: number
  quantity_required: number
  quantity_with_waste: number
  unit_cost: number
  total_cost: number
  status: 'planned' | 'ordered' | 'delivered' | 'in_use' | 'depleted'
  supplier?: string
  order_date?: string
  delivery_date?: string
  notes?: string
  material?: Material
  created_at: string
  updated_at: string
}

// Construction Phase Types
export interface ConstructionPhase {
  id: number
  project_id: number
  name: string
  description?: string
  phase_order: number
  estimated_duration_days: number
  actual_duration_days?: number
  status: 'pending' | 'in_progress' | 'completed' | 'delayed'
  progress_percentage: number
  start_date?: string
  end_date?: string
  dependencies?: number[]
  created_at: string
  updated_at: string
}

// Task Management Types
export interface Task {
  id: number
  phase_id: number
  name: string
  description?: string
  estimated_hours: number
  actual_hours?: number
  status: 'pending' | 'in_progress' | 'completed' | 'blocked'
  priority: 'low' | 'medium' | 'high' | 'critical'
  assigned_to?: number
  due_date?: string
  completed_at?: string
  created_at: string
  updated_at: string
}

// Budget Management Types
export interface BudgetCategory {
  id: number
  project_id: number
  name: string
  description?: string
  budgeted_amount: number
  spent_amount: number
  category_type: 'material' | 'labor' | 'equipment' | 'permit' | 'contingency' | 'other'
  created_at: string
  updated_at: string
}

export interface BudgetTransaction {
  id: number
  budget_category_id: number
  amount: number
  description: string
  transaction_type: 'income' | 'expense'
  transaction_date: string
  reference_number?: string
  vendor?: string
  created_at: string
  updated_at: string
}

// Compliance and Documentation Types
export interface ComplianceRequirement {
  id: number
  project_id: number
  requirement_type: string
  description: string
  jurisdiction: string
  status: 'pending' | 'submitted' | 'approved' | 'rejected'
  submission_date?: string
  approval_date?: string
  expiry_date?: string
  document_url?: string
  notes?: string
  created_at: string
  updated_at: string
}

export interface Document {
  id: number
  project_id: number
  name: string
  document_type: 'permit' | 'contract' | 'drawing' | 'photo' | 'report' | 'other'
  file_path: string
  file_size: number
  mime_type: string
  uploaded_by: number
  version: number
  is_latest: boolean
  created_at: string
  updated_at: string
}

// Resource Management Types
export interface Resource {
  id: number
  name: string
  resource_type: 'labor' | 'equipment' | 'material'
  description?: string
  unit_cost?: number
  availability_status: 'available' | 'in_use' | 'maintenance' | 'unavailable'
  location?: string
  specifications?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface ResourceAllocation {
  id: number
  resource_id: number
  project_id: number
  task_id?: number
  allocated_quantity: number
  start_date: string
  end_date?: string
  status: 'active' | 'completed' | 'cancelled'
  notes?: string
  created_at: string
  updated_at: string
}

// User and Authentication Types
export interface User {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  role: 'admin' | 'manager' | 'worker' | 'client'
  permissions: string[]
  is_active: boolean
  last_login?: string
  created_at: string
  updated_at: string
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

// WebSocket Message Types
export interface WebSocketMessage {
  type: string
  data: any
  timestamp: string
  user_id?: number
  project_id?: number
}

export interface ProjectUpdateMessage extends WebSocketMessage {
  type: 'project_update'
  data: {
    project_id: number
    field: string
    old_value: any
    new_value: any
  }
}

export interface TaskUpdateMessage extends WebSocketMessage {
  type: 'task_update'
  data: {
    task_id: number
    project_id: number
    action: 'created' | 'updated' | 'deleted'
    task: Task
  }
}

// Chart and Analytics Types
export interface ChartDataPoint {
  label: string
  value: number
  color?: string
  metadata?: Record<string, any>
}

export interface TimeSeriesData {
  date: string
  value: number
  category?: string
  metadata?: Record<string, any>
}

// API Response Types
export interface ApiResponse<T> {
  data: T
  status: number
  message?: string
  errors?: string[]
}

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// Form and Validation Types
export interface ValidationError {
  field: string
  message: string
  code?: string
}

export interface FormState<T> {
  data: T
  errors: Record<string, string>
  loading: boolean
  dirty: boolean
  valid: boolean
}

// Filter and Search Types
export interface FilterOptions {
  search?: string
  status?: string[]
  category?: string[]
  date_range?: {
    start: string
    end: string
  }
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export interface SearchResult<T> {
  items: T[]
  total: number
  query: string
  filters: FilterOptions
}

// Export and Report Types
export interface ExportOptions {
  format: 'pdf' | 'excel' | 'csv' | 'json'
  include_images: boolean
  date_range?: {
    start: string
    end: string
  }
  filters?: FilterOptions
}

export interface ReportData {
  title: string
  generated_at: string
  project_id?: number
  data: any
  charts?: ChartDataPoint[]
  summary: Record<string, any>
}

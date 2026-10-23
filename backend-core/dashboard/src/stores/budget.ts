import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type { BudgetSummary, ChangeOrder, ChangeOrderStatus, Expense, ExpenseCategory } from 'src/types/controls'

export interface ExpenseFields {
  vendor: string
  amount: number
  category: ExpenseCategory
  description?: string | null
  status: 'pending' | 'paid'
  incurred_on?: string | null
  invoice_number?: string | null
  phase_id?: number | null
}

export interface ChangeOrderFields {
  title: string
  description?: string | null
  cost_impact: number
  schedule_impact_days: number
  status?: ChangeOrderStatus
  requested_by?: string | null
  floor_plan_version?: number | null
}

/** The selected project's earned value, expenses and change orders. */
export const useBudgetStore = defineStore('budget', {
  state: () => ({
    projectId: null as number | null,
    summary: null as BudgetSummary | null,
    expenses: [] as Expense[],
    changeOrders: [] as ChangeOrder[],
    loading: false,
    error: null as string | null
  }),

  getters: {
    pendingChangeOrders: (state): ChangeOrder[] => state.changeOrders.filter(co => co.status === 'submitted')
  },

  actions: {
    clear() {
      this.projectId = null
      this.summary = null
      this.expenses = []
      this.changeOrders = []
    },

    async load(projectId: number) {
      this.projectId = projectId
      this.loading = true
      this.error = null
      try {
        const [summary, expenses, changeOrders] = await Promise.all([
          apiClient.get<BudgetSummary>(`/projects/${projectId}/budget`),
          apiClient.get<{ expenses: Expense[] }>(`/projects/${projectId}/expenses`),
          apiClient.get<{ change_orders: ChangeOrder[] }>(`/projects/${projectId}/change-orders`)
        ])
        if (this.projectId !== projectId) return
        this.summary = summary
        this.expenses = expenses.expenses
        this.changeOrders = changeOrders.change_orders
      } catch (err) {
        this.error = (err as Error).message
        throw err
      } finally {
        this.loading = false
      }
    },

    async reload() {
      if (this.projectId) await this.load(this.projectId)
    },

    async addExpense(fields: ExpenseFields) {
      if (!this.projectId) return
      await apiClient.post(`/projects/${this.projectId}/expenses`, fields)
      await this.reload()
    },

    async deleteExpense(expenseId: number) {
      if (!this.projectId) return
      await apiClient.delete(`/projects/${this.projectId}/expenses/${expenseId}`)
      await this.reload()
    },

    /** On the loaded project, or on `forProject` (the copilot, from any page). */
    async addChangeOrder(fields: ChangeOrderFields, forProject?: number | null): Promise<ChangeOrder | undefined> {
      const projectId = forProject ?? this.projectId
      if (!projectId) return
      const co = await apiClient.post<ChangeOrder>(`/projects/${projectId}/change-orders`, fields)
      if (projectId === this.projectId) await this.reload()
      return co
    },

    async updateChangeOrder(coId: number, fields: Partial<ChangeOrderFields>) {
      if (!this.projectId) return
      await apiClient.patch(`/projects/${this.projectId}/change-orders/${coId}`, fields)
      await this.reload()
    }
  }
})

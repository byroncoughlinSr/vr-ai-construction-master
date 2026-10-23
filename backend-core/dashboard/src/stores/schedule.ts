import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type { Schedule, SchedulePhase, ScheduleTask, TaskPriority, TaskStatus } from 'src/types/controls'

export interface TaskFields {
  name?: string
  description?: string | null
  status?: TaskStatus
  priority?: TaskPriority
  planned_duration_days?: number
  planned_start_date?: string | null
  planned_end_date?: string | null
  budgeted_cost?: number
  actual_cost?: number
  requires_inspection?: boolean
}

/** The selected project's phases and tasks (GET /projects/{id}/schedule).
 * Progress is earned on the backend; after a change the store reloads the
 * schedule so the summary figures stay right. */
export const useScheduleStore = defineStore('schedule', {
  state: () => ({
    projectId: null as number | null,
    schedule: null as Schedule | null,
    loading: false,
    error: null as string | null
  }),

  getters: {
    phases: (state): SchedulePhase[] => state.schedule?.phases ?? [],
    tasks: (state): Array<ScheduleTask & { phase_name: string }> =>
      (state.schedule?.phases ?? []).flatMap(p => p.tasks.map(t => ({ ...t, phase_name: p.name }))),
    openTasks(): Array<ScheduleTask & { phase_name: string }> {
      return this.tasks.filter(t => t.status !== 'completed')
    }
  },

  actions: {
    clear() {
      this.projectId = null
      this.schedule = null
    },

    async load(projectId: number) {
      this.projectId = projectId
      this.loading = true
      this.error = null
      try {
        const schedule = await apiClient.get<Schedule>(`/projects/${projectId}/schedule`)
        if (this.projectId === projectId) this.schedule = schedule
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

    async baseline(startDate: string) {
      if (!this.projectId) return
      this.schedule = await apiClient.post<Schedule>(`/projects/${this.projectId}/schedule/baseline`, {
        start_date: startDate
      })
    },

    async addPhase(name: string, budgetedCost = 0) {
      if (!this.projectId) return
      await apiClient.post(`/projects/${this.projectId}/phases`, { name, budgeted_cost: budgetedCost })
      await this.reload()
    },

    async updatePhase(phaseId: number, fields: Partial<{ name: string; budgeted_cost: number; planned_start_date: string; planned_end_date: string }>) {
      if (!this.projectId) return
      await apiClient.patch(`/projects/${this.projectId}/phases/${phaseId}`, fields)
      await this.reload()
    },

    async addTask(phaseId: number, fields: TaskFields & { name: string }) {
      if (!this.projectId) return
      const task = await apiClient.post<ScheduleTask>(`/projects/${this.projectId}/phases/${phaseId}/tasks`, fields)
      await this.reload()
      return task
    },

    async updateTask(taskId: number, fields: TaskFields) {
      if (!this.projectId) return
      await apiClient.patch(`/projects/${this.projectId}/tasks/${taskId}`, fields)
      await this.reload()
    },

    async deleteTask(taskId: number) {
      if (!this.projectId) return
      await apiClient.delete(`/projects/${this.projectId}/tasks/${taskId}`)
      await this.reload()
    }
  }
})

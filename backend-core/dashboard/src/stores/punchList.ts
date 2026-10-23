import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type { PunchItem, PunchStatus, PunchSummary, TaskPriority } from 'src/types/controls'

export interface PunchItemFields {
  title: string
  description?: string | null
  room?: string | null
  trade?: string
  priority?: TaskPriority
  status?: PunchStatus
  assignee?: string | null
  due_date?: string | null
  phase_id?: number | null
}

/** "active" = everything not closed (the default view); otherwise one status or all. */
export type PunchStatusFilter = 'active' | 'all' | PunchStatus

/** The selected project's punch list, with the page's filters. */
export const usePunchListStore = defineStore('punchList', {
  state: () => ({
    projectId: null as number | null,
    summary: null as PunchSummary | null,
    items: [] as PunchItem[],
    rooms: [] as string[],
    trades: [] as string[],
    filterStatus: 'active' as PunchStatusFilter,
    filterRoom: null as string | null,
    filterTrade: null as string | null,
    searchQuery: '',
    loading: false,
    error: null as string | null
  }),

  getters: {
    filteredItems(state): PunchItem[] {
      const q = state.searchQuery.trim().toLowerCase()
      return state.items.filter(i =>
        (state.filterStatus === 'all' ||
          (state.filterStatus === 'active' ? i.status !== 'closed' : i.status === state.filterStatus)) &&
        (!state.filterRoom || (i.room ?? 'Unassigned') === state.filterRoom) &&
        (!state.filterTrade || i.trade === state.filterTrade) &&
        (!q || [i.code, i.title, i.description, i.assignee, i.room].some(v => v?.toLowerCase().includes(q)))
      )
    },

    /** Floor plan rooms plus any other location already used on an item. */
    roomOptions(state): string[] {
      const extra = state.items.map(i => i.room).filter((r): r is string => !!r && !state.rooms.includes(r))
      return [...state.rooms, ...new Set(extra)]
    }
  },

  actions: {
    clear() {
      this.projectId = null
      this.summary = null
      this.items = []
      this.rooms = []
      this.filterRoom = null
    },

    async load(projectId: number) {
      if (this.projectId !== projectId) this.filterRoom = null
      this.projectId = projectId
      this.loading = true
      this.error = null
      try {
        const data = await apiClient.get<{ summary: PunchSummary; items: PunchItem[]; rooms: string[]; trades: string[] }>(
          `/projects/${projectId}/punch-list`
        )
        if (this.projectId !== projectId) return
        this.summary = data.summary
        this.items = data.items
        this.rooms = data.rooms
        this.trades = data.trades
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

    async save(fields: Partial<PunchItemFields>, itemId?: number) {
      if (!this.projectId) return
      if (itemId) await apiClient.patch(`/projects/${this.projectId}/punch-items/${itemId}`, fields)
      else await apiClient.post(`/projects/${this.projectId}/punch-items`, fields)
      await this.reload()
    },

    async setStatus(itemId: number, status: PunchStatus) {
      await this.save({ status }, itemId)
    },

    async remove(itemId: number) {
      if (!this.projectId) return
      await apiClient.delete(`/projects/${this.projectId}/punch-items/${itemId}`)
      await this.reload()
    }
  }
})

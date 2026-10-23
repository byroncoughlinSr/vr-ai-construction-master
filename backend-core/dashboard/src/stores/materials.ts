import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type { BomItem, BomStatus } from 'src/types/controls'

type BackendMaterial = Omit<BomItem, 'total_cost'>

export type BomFields = Partial<Omit<BomItem, 'id' | 'project_id' | 'total_cost'>>

const withTotal = (m: BackendMaterial): BomItem => ({
  ...m,
  total_cost: (m.quantity_needed || 0) * (m.unit_cost || 0)
})

/** The selected project's bill of materials (backend `materials`, first
 * written by the AI plan). */
export const useMaterialsStore = defineStore('materials', {
  state: () => ({
    projectId: null as number | null,
    items: [] as BomItem[],
    loading: false,
    error: null as string | null
  }),

  getters: {
    totalCost: (state): number => state.items.reduce((sum, m) => sum + m.total_cost, 0),
    countByStatus: state => (status: BomStatus) => state.items.filter(m => m.status === status).length,
    /** Items with less on hand than needed, that aren't on order. */
    shortages: (state): BomItem[] =>
      state.items.filter(m => m.status === 'available' && m.quantity_available < m.quantity_needed),
    topByCost: state => (limit = 5): BomItem[] =>
      [...state.items].sort((a, b) => b.total_cost - a.total_cost).slice(0, limit)
  },

  actions: {
    clear() {
      this.projectId = null
      this.items = []
    },

    async load(projectId: number) {
      this.projectId = projectId
      this.loading = true
      this.error = null
      try {
        // The list is paged at 100; a house's plan has far fewer lines.
        const response = await apiClient.get<{ materials: BackendMaterial[] }>('/materials/', {
          project_id: projectId,
          page_size: 100
        })
        if (this.projectId === projectId) this.items = (response.materials ?? []).map(withTotal)
      } catch (err) {
        this.error = (err as Error).message
        throw err
      } finally {
        this.loading = false
      }
    },

    async add(fields: BomFields & { name: string; unit: string; unit_cost: number }) {
      if (!this.projectId) return
      const created = await apiClient.post<BackendMaterial>('/materials/', { ...fields, project_id: this.projectId })
      this.items.push(withTotal(created))
    },

    async update(materialId: number, fields: BomFields) {
      const updated = await apiClient.put<BackendMaterial>(`/materials/${materialId}`, fields)
      const index = this.items.findIndex(m => m.id === materialId)
      if (index !== -1) this.items[index] = withTotal(updated)
    },

    async remove(materialId: number) {
      await apiClient.delete(`/materials/${materialId}`)
      this.items = this.items.filter(m => m.id !== materialId)
    }
  }
})

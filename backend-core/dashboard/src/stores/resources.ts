import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type { CrewMember, EquipmentItem, EquipmentStatus } from 'src/types/controls'

export type CrewFields = Partial<Omit<CrewMember, 'id' | 'project_name'>>

export interface EquipmentFields {
  name?: string
  equipment_type?: string
  description?: string | null
  model?: string | null
  serial_number?: string | null
  owned?: boolean
  rental_company?: string | null
  daily_rate?: number
  status?: EquipmentStatus
  next_maintenance_date?: string | null
  location?: string | null
  project_id?: number | null
}

/** Crew and equipment are shared by all projects (each is on at most one), so
 * the store holds them all and pages filter by project. */
export const useResourcesStore = defineStore('resources', {
  state: () => ({
    crew: [] as CrewMember[],
    equipment: [] as EquipmentItem[],
    loading: false,
    loaded: false,
    error: null as string | null
  }),

  getters: {
    crewOn: state => (projectId: number | null) => state.crew.filter(m => m.project_id === projectId),
    equipmentOn: state => (projectId: number | null) => state.equipment.filter(e => e.project_id === projectId),
    /** Labor cost of a day (8 h) for the crew on a project. */
    dailyLaborCost: state => (projectId: number | null) =>
      state.crew.filter(m => m.project_id === projectId).reduce((sum, m) => sum + m.hourly_rate * 8, 0)
  },

  actions: {
    async load() {
      this.loading = true
      this.error = null
      try {
        const [crew, equipment] = await Promise.all([
          apiClient.get<{ crew: CrewMember[] }>('/resources/crew'),
          apiClient.get<{ equipment: EquipmentItem[] }>('/resources/equipment')
        ])
        this.crew = crew.crew
        this.equipment = equipment.equipment
        this.loaded = true
      } catch (err) {
        this.error = (err as Error).message
        throw err
      } finally {
        this.loading = false
      }
    },

    async saveCrew(fields: CrewFields, memberId?: number) {
      const saved = memberId
        ? await apiClient.patch<CrewMember>(`/resources/crew/${memberId}`, fields)
        : await apiClient.post<CrewMember>('/resources/crew', fields)
      const index = this.crew.findIndex(m => m.id === saved.id)
      if (index === -1) this.crew.push(saved)
      else this.crew[index] = saved
      return saved
    },

    async deleteCrew(memberId: number) {
      await apiClient.delete(`/resources/crew/${memberId}`)
      this.crew = this.crew.filter(m => m.id !== memberId)
    },

    async saveEquipment(fields: EquipmentFields, itemId?: number) {
      const saved = itemId
        ? await apiClient.patch<EquipmentItem>(`/resources/equipment/${itemId}`, fields)
        : await apiClient.post<EquipmentItem>('/resources/equipment', fields)
      const index = this.equipment.findIndex(e => e.id === saved.id)
      if (index === -1) this.equipment.push(saved)
      else this.equipment[index] = saved
      return saved
    },

    async deleteEquipment(itemId: number) {
      await apiClient.delete(`/resources/equipment/${itemId}`)
      this.equipment = this.equipment.filter(e => e.id !== itemId)
    }
  }
})

import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type { ProjectMaterial } from 'src/types/models'

interface MaterialsState {
  projectMaterials: ProjectMaterial[]
  loading: boolean
  error: string | null
  filters: {
    category: string | null
    status: string | null
    search: string
  }
}

export const useMaterialsStore = defineStore('materials', {
  state: (): MaterialsState => ({
    projectMaterials: [],
    loading: false,
    error: null,
    filters: {
      category: null,
      status: null,
      search: ''
    }
  }),

  getters: {
    filteredMaterials: (state): ProjectMaterial[] => {
      let result = state.projectMaterials

      if (state.filters.search) {
        const search = state.filters.search.toLowerCase()
        result = result.filter(pm =>
          pm.material?.name.toLowerCase().includes(search) ||
          pm.material?.category.toLowerCase().includes(search) ||
          pm.supplier?.toLowerCase().includes(search)
        )
      }

      if (state.filters.category) {
        result = result.filter(pm =>
          pm.material?.category === state.filters.category
        )
      }

      if (state.filters.status) {
        result = result.filter(pm => pm.status === state.filters.status)
      }

      return result
    },

    totalCost: (state): number => {
      return state.projectMaterials.reduce((sum, pm) => sum + (pm.total_cost || 0), 0)
    },

    materialsByCategory: (state): Record<string, ProjectMaterial[]> => {
      return state.projectMaterials.reduce((acc, material) => {
        const category = material.material?.category || 'Uncategorized'
        if (!acc[category]) {
          acc[category] = []
        }
        acc[category].push(material)
        return acc
      }, {} as Record<string, ProjectMaterial[]>)
    },

    materialsByStatus: (state): Record<string, ProjectMaterial[]> => {
      return state.projectMaterials.reduce((acc, material) => {
        const status = material.status
        if (!acc[status]) {
          acc[status] = []
        }
        acc[status].push(material)
        return acc
      }, {} as Record<string, ProjectMaterial[]>)
    },

    topMaterialsByCost: (state) => {
      return (limit = 5): ProjectMaterial[] => {
        return [...state.projectMaterials]
          .sort((a, b) => (b.total_cost || 0) - (a.total_cost || 0))
          .slice(0, limit)
      }
    },

    lowStockMaterials: (state): ProjectMaterial[] => {
      return state.projectMaterials.filter(pm =>
        pm.status === 'in_use' &&
        pm.quantity_with_waste <= (pm.quantity_required * 0.1) // Less than 10% remaining
      )
    },

    orderedMaterials: (state): ProjectMaterial[] => {
      return state.projectMaterials.filter(pm => pm.status === 'ordered')
    },

    deliveredMaterials: (state): ProjectMaterial[] => {
      return state.projectMaterials.filter(pm => pm.status === 'delivered')
    }
  },

  actions: {
    async fetchProjectMaterials(projectId: number): Promise<ProjectMaterial[]> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.get<{ materials: ProjectMaterial[] } | ProjectMaterial[]>(
          `/projects/${projectId}/materials`
        )
        this.projectMaterials = Array.isArray(response)
          ? response
          : response.materials
        return this.projectMaterials
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error fetching project materials:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async addMaterial(projectId: number, materialData: Partial<ProjectMaterial>): Promise<ProjectMaterial> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.post<ProjectMaterial>(
          `/projects/${projectId}/materials`,
          materialData
        )
        this.projectMaterials.push(response)
        return response
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error adding material:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateMaterial(materialId: number, materialData: Partial<ProjectMaterial>): Promise<ProjectMaterial> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.put<ProjectMaterial>(
          `/project-materials/${materialId}`,
          materialData
        )

        const index = this.projectMaterials.findIndex(m => m.id === materialId)
        if (index !== -1) {
          this.projectMaterials[index] = response
        }

        return response
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error updating material:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteMaterial(materialId: number): Promise<void> {
      this.loading = true
      this.error = null
      try {
        await apiClient.delete(`/project-materials/${materialId}`)
        this.projectMaterials = this.projectMaterials.filter(m => m.id !== materialId)
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error deleting material:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateMaterialStatus(materialId: number, status: ProjectMaterial['status']): Promise<ProjectMaterial> {
      return this.updateMaterial(materialId, { status })
    },

    async bulkUpdateStatus(materialIds: number[], status: ProjectMaterial['status']): Promise<ProjectMaterial[]> {
      this.loading = true
      this.error = null
      try {
        const promises = materialIds.map(id =>
          apiClient.put<ProjectMaterial>(`/project-materials/${id}`, { status })
        )
        const responses = await Promise.all(promises)

        // Update local state
        responses.forEach(response => {
          const index = this.projectMaterials.findIndex(m => m.id === response.id)
          if (index !== -1) {
            this.projectMaterials[index] = response
          }
        })

        return responses
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error bulk updating materials:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    setFilters(filters: Partial<MaterialsState['filters']>): void {
      this.filters = { ...this.filters, ...filters }
    },

    clearFilters(): void {
      this.filters = {
        category: null,
        status: null,
        search: ''
      }
    },

    clearError(): void {
      this.error = null
    }
  }
})

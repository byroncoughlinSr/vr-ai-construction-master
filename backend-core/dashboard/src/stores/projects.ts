import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type { Project, ProjectSummary } from 'src/types/models'

// Shape returned by the backend /api/v1/projects/ endpoint
interface BackendProject {
  id: number
  name: string
  description: string
  status: string
  budget: number | null
  estimated_cost: number
  actual_cost: number | null
  address: string | null
  latitude: number | null
  longitude: number | null
  start_date: string | null
  end_date: string | null
  estimated_completion_date: string | null
  created_at: string
  updated_at: string | null
}

interface BackendProjectListResponse {
  projects: BackendProject[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/** Map backend field names to the frontend Project model. */
function mapProject(p: BackendProject): Project {
  return {
    id: p.id,
    name: p.name,
    description: p.description ?? '',
    project_type: 'house',
    location: p.address ?? '',
    address: p.address ?? '',
    lot_size: 0,
    climate_zone: '',
    total_square_footage: 0,
    number_of_floors: 1,
    building_height: 0,
    target_budget: p.budget ?? p.estimated_cost ?? 0,
    target_completion_days: 0,
    status: (p.status as Project['status']) ?? 'planning',
    progress_percentage: 0,
    created_at: p.created_at,
    updated_at: p.updated_at ?? p.created_at,
    started_at: p.start_date ?? undefined,
    completed_at: p.end_date ?? undefined
  }
}

interface ProjectsState {
  projects: Project[]
  currentProject: ProjectSummary | null
  loading: boolean
  error: string | null
}

export const useProjectsStore = defineStore('projects', {
  state: (): ProjectsState => ({
    projects: [],
    currentProject: null,
    loading: false,
    error: null
  }),

  getters: {
    getProjectById: (state): ((id: number) => Project | undefined) => {
      return (id: number): Project | undefined => {
        return state.projects.find(project => project.id === id)
      }
    },

    activeProjects: (state): Project[] => {
      return state.projects.filter(p => p.status !== 'completed')
    },

    totalBudget: (state): number => {
      return state.projects.reduce((sum, p) => sum + (p.target_budget || 0), 0)
    },

    projectsByType: (state): Record<string, Project[]> => {
      return state.projects.reduce((acc, project) => {
        const type = project.project_type
        if (!acc[type]) {
          acc[type] = []
        }
        acc[type].push(project)
        return acc
      }, {} as Record<string, Project[]>)
    },

    overdueProjects: (state): Project[] => {
      const now = new Date()
      return state.projects.filter(p =>
        p.target_completion_days &&
        p.started_at &&
        new Date(p.started_at).getTime() + (p.target_completion_days * 24 * 60 * 60 * 1000) < now.getTime() &&
        p.status !== 'completed'
      )
    }
  },

  actions: {
    async fetchProjects(): Promise<Project[]> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.get<BackendProjectListResponse>('/projects/')
        const mapped = (response.projects ?? []).map(mapProject)
        this.projects = mapped
        // Auto-select the first project if none is currently selected
        if (!this.currentProject && mapped.length > 0) {
          this.currentProject = mapped[0] as ProjectSummary
        }
        return mapped
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error fetching projects:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchProjectSummary(projectId: number): Promise<ProjectSummary> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.get<BackendProject>(`/projects/${projectId}`)
        const mapped: ProjectSummary = {
          ...mapProject(response),
          total_spent: 0,
          spent_percentage: 0,
          material_count: 0,
          task_count: 0,
          completed_tasks: 0
        }
        this.currentProject = mapped
        return mapped
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error fetching project summary:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async createProject(projectData: Partial<Project>): Promise<Project> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.post<Project>('/projects', projectData)
        this.projects.push(response)
        return response
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error creating project:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateProject(projectId: number, projectData: Partial<Project>): Promise<Project> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.put<Project>(`/projects/${projectId}`, projectData)

        const index = this.projects.findIndex(p => p.id === projectId)
        if (index !== -1) {
          this.projects[index] = response
        }

        if (this.currentProject?.id === projectId) {
          this.currentProject = response as ProjectSummary
        }

        return response
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error updating project:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteProject(projectId: number): Promise<void> {
      this.loading = true
      this.error = null
      try {
        await apiClient.delete(`/projects/${projectId}`)
        this.projects = this.projects.filter(p => p.id !== projectId)

        if (this.currentProject?.id === projectId) {
          this.currentProject = null
        }
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error deleting project:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async duplicateProject(projectId: number, newName?: string): Promise<Project> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.post<Project>(`/projects/${projectId}/duplicate`, {
          name: newName
        })
        this.projects.push(response)
        return response
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error duplicating project:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    setCurrentProject(project: ProjectSummary | null): void {
      this.currentProject = project
    },

    clearError(): void {
      this.error = null
    },

    // Bulk operations
    async updateProjectStatus(projectId: number, status: Project['status']): Promise<Project> {
      return this.updateProject(projectId, { status })
    },

    async updateProjectProgress(projectId: number, progress: number): Promise<Project> {
      return this.updateProject(projectId, { progress_percentage: progress })
    }
  }
})

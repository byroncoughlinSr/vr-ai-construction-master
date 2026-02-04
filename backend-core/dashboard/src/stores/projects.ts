import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type { Project, ProjectSummary } from 'src/types/models'

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
        const response = await apiClient.get<Project[]>('/projects')
        this.projects = response
        return response
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
        const response = await apiClient.get<ProjectSummary>(`/projects/${projectId}/summary`)
        this.currentProject = response
        return response
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

import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type { Project } from 'src/types/models'
import type { ProjectOverview } from 'src/types/controls'

// Shape returned by the backend /api/v1/projects/ endpoint
export interface BackendProject {
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

// The editable fields, as the backend names them (ProjectCreate / ProjectUpdate).
export interface ProjectFields {
  name?: string
  description?: string | null
  status?: string
  budget?: number | null
  address?: string | null
  start_date?: string | null
  estimated_completion_date?: string | null
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

// Which project was selected last, so a reload comes back to it (per browser).
const SELECTED_KEY = 'dashboard.selectedProjectId'

function rememberedProjectId(): number | null {
  try {
    const value = Number(localStorage.getItem(SELECTED_KEY))
    return Number.isFinite(value) && value > 0 ? value : null
  } catch {
    return null
  }
}

function rememberProjectId(id: number | null): void {
  try {
    if (id) localStorage.setItem(SELECTED_KEY, String(id))
    else localStorage.removeItem(SELECTED_KEY)
  } catch {
    // Storage may be unavailable (private window, headset WebView); not needed.
  }
}

interface ProjectsState {
  projects: Project[]
  raw: Record<number, BackendProject>
  currentProject: Project | null
  overview: ProjectOverview | null
  overviewLoading: boolean
  loading: boolean
  loaded: boolean
  error: string | null
}

export const useProjectsStore = defineStore('projects', {
  state: (): ProjectsState => ({
    projects: [],
    raw: {},
    currentProject: null,
    overview: null,
    overviewLoading: false,
    loading: false,
    loaded: false,
    error: null
  }),

  getters: {
    currentProjectId: (state): number | null => state.currentProject?.id ?? null,

    /** The selected project with the backend's own fields (dates, cost). */
    currentRaw: (state): BackendProject | null =>
      state.currentProject ? state.raw[state.currentProject.id] ?? null : null,

    getProjectById: (state): ((id: number) => Project | undefined) => {
      return (id: number): Project | undefined => state.projects.find(project => project.id === id)
    },

    activeProjects: (state): Project[] => state.projects.filter(p => p.status !== 'completed')
  },

  actions: {
    _store(p: BackendProject): Project {
      this.raw[p.id] = p
      const mapped = mapProject(p)
      const index = this.projects.findIndex(x => x.id === p.id)
      if (index === -1) this.projects.unshift(mapped)
      else this.projects[index] = mapped
      if (this.currentProject?.id === p.id) this.currentProject = mapped
      return mapped
    },

    async fetchProjects(): Promise<Project[]> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.get<BackendProjectListResponse>('/projects/', { page_size: 100 })
        const list = response.projects ?? []
        this.raw = Object.fromEntries(list.map(p => [p.id, p]))
        this.projects = list.map(mapProject)
        // Keep the selection if it still exists, else the one picked last, else the newest.
        const keep = this.currentProject && this.projects.find(p => p.id === this.currentProject?.id)
        const remembered = rememberedProjectId()
        this.currentProject =
          keep ?? this.projects.find(p => p.id === remembered) ?? this.projects[0] ?? null
        this.loaded = true
        return this.projects
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error fetching projects:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    selectProject(projectId: number | null): void {
      this.currentProject = projectId ? this.projects.find(p => p.id === projectId) ?? null : null
      this.overview = null
      rememberProjectId(this.currentProject?.id ?? null)
    },

    async fetchOverview(forProject?: number | null): Promise<ProjectOverview | null> {
      const projectId = forProject ?? this.currentProjectId
      if (!projectId) return null
      this.overviewLoading = true
      try {
        const overview = await apiClient.get<ProjectOverview>(`/projects/${projectId}/overview`)
        // Ignore an answer for a project that is no longer selected.
        if (projectId === this.currentProjectId) this.overview = overview
        return overview
      } finally {
        this.overviewLoading = false
      }
    },

    async createProject(fields: ProjectFields): Promise<Project> {
      const created = await apiClient.post<BackendProject>('/projects/', { status: 'planning', ...fields })
      const project = this._store(created)
      this.selectProject(project.id)
      return project
    },

    /** Generate a whole project (plan, phases, tasks, materials, floor plan v1)
     * from a description with the AI planner, then select it. Takes a minute or two. */
    async generateProject(prompt: string, budget?: number | null): Promise<Project> {
      const result = await apiClient.post<{ project_id: number }>('/planning/generate-project', {
        prompt,
        budget: budget || null,
        generate_image: false
      })
      const created = await apiClient.get<BackendProject>(`/projects/${result.project_id}`)
      const project = this._store(created)
      this.selectProject(project.id)
      return project
    },

    async updateProject(projectId: number, fields: ProjectFields): Promise<Project> {
      const updated = await apiClient.put<BackendProject>(`/projects/${projectId}`, fields)
      return this._store(updated)
    },

    async deleteProject(projectId: number): Promise<void> {
      await apiClient.delete(`/projects/${projectId}`)
      this.projects = this.projects.filter(p => p.id !== projectId)
      delete this.raw[projectId]
      if (this.currentProject?.id === projectId) this.selectProject(this.projects[0]?.id ?? null)
    },

    /** The floor plan renames the house; keep the list and header in step. */
    renameLocally(projectId: number, name: string): void {
      const raw = this.raw[projectId]
      if (raw) this._store({ ...raw, name })
    }
  }
})

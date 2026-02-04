# Vue 3 + Quasar Dashboard - Complete Plan with TypeScript + Script Setup

## 🎯 **Overview**

This comprehensive plan creates a **production-ready Vue 3 + Quasar dashboard** using **TypeScript + Script Setup syntax**, with complete backend integration for the VR Construction Platform. It combines the best of modern Vue 3 development with Quasar's Material Design components and robust state management.

---

## **📋 Implementation Roadmap**

### **Phase 1: Project Setup & Core Architecture (Week 1)**

#### **1.1 Initialize Quasar TypeScript Project**
```bash
# Create Quasar project with TypeScript
cd ~/vr-construction-platform
npm install -g @quasar/cli
npm init quasar dashboard

# Project configuration:
# - Quasar v2 (Vue 3)
# - TypeScript: Yes
# - Features: ESLint, Axios, Pinia
# - CSS preprocessor: Sass/SCSS
# - Package manager: npm

cd dashboard
npm install chart.js vue-chartjs date-fns
npm install -D typescript @types/node vitest @vue/test-utils
```

#### **1.2 TypeScript Configuration**
```typescript
// tsconfig.json
{
  "extends": "@quasar/app-vite/tsconfig-preset",
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "src/*": ["src/*"],
      "components/*": ["src/components/*"],
      "layouts/*": ["src/layouts/*"],
      "pages/*": ["src/pages/*"],
      "stores/*": ["src/stores/*"],
      "types/*": ["src/types/*"],
      "services/*": ["src/services/*"],
      "composables/*": ["src/composables/*"]
    },
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  }
}
```

#### **1.3 Environment Configuration**
```javascript
// quasar.config.js
module.exports = function (ctx) {
  return {
    supportTS: {
      tsCheckerConfig: {
        eslint: {
          enabled: true,
          files: './src/**/*.{ts,tsx,js,jsx,vue}'
        }
      }
    },
    boot: [
      'axios',
      'pinia',
      'websocket',
      'env',
      'error-handler'
    ],
    build: {
      env: {
        API_BASE_URL: ctx.dev
          ? 'http://localhost:8000/api/v1'
          : 'https://api.vrconstruction.com/api/v1',
        WS_URL: ctx.dev
          ? 'ws://localhost:8000/api/v1/ws'
          : 'wss://api.vrconstruction.com/api/v1/ws'
      }
    }
  }
}
```

### **Phase 2: Type Definitions & API Integration (Week 2)**

#### **2.1 Comprehensive Type Definitions**
```typescript
// src/types/models.ts
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

// Material, Phase, Task, Budget types...
```

#### **2.2 API Service Layer**
```typescript
// src/services/api.ts
import { api } from 'boot/axios'

export interface ApiResponse<T> {
  data: T
  status: number
  message?: string
}

export class ApiClient {
  async get<T>(endpoint: string, params?: Record<string, any>): Promise<T> {
    const response = await api.get(endpoint, { params })
    return response.data
  }

  async post<T>(endpoint: string, data: any): Promise<T> {
    const response = await api.post(endpoint, data)
    return response.data
  }

  async put<T>(endpoint: string, data: any): Promise<T> {
    const response = await api.put(endpoint, data)
    return response.data
  }

  async delete<T>(endpoint: string): Promise<T> {
    const response = await api.delete(endpoint)
    return response.data
  }
}

export const apiClient = new ApiClient()
```

#### **2.3 WebSocket Service**
```typescript
// src/services/websocket.ts
export class WebSocketService {
  private ws: WebSocket | null = null
  public connected = ref(false)
  public messages = reactive<WebSocketMessage[]>([])

  constructor(private url: string) {}

  connect(): void {
    try {
      this.ws = new WebSocket(this.url)
      this.ws.onopen = () => {
        this.connected.value = true
      }
      this.ws.onmessage = (event) => {
        const message: WebSocketMessage = JSON.parse(event.data)
        this.handleMessage(message)
      }
      this.ws.onclose = () => {
        this.connected.value = false
        this.attemptReconnect()
      }
    } catch (error) {
      console.error('WebSocket connection failed:', error)
    }
  }

  private handleMessage(message: WebSocketMessage): void {
    this.messages.push(message)
    // Handle different message types
  }

  send(data: any): void {
    if (this.ws && this.connected.value) {
      this.ws.send(JSON.stringify(data))
    }
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close()
    }
  }
}
```

### **Phase 3: State Management with Pinia (Week 3)**

#### **3.1 Projects Store**
```typescript
// src/stores/projects.ts
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
    getProjectById: (state) => {
      return (id: number): Project | undefined => {
        return state.projects.find(project => project.id === id)
      }
    },

    activeProjects: (state): Project[] => {
      return state.projects.filter(p => p.status !== 'completed')
    },

    totalBudget: (state): number => {
      return state.projects.reduce((sum, p) => sum + (p.target_budget || 0), 0)
    }
  },

  actions: {
    async fetchProjects(): Promise<Project[]> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.get<Project[]>('/projects')
        this.projects = response.data
        return response.data
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
        this.currentProject = response.data
        return response.data
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
        this.projects.push(response.data)
        return response.data
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
          this.projects[index] = response.data
        }

        if (this.currentProject?.id === projectId) {
          this.currentProject = response.data as ProjectSummary
        }

        return response.data
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error updating project:', error)
        throw error
      } finally {
        this.loading = false
      }
    }
  }
})
```

#### **3.2 Materials Store**
```typescript
// src/stores/materials.ts
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
          pm.material?.name.toLowerCase().includes(search)
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

    topMaterialsByCost: (state) => {
      return (limit = 5): ProjectMaterial[] => {
        return [...state.projectMaterials]
          .sort((a, b) => (b.total_cost || 0) - (a.total_cost || 0))
          .slice(0, limit)
      }
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
        this.projectMaterials = Array.isArray(response.data)
          ? response.data
          : response.data.materials
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
        this.projectMaterials.push(response.data)
        return response.data
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
          this.projectMaterials[index] = response.data
        }

        return response.data
      } catch (error) {
        this.error = (error as Error).message
        console.error('Error updating material:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    setFilters(filters: Partial<MaterialsState['filters']>): void {
      this.filters = { ...this.filters, ...filters }
    }
  }
})
```

#### **3.3 Authentication Store**
```typescript
// src/stores/auth.ts
import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'

export interface User {
  id: number
  username: string
  email: string
  role: 'admin' | 'manager' | 'worker'
  permissions: string[]
}

interface AuthState {
  user: User | null
  token: string | null
  loading: boolean
  error: string | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    token: localStorage.getItem('auth_token') || null,
    loading: false,
    error: null
  }),

  getters: {
    isAuthenticated: (state): boolean => !!state.token && !!state.user,
    isAdmin: (state): boolean => state.user?.role === 'admin',
    hasPermission: (state) => (permission: string): boolean =>
      state.user?.permissions?.includes(permission) || false
  },

  actions: {
    async login(credentials: { username: string; password: string }): Promise<{ user: User; token: string }> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.post<{ user: User; token: string }>('/auth/login', credentials)
        this.user = response.data.user
        this.token = response.data.token

        localStorage.setItem('auth_token', this.token)
        api.defaults.headers.common['Authorization'] = `Bearer ${this.token}`

        return response.data
      } catch (error) {
        this.error = (error as Error).message
        throw error
      } finally {
        this.loading = false
      }
    },

    async logout(): Promise<void> {
      try {
        await apiClient.post('/auth/logout', {})
      } catch (error) {
        // Ignore logout errors
      } finally {
        this.user = null
        this.token = null
        localStorage.removeItem('auth_token')
        delete api.defaults.headers.common['Authorization']
      }
    },

    async refreshToken(): Promise<void> {
      try {
        const response = await apiClient.post<{ token: string }>('/auth/refresh', {})
        this.token = response.data.token
        localStorage.setItem('auth_token', this.token)
        api.defaults.headers.common['Authorization'] = `Bearer ${this.token}`
      } catch (error) {
        this.logout()
        throw error
      }
    }
  }
})
```

### **Phase 4: Components with Script Setup (Week 4)**

#### **4.1 Main Layout**
```vue
<template>
  <q-layout view="hHh lpR fFf">
    <!-- Header -->
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <q-toolbar-title>
          <q-icon name="home_work" size="sm" class="q-mr-sm" />
          VR Construction Platform
        </q-toolbar-title>

        <q-space />

        <!-- Project Selector -->
        <q-select
          v-model="selectedProject"
          :options="projects"
          option-value="id"
          option-label="name"
          label="Select Project"
          dark
          outlined
          dense
          style="min-width: 250px"
          class="q-mr-md"
          @update:model-value="onProjectChange"
        />

        <!-- Export Menu -->
        <q-btn-dropdown flat dense label="Export" icon="download">
          <q-list>
            <q-item clickable v-close-popup @click="exportPDF">
              <q-item-section avatar>
                <q-icon name="picture_as_pdf" color="red" />
              </q-item-section>
              <q-item-section>
                <q-item-label>PDF Report</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-btn-dropdown>

        <!-- Settings -->
        <q-btn flat dense round icon="settings" class="q-ml-sm">
          <q-menu>
            <q-list style="min-width: 200px">
              <q-item clickable v-close-popup>
                <q-item-section>Dark Mode</q-item-section>
                <q-item-section side>
                  <q-toggle v-model="darkMode" @update:model-value="toggleDarkMode" />
                </q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
      </q-toolbar>
    </q-header>

    <!-- Left Drawer -->
    <q-drawer
      v-model="leftDrawerOpen"
      show-if-above
      bordered
      :width="250"
    >
      <q-list>
        <q-item-label header>Navigation</q-item-label>

        <q-item clickable to="/" exact>
          <q-item-section avatar>
            <q-icon name="dashboard" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Dashboard</q-item-label>
          </q-item-section>
        </q-item>

        <q-item clickable to="/timeline">
          <q-item-section avatar>
            <q-icon name="event" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Timeline</q-item-label>
          </q-item-section>
        </q-item>

        <q-item clickable to="/materials">
          <q-item-section avatar>
            <q-icon name="inventory" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Materials</q-item-label>
          </q-item-section>
        </q-item>

        <q-item clickable to="/budget">
          <q-item-section avatar>
            <q-icon name="attach_money" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Budget</q-item-label>
          </q-item-section>
        </q-item>
      </q-list>
    </q-drawer>

    <!-- Main Content -->
    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useQuasar } from 'quasar'
import { useProjectsStore } from 'stores/projects'
import { useAuthStore } from 'stores/auth'
import type { Project } from 'src/types/models'

const $q = useQuasar()
const projectsStore = useProjectsStore()
const authStore = useAuthStore()

// State
const leftDrawerOpen = ref(true)
const darkMode = ref($q.dark.isActive)
const selectedProject = ref<Project | null>(null)

// Computed
const projects = computed(() => projectsStore.projects)

// Methods
const loadProjects = async (): Promise<void> => {
  try {
    await projectsStore.fetchProjects()
    if (projects.value.length > 0) {
      selectedProject.value = projects.value[0]
    }
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: 'Failed to load projects'
    })
  }
}

const onProjectChange = async (project: Project): Promise<void> => {
  if (!project) return

  try {
    await projectsStore.fetchProjectSummary(project.id)
    $q.notify({
      type: 'positive',
      message: `Loaded ${project.name}`
    })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: 'Failed to load project'
    })
  }
}

const toggleDarkMode = (value: boolean): void => {
  $q.dark.set(value)
}

const exportPDF = async (): Promise<void> => {
  if (!selectedProject.value) return

  $q.loading.show({ message: 'Generating PDF...' })

  try {
    const response = await fetch(`/api/projects/${selectedProject.value.id}/report/pdf`)
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${selectedProject.value.name}_Report.pdf`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)

    $q.notify({
      type: 'positive',
      message: 'PDF downloaded successfully'
    })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: 'Failed to generate PDF'
    })
  } finally {
    $q.loading.hide()
  }
}

// Lifecycle
onMounted(() => {
  loadProjects()
})
</script>
```

#### **4.2 Dashboard Home Page**
```vue
<template>
  <q-page class="q-pa-md">
    <!-- Loading State -->
    <div v-if="loading" class="flex flex-center q-pa-xl">
      <q-spinner size="50px" color="primary" />
      <p class="q-ml-md">{{ loadingMessage }}</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="q-pa-md">
      <q-banner class="bg-negative text-white">
        <template v-slot:avatar>
          <q-icon name="error" />
        </template>
        {{ error }}
      </q-banner>
    </div>

    <!-- Dashboard Content -->
    <div v-else>
      <!-- Project Header -->
      <div class="row items-center q-mb-md">
        <div class="col">
          <h4 class="q-ma-none">{{ project?.name }}</h4>
          <p class="text-grey-7 q-mb-none">{{ project?.description }}</p>
        </div>
        <div class="col-auto">
          <q-btn
            color="primary"
            label="Refresh"
            icon="refresh"
            @click="refreshData"
          />
        </div>
      </div>

      <!-- Summary Cards -->
      <div class="row q-col-gutter-md q-mb-lg">
        <!-- Budget Card -->
        <div class="col-12 col-md-4">
          <q-card class="bg-gradient-primary text-white">
            <q-card-section>
              <div class="text-h6">Total Budget</div>
              <div class="text-h3 q-mt-sm">
                ${{ formatCurrency(totalBudget) }}
              </div>
              <q-linear-progress
                :value="budgetPercentage / 100"
                color="white"
                track-color="rgba(255,255,255,0.3)"
                size="8px"
                rounded
                class="q-mt-sm"
              />
              <div class="text-caption q-mt-xs">
                Spent: ${{ formatCurrency(totalSpent) }} ({{ budgetPercentage.toFixed(1) }}%)
              </div>
            </q-card-section>
          </q-card>
        </div>

        <!-- Progress Card -->
        <div class="col-12 col-md-4">
          <q-card class="bg-gradient-success text-white">
            <q-card-section>
              <div class="text-h6">Progress</div>
              <div class="text-h3 q-mt-sm">
                {{ overallProgress.toFixed(0) }}%
              </div>
              <q-circular-progress
                :value="overallProgress"
                size="80px"
                :thickness="0.15"
                color="white"
                track-color="rgba(255,255,255,0.3)"
                show-value
                class="q-ma-sm"
              >
                <div class="text-white text-bold">
                  {{ overallProgress.toFixed(0) }}%
                </div>
              </q-circular-progress>
            </q-card-section>
          </q-card>
        </div>

        <!-- Materials Card -->
        <div class="col-12 col-md-4">
          <q-card class="bg-gradient-info text-white">
            <q-card-section>
              <div class="text-h6">Materials Cost</div>
              <div class="text-h3 q-mt-sm">
                ${{ formatCurrency(materialsCost) }}
              </div>
              <div class="text-caption q-mt-sm">
                {{ materialsCount }} materials assigned
              </div>
            </q-card-section>
          </q-card>
        </div>
      </div>

      <!-- Charts Row -->
      <div class="row q-col-gutter-md q-mb-lg">
        <!-- Budget Breakdown -->
        <div class="col-12 col-md-6">
          <q-card>
            <q-card-section>
              <div class="text-h6">Budget Breakdown</div>
            </q-card-section>
            <q-card-section>
              <budget-pie-chart :budget-data="budgetData" />
            </q-card-section>
          </q-card>
        </div>

        <!-- Cost Trend -->
        <div class="col-12 col-md-6">
          <q-card>
            <q-card-section>
              <div class="text-h6">Cost Trend</div>
            </q-card-section>
            <q-card-section>
              <cost-trend-chart :expenses="expenses" />
            </q-card-section>
          </q-card>
        </div>
      </div>

      <!-- Timeline -->
      <q-card class="q-mb-lg">
        <q-card-section>
          <div class="text-h6">Construction Timeline</div>
        </q-card-section>
        <q-card-section>
          <timeline-gantt :phases="sortedPhases" />
        </q-card-section>
      </q-card>

      <!-- Top Materials -->
      <q-card>
        <q-card-section>
          <div class="text-h6">Top Materials by Cost</div>
        </q-card-section>
        <q-card-section>
          <q-list>
            <q-item
              v-for="material in topMaterials"
              :key="material.id"
            >
              <q-item-section>
                <q-item-label>{{ material.material?.name }}</q-item-label>
                <q-item-label caption>
                  {{ material.quantity_with_waste }} {{ material.material?.unit }}
                </q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-item-label>${{ formatCurrency(material.total_cost) }}</q-item-label>
                <q-badge :color="getStatusColor(material.status)">
                  {{ material.status }}
                </q-badge>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
      </q-card>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useQuasar } from 'quasar'
import { useProjectsStore } from 'stores/projects'
import { useMaterialsStore } from 'stores/materials'
import { useBudgetStore } from 'stores/budget'
import { usePhasesStore } from 'stores/phases'
import BudgetPieChart from 'components/BudgetPieChart.vue'
import CostTrendChart from 'components/CostTrendChart.vue'
import TimelineGantt from 'components/TimelineGantt.vue'
import type { ProjectSummary, ConstructionPhase, ProjectMaterial } from 'src/types/models'

const $q = useQuasar()
const projectsStore = useProjectsStore()
const materialsStore = useMaterialsStore()
const budgetStore = useBudgetStore()
const phasesStore = usePhasesStore()

// State
const loading = ref(false)
const error = ref<string | null>(null)
const loadingMessage = ref('Loading project data...')

// Computed
const project = computed<ProjectSummary | null>(() => projectsStore.currentProject)
const sortedPhases = computed<ConstructionPhase[]>(() => phasesStore.sortedPhases)
const topMaterials = computed<ProjectMaterial[]>(() => materialsStore.topMaterialsByCost(5))

const totalBudget = computed<number>(() => {
  if (!project.value) return 0
  return budgetStore.totalBudgeted(project.value.id)
})

const totalSpent = computed<number>(() => {
  if (!project.value) return 0
  return budgetStore.totalSpent(project.value.id)
})

const budgetPercentage = computed<number>(() => {
  if (!project.value) return 0
  return budgetStore.overallPercentageSpent(project.value.id)
})

const overallProgress = computed<number>(() => {
  if (!project.value) return 0
  return phasesStore.overallProgress(project.value.id)
})

const materialsCost = computed<number>(() => materialsStore.totalCost)
const materialsCount = computed<number>(() => materialsStore.projectMaterials.length)

// Methods
const loadData = async (): Promise<void> => {
  loading.value = true
  error.value = null

  try {
    const projectId = 1 // Get from route or context

    await Promise.all([
      projectsStore.fetchProjectSummary(projectId),
      materialsStore.fetchProjectMaterials(projectId),
      budgetStore.fetchBudget(projectId),
      phasesStore.fetchPhases(projectId)
    ])
  } catch (err) {
    error.value = (err as Error).message
    $q.notify({
      type: 'negative',
      message: 'Failed to load project data',
      caption: (err as Error).message
    })
  } finally {
    loading.value = false
  }
}

const refreshData = async (): Promise<void> => {
  await loadData()
  $q.notify({
    type: 'positive',
    message: 'Data refreshed successfully'
  })
}

const formatCurrency = (value: number): string => {
  if (!value && value !== 0) return '0'
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const getStatusColor = (status: ProjectMaterial['status']): string => {
  const colors: Record<ProjectMaterial['status'], string> = {
    planned: 'grey',
    ordered: 'orange',
    delivered: 'blue',
    in_use: 'green',
    depleted: 'grey-5'
  }
  return colors[status]
}

// Lifecycle
onMounted(() => {
  loadData()
})
</script>

<style lang="sass" scoped>
.bg-gradient-primary
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)

.bg-gradient-success
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%)

.bg-gradient-info
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)
</style>
```

### **Phase 5: Advanced Features (Week 5)**

#### **5.1 Reusable Composables**
```typescript
// src/composables/useCurrency.ts
export function useCurrency() {
  const formatCurrency = (value: number, decimals = 0): string => {
    if (!value && value !== 0) return '0'

    return new Intl.NumberFormat('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    }).format(value)
  }

  const parseCurrency = (value: string): number => {
    return parseFloat(value.replace(/[^0-9.-]+/g, ''))
  }

  return {
    formatCurrency,
    parseCurrency
  }
}

// src/composables/useApiCache.ts
import { ref, computed } from 'vue'
import { CacheService } from 'src/services/cache'

export function useApiCache<T>(
  cacheKey: string,
  apiCall: () => Promise<T>,
  ttl = 5 * 60 * 1000
) {
  const data = ref<T | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const loadData = async (forceRefresh = false) => {
    loading.value = true
    error.value = null

    try {
      if (!forceRefresh) {
        const cachedData = CacheService.get<T>(cacheKey)
        if (cachedData) {
          data.value = cachedData
          return cachedData
        }
      }

      const result = await apiCall()
      data.value = result
      CacheService.set(cacheKey, result, ttl)
      return result
    } catch (err) {
      error.value = err.message
      throw err
    } finally {
      loading.value = false
    }
  }

  const refresh = () => loadData(true)
  const clearCache = () => CacheService.remove(cacheKey)

  return {
    data: computed(() => data.value),
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    loadData,
    refresh,
    clearCache
  }
}
```

#### **5.2 Chart Components**
```vue
<!-- src/components/BudgetPieChart.vue -->
<template>
  <div>
    <canvas ref="chartCanvas"></canvas>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Chart, registerables } from 'chart.js'

Chart.register(...registerables)

interface BudgetData {
  category: string
  budgeted_amount: number
}

interface Props {
  budgetData: BudgetData[]
}

const props = defineProps<Props>()

const chartCanvas = ref<HTMLCanvasElement>()
let chart: Chart | null = null

const createChart = () => {
  if (!chartCanvas.value || !props.budgetData.length) return

  const ctx = chartCanvas.value.getContext('2d')
  if (!ctx) return

  if (chart) {
    chart.destroy()
  }

  const labels = props.budgetData.map(item => item.category)
  const data = props.budgetData.map(item => item.budgeted_amount)
  const colors = [
    '#667eea', '#764ba2', '#f093fb', '#f5576c',
    '#4facfe', '#00f2fe', '#43e97b', '#38f9d7'
  ]

  chart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: colors.slice(0, data.length),
        borderWidth: 2,
        borderColor: '#fff'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          position: 'right',
          labels: {
            usePointStyle: true,
            padding: 15
          }
        }
      }
    }
  })
}

watch(() => props.budgetData, () => {
  createChart()
}, { deep: true })

onMounted(() => {
  createChart()
})
</script>
```

### **Phase 6: Testing & Production (Week 6)**

#### **6.1 Unit Tests**
```typescript
// src/test/stores/projects.test.ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useProjectsStore } from 'stores/projects'

describe('Projects Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should initialize with correct default state', () => {
    const store = useProjectsStore()
    expect(store.currentProject).toBeNull()
    expect(store.projects).toEqual([])
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('should calculate total budget correctly', () => {
    const store = useProjectsStore()
    store.projects = [
      { id: 1, target_budget: 10000 },
      { id: 2, target_budget: 25000 }
    ]
    expect(store.totalBudget).toBe(35000)
  })
})

// src/test/services/api.test.ts
import { describe, it, expect, vi } from 'vitest'
import { apiClient } from 'src/services/api'
import axios from 'axios'

vi.mock('axios')
const mockedAxios = vi.mocked(axios)

describe('API Client', () => {
  it('should fetch data successfully', async () => {
    const mockData = { id: 1, name: 'Test Project' }
    mockedAxios.get.mockResolvedValue({ data: mockData })

    const result = await apiClient.get('/projects/1')
    expect(result).toEqual(mockData)
  })
})
```

#### **6.2 Production Build Configuration**
```javascript
// quasar.config.js - Production config
const { configure } = require('quasar/wrappers')

module.exports = configure(function (ctx) {
  return {
    build: {
      vueRouterMode: 'history',
      env: {
        API_BASE_URL: 'https://api.vrconstruction.com/api/v1',
        WS_URL: 'wss://api.vrconstruction.com/api/v1/ws'
      }
    },

    pwa: {
      workboxMode: 'generateSW',
      injectPwaMetaTags: true,
      swFilename: 'sw.js',
      manifestFilename: 'manifest.json'
    },

    electron: {
      inspectPort: 5858,
      bundler: ctx.dev ? 'packager' : 'builder'
    }
  }
})
```

#### **6.3 Docker Deployment**
```dockerfile
# Dockerfile
FROM node:18-alpine as build

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist/spa /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

---

## **🔧 Key Technologies & Architecture**

### **Frontend Stack**
- **Vue 3** - Composition API with `<script setup>` syntax
- **Quasar Framework** - Material Design components
- **TypeScript** - Full type safety
- **Pinia** - State management
- **Vue Router** - SPA routing
- **Axios** - HTTP client with interceptors

### **Backend Integration**
- **FastAPI** - REST API backend
- **WebSocket** - Real-time updates
- **JWT Authentication** - Secure API access
- **Caching** - Performance optimization
- **Error Handling** - Comprehensive error management

### **Development Tools**
- **Vite** - Fast development server
- **ESLint + Prettier** - Code quality
- **Vitest** - Unit testing
- **Playwright** - E2E testing

### **Production Features**
- **PWA** - Offline capabilities
- **Docker** - Containerized deployment
- **CDN** - Static asset optimization
- **Monitoring** - Performance tracking

---

## **📈 Implementation Benefits**

✅ **Type Safety** - Compile-time error checking  
✅ **Developer Experience** - Excellent IDE support  
✅ **Performance** - Optimized builds and caching  
✅ **Scalability** - Modular architecture  
✅ **Maintainability** - Clean, organized code  
✅ **Real-time Updates** - WebSocket integration  
✅ **Offline Support** - PWA capabilities  
✅ **Production Ready** - Docker deployment  

---

## **🚀 Getting Started**

1. **Setup Project**: `npm init quasar dashboard`
2. **Install Dependencies**: `npm install`
3. **Configure TypeScript**: Update `tsconfig.json`
4. **Create Stores**: Implement Pinia stores
5. **Build Components**: Use `<script setup>` syntax
6. **Add API Integration**: Connect to FastAPI backend
7. **Testing**: Add unit and E2E tests
8. **Deploy**: Docker containerization

This plan provides a **comprehensive roadmap** for building a modern, scalable Vue 3 + Quasar dashboard with TypeScript and complete backend integration! 🎯

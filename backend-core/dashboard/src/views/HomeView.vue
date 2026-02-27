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
        <template v-slot:action>
          <q-btn flat label="Retry" @click="refreshData" />
          <q-btn flat label="Load to VR" @click="loadProjectToVR" icon="view_in_ar" />
        </template>
      </q-banner>
    </div>

    <!-- Dashboard Content -->
    <div v-else>
      <!-- Project Header -->
      <div class="row items-center q-mb-md">
        <div class="col">
          <h4 class="q-ma-none">{{ project?.name || 'No Project Selected' }}</h4>
          <p class="text-grey-7 q-mb-none">{{ project?.description }}</p>
          <div class="text-caption text-grey-6">
            Status: <q-badge :color="getStatusColor(project?.status)" :label="project?.status" />
            • Type: {{ project?.project_type }}
            • Location: {{ project?.location }}
          </div>
        </div>
        <div class="col-auto">
          <q-btn
            color="primary"
            label="Refresh"
            icon="refresh"
            @click="refreshData"
            :loading="loading"
            class="q-mr-sm"
          />
          <q-btn
            color="secondary"
            label="Load to VR"
            icon="view_in_ar"
            @click="loadProjectToVR"
            :loading="loading"
            :disable="!project"
          />
        </div>
      </div>

      <!-- Summary Cards -->
      <div class="row q-col-gutter-md q-mb-lg">
        <!-- Budget Card -->
        <div class="col-12 col-md-3">
          <q-card class="bg-gradient-primary text-white cursor-pointer" @click="$router.push('/budget')">
            <q-card-section>
              <div class="text-h6">Total Budget</div>
              <div class="text-h4 q-mt-sm">
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
        <div class="col-12 col-md-3">
          <q-card class="bg-gradient-success text-white cursor-pointer" @click="$router.push('/timeline')">
            <q-card-section>
              <div class="text-h6">Progress</div>
              <div class="text-h4 q-mt-sm">
                {{ overallProgress.toFixed(0) }}%
              </div>
              <q-circular-progress
                :value="overallProgress"
                size="60px"
                :thickness="0.15"
                color="white"
                track-color="rgba(255,255,255,0.3)"
                show-value
                class="q-ma-sm"
              />
              <div class="text-caption q-mt-xs">
                {{ completedTasks }}/{{ totalTasks }} tasks completed
              </div>
            </q-card-section>
          </q-card>
        </div>

        <!-- Materials Card -->
        <div class="col-12 col-md-3">
          <q-card class="bg-gradient-info text-white cursor-pointer" @click="$router.push('/materials')">
            <q-card-section>
              <div class="text-h6">Materials</div>
              <div class="text-h4 q-mt-sm">
                ${{ formatCurrency(materialsCost) }}
              </div>
              <div class="text-caption q-mt-sm">
                {{ materialsCount }} materials tracked
              </div>
              <div v-if="lowStockCount > 0" class="text-caption text-orange">
                ⚠️ {{ lowStockCount }} low stock items
              </div>
            </q-card-section>
          </q-card>
        </div>

        <!-- Resources Card -->
        <div class="col-12 col-md-3">
          <q-card class="bg-gradient-warning text-white cursor-pointer" @click="$router.push('/resources')">
            <q-card-section>
              <div class="text-h6">Resources</div>
              <div class="text-h4 q-mt-sm">
                {{ activeResources }}
              </div>
              <div class="text-caption q-mt-sm">
                {{ availableResources }} available
              </div>
              <div class="text-caption">
                {{ maintenanceResources }} in maintenance
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
              <budget-pie-chart
                :budget-data="budgetData"
                :loading="loading"
              />
            </q-card-section>
          </q-card>
        </div>

        <!-- Cost Trend -->
        <div class="col-12 col-md-6">
          <q-card>
            <q-card-section>
              <div class="text-h6">Cost Trend (Last 30 Days)</div>
            </q-card-section>
            <q-card-section>
              <cost-trend-chart
                :expenses="recentExpenses"
                :loading="loading"
              />
            </q-card-section>
          </q-card>
        </div>
      </div>

      <!-- Timeline and Materials Row -->
      <div class="row q-col-gutter-md q-mb-lg">
        <!-- Timeline -->
        <div class="col-12 col-md-8">
          <q-card>
            <q-card-section>
              <div class="text-h6">Construction Timeline</div>
            </q-card-section>
            <q-card-section>
              <timeline-gantt
                :phases="sortedPhases"
                :loading="loading"
              />
            </q-card-section>
          </q-card>
        </div>

        <!-- Top Materials -->
        <div class="col-12 col-md-4">
          <q-card>
            <q-card-section>
              <div class="text-h6">Top Materials by Cost</div>
            </q-card-section>
            <q-card-section>
              <q-list v-if="topMaterials.length > 0">
                <q-item
                  v-for="material in topMaterials"
                  :key="material.id"
                  clickable
                  @click="$router.push('/materials')"
                >
                  <q-item-section>
                    <q-item-label>{{ material.material?.name }}</q-item-label>
                    <q-item-label caption>
                      {{ material.quantity_with_waste }} {{ material.material?.unit }}
                    </q-item-label>
                  </q-item-section>
                  <q-item-section side>
                    <q-item-label class="text-weight-bold">
                      ${{ formatCurrency(material.total_cost) }}
                    </q-item-label>
                    <q-badge
                      :color="getMaterialStatusColor(material.status)"
                      :label="material.status"
                      class="q-ml-sm"
                    />
                  </q-item-section>
                </q-item>
              </q-list>
              <div v-else class="text-center text-grey-6 q-pa-md">
                <q-icon name="inventory" size="48px" />
                <div class="q-mt-sm">No materials data available</div>
              </div>
            </q-card-section>
          </q-card>
        </div>
      </div>

      <!-- Recent Activity -->
      <q-card>
        <q-card-section>
          <div class="text-h6">Recent Activity</div>
        </q-card-section>
        <q-card-section>
          <q-timeline v-if="recentActivities.length > 0" color="primary">
            <q-timeline-entry
              v-for="activity in recentActivities"
              :key="activity.id"
              :title="activity.title"
              :subtitle="activity.description"
              :caption="formatDate(activity.timestamp)"
              :icon="activity.icon"
            >
              <div v-if="activity.details" class="text-caption">
                {{ activity.details }}
              </div>
            </q-timeline-entry>
          </q-timeline>
          <div v-else class="text-center text-grey-6 q-pa-md">
            <q-icon name="history" size="48px" />
            <div class="q-mt-sm">No recent activity</div>
          </div>
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
import { apiClient } from 'src/services/api'
import BudgetPieChart from 'components/BudgetPieChart.vue'
import CostTrendChart from 'components/CostTrendChart.vue'
import TimelineGantt from 'components/TimelineGantt.vue'
import type { ProjectSummary, ConstructionPhase, ProjectMaterial } from 'src/types/models'

const $q = useQuasar()
const projectsStore = useProjectsStore()
const materialsStore = useMaterialsStore()

// Reactive state
const loading = ref(false)
const error = ref<string | null>(null)
const loadingMessage = ref('Loading dashboard data...')

// Computed properties
const project = computed<ProjectSummary | null>(() => projectsStore.currentProject)
const sortedPhases = computed<ConstructionPhase[]>(() => {
  // This would come from a phases store in a full implementation
  return []
})
const topMaterials = computed<ProjectMaterial[]>(() => materialsStore.topMaterialsByCost(5))

const totalBudget = computed<number>(() => {
  return project.value?.target_budget || 0
})

const totalSpent = computed<number>(() => {
  // This would be calculated from budget transactions
  return Math.floor((project.value?.target_budget || 0) * (budgetPercentage.value / 100))
})

const budgetPercentage = computed<number>(() => {
  if (!project.value) return 0
  // This would be calculated from actual budget data
  return Math.floor(Math.random() * 60) + 20 // Mock data for now
})

const overallProgress = computed<number>(() => {
  if (!project.value) return 0
  return project.value.progress_percentage
})

const completedTasks = computed<number>(() => {
  if (!project.value) return 0
  return project.value.completed_tasks
})

const totalTasks = computed<number>(() => {
  if (!project.value) return 0
  return project.value.task_count
})

const materialsCost = computed<number>(() => materialsStore.totalCost)
const materialsCount = computed<number>(() => materialsStore.projectMaterials.length)
const lowStockCount = computed<number>(() => materialsStore.lowStockMaterials.length)

// Mock data - in a real implementation these would come from proper stores
const activeResources = computed(() => 12)
const availableResources = computed(() => 8)
const maintenanceResources = computed(() => 2)

const budgetData = computed(() => [
  { category: 'Materials', budgeted_amount: 45000, color: '#1976D2' },
  { category: 'Labor', budgeted_amount: 35000, color: '#26A69A' },
  { category: 'Equipment', budgeted_amount: 15000, color: '#9C27B0' },
  { category: 'Permits', budgeted_amount: 5000, color: '#F2C037' }
])

const recentExpenses = computed(() => [
  { date: '2024-01-15', value: 2500, category: 'Materials' },
  { date: '2024-01-14', value: 1800, category: 'Labor' },
  { date: '2024-01-13', value: 3200, category: 'Materials' },
  { date: '2024-01-12', value: 950, category: 'Equipment' },
  { date: '2024-01-11', value: 2100, category: 'Materials' }
])

const recentActivities = computed(() => [
  {
    id: 1,
    title: 'Material Delivered',
    description: 'Concrete blocks (500 units)',
    details: 'Supplier: ABC Construction Supplies',
    timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    icon: 'local_shipping'
  },
  {
    id: 2,
    title: 'Task Completed',
    description: 'Foundation preparation',
    details: 'Phase 1 - Week 2 completed ahead of schedule',
    timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    icon: 'check_circle'
  },
  {
    id: 3,
    title: 'Budget Updated',
    description: 'Additional $5,000 allocated',
    details: 'Approved by project manager',
    timestamp: new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString(),
    icon: 'attach_money'
  }
])

// Methods
const loadData = async (): Promise<void> => {
  loading.value = true
  error.value = null
  loadingMessage.value = 'Loading dashboard data...'

  try {
    loadingMessage.value = 'Loading projects...'
    await projectsStore.fetchProjects()

    const projectId = projectsStore.currentProject?.id
    if (projectId) {
      loadingMessage.value = 'Loading project materials...'
      // Materials are optional — don't block the dashboard if they fail
      try {
        await materialsStore.fetchProjectMaterials(projectId)
      } catch {
        console.warn('Could not load materials for project', projectId)
      }
    }
  } catch (err) {
    error.value = (err as Error).message
    $q.notify({
      type: 'negative',
      message: 'Failed to load dashboard data',
      caption: (err as Error).message
    })
  } finally {
    loading.value = false
  }
}

const refreshData = async (): Promise<void> => {
  await loadData()
  if (!error.value) {
    $q.notify({
      type: 'positive',
      message: 'Dashboard data refreshed'
    })
  }
}

const loadProjectToVR = (): void => {
  const projectId = projectsStore.currentProject?.id
  const projectName = projectsStore.currentProject?.name || 'Project'
  
  if (!projectId) {
    $q.notify({
      type: 'warning',
      message: 'No project selected',
      caption: 'Please select a project first'
    })
    return
  }
  
  // Show immediate feedback
  $q.notify({
    type: 'info',
    message: `Loading "${projectName}" into VR`,
    caption: 'Request sent to backend...',
    timeout: 2000
  })
  
  // Fire-and-forget: Send request without waiting for response
  apiClient.post<{
    success: boolean
    project_id: number
    project_name: string
    generation_id: string
    status: string
    message: string
    websocket_url: string
    vr_geometry_url: string
  }>(`/projects/${projectId}/load-to-vr`, {})
    .then((response) => {
      // Handle success in background
      console.log(`✅ Project ${projectId} load initiated, generation_id: ${response.generation_id}`)
      $q.notify({
        type: 'positive',
        message: 'VR load started successfully',
        caption: 'Image generation in progress...',
        timeout: 2000
      })
      
      // Trigger VR Quest app to load the project
      try {
        // Check if running in VR Quest WebView with Android interface
        if (typeof (window as any).Android !== 'undefined' && 
            typeof (window as any).Android.loadProject === 'function') {
          console.log(`📲 Calling Android.loadProject(${projectId})`)
          ;(window as any).Android.loadProject(projectId)
          $q.notify({
            type: 'positive',
            message: 'VR loading...',
            caption: 'Check your Quest headset!',
            timeout: 3000
          })
        } else {
          console.log('ℹ️ Not in VR WebView - Android interface not available')
        }
      } catch (err) {
        console.error('Failed to call Android.loadProject:', err)
      }
    })
    .catch((err) => {
      // Handle errors in background
      console.error('Load to VR failed:', err)
      $q.notify({
        type: 'negative',
        message: 'Failed to load project to VR',
        caption: (err as Error).message,
        timeout: 3000
      })
    })
  
  // Don't wait - return immediately
  console.log(`🚀 Load to VR request sent for project ${projectId}`)
}

const formatCurrency = (value: number): string => {
  if (!value && value !== 0) return '0'
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value)
}

const formatDate = (dateString: string): string => {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const getStatusColor = (status?: string): string => {
  const colors: Record<string, string> = {
    draft: 'grey',
    planning: 'blue',
    in_progress: 'orange',
    completed: 'green',
    on_hold: 'red'
  }
  return colors[status || ''] || 'grey'
}

const getMaterialStatusColor = (status: ProjectMaterial['status']): string => {
  const colors: Record<ProjectMaterial['status'], string> = {
    planned: 'grey',
    ordered: 'orange',
    delivered: 'blue',
    in_use: 'green',
    depleted: 'red'
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

.bg-gradient-warning
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)

.cursor-pointer
  cursor: pointer
  transition: transform 0.2s

  &:hover
    transform: translateY(-2px)
</style>

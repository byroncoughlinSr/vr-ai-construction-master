# Vue 3 + Quasar Dashboard - Complete Implementation

## 🎨 **Perfect Choice!**

**Why Vue 3 + Quasar is Excellent:**
- ✅ Beautiful Material Design components out of the box
- ✅ QTable, QCard, QTimeline built-in
- ✅ Responsive grid system
- ✅ Dark mode support
- ✅ 80+ UI components ready to use
- ✅ Smaller bundle size than alternatives
- ✅ Excellent TypeScript support

---

## **Step 1: Setup Quasar Project**

```bash
# Navigate to your project
cd ~/vr-construction-platform

# Install Quasar CLI
npm install -g @quasar/cli

# Create Quasar project
npm init quasar

# Follow prompts:
# - App with Quasar CLI
# - Project folder: dashboard
# - Quasar v2 (Vue 3)
# - TypeScript: No (or Yes if you prefer)
# - Features: ESLint, Axios
# - CSS preprocessor: Sass
# - Package manager: npm

cd dashboard

# Install additional dependencies
npm install chart.js vue-chartjs axios
npm install date-fns  # For date formatting

# Start development server
quasar dev
```

---

## **Step 2: Configure API Connection**

```javascript
// src/boot/axios.js
import { boot } from 'quasar/wrappers'
import axios from 'axios'

// Create axios instance
const api = axios.create({ 
  baseURL: 'http://localhost:8000/api/v1'
})

export default boot(({ app }) => {
  app.config.globalProperties.$axios = axios
  app.config.globalProperties.$api = api
})

export { api }
```

```javascript
// quasar.config.js
// Add axios to boot
boot: [
  'axios'
]
```

---

## **Step 3: Main Dashboard Layout**

```vue
<!-- src/layouts/MainLayout.vue -->
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
          @update:model-value="loadProject"
        />

        <!-- Export Menu -->
        <q-btn-dropdown
          flat
          dense
          label="Export"
          icon="download"
        >
          <q-list>
            <q-item clickable v-close-popup @click="exportPDF">
              <q-item-section avatar>
                <q-icon name="picture_as_pdf" color="red" />
              </q-item-section>
              <q-item-section>
                <q-item-label>PDF Report</q-item-label>
              </q-item-section>
            </q-item>

            <q-item clickable v-close-popup @click="exportExcel">
              <q-item-section avatar>
                <q-icon name="table_chart" color="green" />
              </q-item-section>
              <q-item-section>
                <q-item-label>Excel Spreadsheet</q-item-label>
              </q-item-section>
            </q-item>

            <q-item clickable v-close-popup @click="exportImages">
              <q-item-section avatar>
                <q-icon name="photo_library" color="blue" />
              </q-item-section>
              <q-item-section>
                <q-item-label>All Images (ZIP)</q-item-label>
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
                  <q-toggle v-model="darkMode" />
                </q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
      </q-toolbar>
    </q-header>

    <!-- Left Drawer (Navigation) -->
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

        <q-item clickable to="/resources">
          <q-item-section avatar>
            <q-icon name="groups" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Resources</q-item-label>
          </q-item-section>
        </q-item>

        <q-item clickable to="/3d-viewer">
          <q-item-section avatar>
            <q-icon name="view_in_ar" />
          </q-item-section>
          <q-item-section>
            <q-item-label>3D Viewer</q-item-label>
          </q-item-section>
        </q-item>

        <q-separator class="q-my-md" />

        <q-item clickable to="/images">
          <q-item-section avatar>
            <q-icon name="photo_library" />
          </q-item-section>
          <q-item-section>
            <q-item-label>AI Images</q-item-label>
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

<script>
import { ref, onMounted } from 'vue'
import { api } from 'boot/axios'
import { useQuasar } from 'quasar'

export default {
  name: 'MainLayout',

  setup() {
    const $q = useQuasar()
    const leftDrawerOpen = ref(true)
    const darkMode = ref($q.dark.isActive)
    const selectedProject = ref(null)
    const projects = ref([])

    // Watch dark mode toggle
    watch(darkMode, (val) => {
      $q.dark.set(val)
    })

    // Load projects list
    const loadProjects = async () => {
      try {
        const response = await api.get('/projects')
        projects.value = response.data
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

    const loadProject = (project) => {
      // Emit event or use store to update current project
      console.log('Loading project:', project)
    }

    const exportPDF = async () => {
      if (!selectedProject.value) return
      
      $q.loading.show({ message: 'Generating PDF...' })
      
      try {
        const response = await api.get(
          `/projects/${selectedProject.value.id}/report/pdf`,
          { responseType: 'blob' }
        )
        
        // Download file
        const url = window.URL.createObjectURL(new Blob([response.data]))
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', `${selectedProject.value.name}_Report.pdf`)
        document.body.appendChild(link)
        link.click()
        link.remove()
        
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

    const exportExcel = () => {
      $q.notify('Excel export coming soon!')
    }

    const exportImages = () => {
      $q.notify('Image export coming soon!')
    }

    onMounted(() => {
      loadProjects()
    })

    return {
      leftDrawerOpen,
      darkMode,
      selectedProject,
      projects,
      loadProject,
      exportPDF,
      exportExcel,
      exportImages
    }
  }
}
</script>
```

---

## **Step 4: Dashboard Home Page**

```vue
<!-- src/pages/IndexPage.vue -->
<template>
  <q-page class="q-pa-md">
    
    <!-- Project Header -->
    <div class="row q-mb-md">
      <div class="col-12">
        <h4 class="q-ma-none">{{ project?.name }}</h4>
        <p class="text-grey-7 q-mb-none">{{ project?.description }}</p>
      </div>
    </div>

    <!-- Summary Cards -->
    <div class="row q-col-gutter-md q-mb-lg">
      <!-- Total Cost Card -->
      <div class="col-12 col-md-4">
        <q-card class="bg-gradient-primary text-white">
          <q-card-section>
            <div class="text-h6">Total Cost</div>
            <div class="text-h3 q-mt-sm">
              ${{ formatCurrency(project?.target_budget) }}
            </div>
            <div class="q-mt-sm">
              <q-linear-progress 
                :value="project?.spent_percentage / 100" 
                color="white"
                track-color="rgba(255,255,255,0.3)"
                size="8px"
                rounded
              />
              <div class="text-caption q-mt-xs">
                Spent: ${{ formatCurrency(project?.total_spent) }} 
                ({{ project?.spent_percentage?.toFixed(1) }}%)
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>

      <!-- Timeline Card -->
      <div class="col-12 col-md-4">
        <q-card class="bg-gradient-success text-white">
          <q-card-section>
            <div class="text-h6">Timeline</div>
            <div class="text-h3 q-mt-sm">
              {{ project?.target_completion_days }} days
            </div>
            <div class="q-mt-sm">
              <div class="text-caption">
                ~{{ Math.ceil(project?.target_completion_days / 30) }} months
              </div>
              <div class="text-caption">
                Status: <strong>{{ project?.status }}</strong>
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>

      <!-- Progress Card -->
      <div class="col-12 col-md-4">
        <q-card class="bg-gradient-info text-white">
          <q-card-section>
            <div class="text-h6">Progress</div>
            <div class="text-h3 q-mt-sm">
              {{ project?.progress_percentage?.toFixed(0) }}%
            </div>
            <div class="q-mt-sm">
              <q-circular-progress
                :value="project?.progress_percentage || 0"
                size="80px"
                :thickness="0.15"
                color="white"
                track-color="rgba(255,255,255,0.3)"
                show-value
                class="q-ma-sm"
              >
                <div class="text-white text-bold">
                  {{ project?.progress_percentage?.toFixed(0) }}%
                </div>
              </q-circular-progress>
              <div class="text-caption">
                {{ completedTasks }} of {{ totalTasks }} tasks complete
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <!-- Charts Row -->
    <div class="row q-col-gutter-md q-mb-lg">
      <!-- Budget Breakdown Chart -->
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

      <!-- Cost Trend Chart -->
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
    <div class="row q-mb-lg">
      <div class="col-12">
        <q-card>
          <q-card-section>
            <div class="text-h6">Construction Timeline</div>
          </q-card-section>
          <q-card-section>
            <timeline-gantt :phases="phases" />
          </q-card-section>
        </q-card>
      </div>
    </div>

    <!-- Quick Info Grid -->
    <div class="row q-col-gutter-md">
      <!-- Recent Materials -->
      <div class="col-12 col-md-6">
        <q-card>
          <q-card-section>
            <div class="text-h6">Materials Summary</div>
          </q-card-section>
          <q-card-section>
            <q-list separator>
              <q-item v-for="material in topMaterials" :key="material.id">
                <q-item-section>
                  <q-item-label>{{ material.material.name }}</q-item-label>
                  <q-item-label caption>
                    {{ material.quantity_with_waste }} {{ material.material.unit }}
                  </q-item-label>
                </q-item-section>
                <q-item-section side>
                  <q-item-label>
                    ${{ formatCurrency(material.total_cost) }}
                  </q-item-label>
                  <q-item-label caption>
                    <q-badge 
                      :color="getStatusColor(material.status)"
                      :label="material.status"
                    />
                  </q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
            <div class="text-center q-mt-md">
              <q-btn 
                flat 
                color="primary" 
                label="View All Materials" 
                to="/materials"
              />
            </div>
          </q-card-section>
        </q-card>
      </div>

      <!-- Upcoming Tasks -->
      <div class="col-12 col-md-6">
        <q-card>
          <q-card-section>
            <div class="text-h6">Upcoming Tasks</div>
          </q-card-section>
          <q-card-section>
            <q-timeline color="primary">
              <q-timeline-entry
                v-for="task in upcomingTasks"
                :key="task.id"
                :title="task.task_name"
                :subtitle="formatDate(task.planned_start_date)"
                :icon="getTaskIcon(task.status)"
              >
                <div>
                  {{ task.description }}
                </div>
                <div class="text-caption text-grey-7 q-mt-xs">
                  Duration: {{ task.estimated_duration_days }} days
                </div>
              </q-timeline-entry>
            </q-timeline>
            <div class="text-center q-mt-md">
              <q-btn 
                flat 
                color="primary" 
                label="View Full Timeline" 
                to="/timeline"
              />
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>

  </q-page>
</template>

<script>
import { ref, onMounted, computed } from 'vue'
import { api } from 'boot/axios'
import { useQuasar } from 'quasar'
import { format } from 'date-fns'
import BudgetPieChart from 'components/BudgetPieChart.vue'
import CostTrendChart from 'components/CostTrendChart.vue'
import TimelineGantt from 'components/TimelineGantt.vue'

export default {
  name: 'IndexPage',

  components: {
    BudgetPieChart,
    CostTrendChart,
    TimelineGantt
  },

  setup() {
    const $q = useQuasar()
    
    // State
    const project = ref(null)
    const phases = ref([])
    const materials = ref([])
    const budgetData = ref([])
    const expenses = ref([])
    const tasks = ref([])

    // Computed
    const topMaterials = computed(() => {
      return materials.value
        .sort((a, b) => b.total_cost - a.total_cost)
        .slice(0, 5)
    })

    const upcomingTasks = computed(() => {
      return tasks.value
        .filter(t => t.status === 'not_started' || t.status === 'in_progress')
        .sort((a, b) => new Date(a.planned_start_date) - new Date(b.planned_start_date))
        .slice(0, 5)
    })

    const completedTasks = computed(() => {
      return tasks.value.filter(t => t.status === 'completed').length
    })

    const totalTasks = computed(() => tasks.value.length)

    // Methods
    const loadProjectData = async () => {
      $q.loading.show({ message: 'Loading project data...' })

      try {
        const projectId = 1 // Get from route or store

        const [projectRes, phasesRes, materialsRes, budgetRes, tasksRes] = await Promise.all([
          api.get(`/projects/${projectId}/summary`),
          api.get(`/projects/${projectId}/phases`),
          api.get(`/projects/${projectId}/materials`),
          api.get(`/projects/${projectId}/budget`),
          api.get(`/projects/${projectId}/tasks`)
        ])

        project.value = projectRes.data
        phases.value = phasesRes.data
        materials.value = materialsRes.data.materials || materialsRes.data
        budgetData.value = budgetRes.data
        tasks.value = tasksRes.data

      } catch (error) {
        console.error('Error loading project:', error)
        $q.notify({
          type: 'negative',
          message: 'Failed to load project data',
          caption: error.message
        })
      } finally {
        $q.loading.hide()
      }
    }

    const formatCurrency = (value) => {
      if (!value) return '0'
      return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
      }).format(value)
    }

    const formatDate = (date) => {
      if (!date) return 'TBD'
      return format(new Date(date), 'MMM dd, yyyy')
    }

    const getStatusColor = (status) => {
      const colors = {
        planned: 'grey',
        ordered: 'orange',
        delivered: 'blue',
        in_use: 'green',
        depleted: 'grey-5',
        completed: 'green',
        in_progress: 'blue',
        not_started: 'grey',
        delayed: 'red'
      }
      return colors[status] || 'grey'
    }

    const getTaskIcon = (status) => {
      const icons = {
        completed: 'check_circle',
        in_progress: 'radio_button_checked',
        not_started: 'radio_button_unchecked',
        delayed: 'warning'
      }
      return icons[status] || 'circle'
    }

    onMounted(() => {
      loadProjectData()
    })

    return {
      project,
      phases,
      materials,
      budgetData,
      expenses,
      tasks,
      topMaterials,
      upcomingTasks,
      completedTasks,
      totalTasks,
      formatCurrency,
      formatDate,
      getStatusColor,
      getTaskIcon
    }
  }
}
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

---

## **Step 5: Chart Components**

```vue
<!-- src/components/BudgetPieChart.vue -->
<template>
  <div>
    <canvas ref="chartCanvas"></canvas>
  </div>
</template>

<script>
import { ref, onMounted, watch } from 'vue'
import { Chart, registerables } from 'chart.js'

Chart.register(...registerables)

export default {
  name: 'BudgetPieChart',

  props: {
    budgetData: {
      type: Array,
      required: true
    }
  },

  setup(props) {
    const chartCanvas = ref(null)
    let chart = null

    const createChart = () => {
      if (!chartCanvas.value || !props.budgetData.length) return

      const ctx = chartCanvas.value.getContext('2d')

      // Destroy existing chart
      if (chart) {
        chart.destroy()
      }

      const labels = props.budgetData.map(item => item.category)
      const data = props.budgetData.map(item => item.budgeted_amount)
      const colors = [
        '#667eea',
        '#764ba2',
        '#f093fb',
        '#f5576c',
        '#4facfe',
        '#00f2fe',
        '#43e97b',
        '#38f9d7',
        '#fa709a',
        '#fee140'
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
            },
            tooltip: {
              callbacks: {
                label: function(context) {
                  let label = context.label || ''
                  if (label) {
                    label += ': '
                  }
                  label += '$' + context.parsed.toLocaleString()
                  return label
                }
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

    return {
      chartCanvas
    }
  }
}
</script>
```

```vue
<!-- src/components/TimelineGantt.vue -->
<template>
  <div class="timeline-gantt">
    <q-timeline color="primary" layout="comfortable">
      <q-timeline-entry
        v-for="phase in sortedPhases"
        :key="phase.id"
        :title="phase.phase_name"
        :subtitle="formatDateRange(phase)"
        :icon="getPhaseIcon(phase.status)"
        :color="getPhaseColor(phase.status)"
      >
        <div class="row items-center q-gutter-sm">
          <div class="col">
            <div class="text-body2">{{ phase.description }}</div>
            <div class="text-caption text-grey-7 q-mt-xs">
              Duration: {{ phase.estimated_duration_days }} days
            </div>
          </div>
          <div class="col-auto">
            <q-badge 
              :color="getPhaseColor(phase.status)" 
              :label="phase.status.replace('_', ' ')"
            />
          </div>
        </div>
        
        <!-- Progress Bar -->
        <q-linear-progress
          :value="phase.progress_percentage / 100"
          :color="getPhaseColor(phase.status)"
          size="12px"
          rounded
          class="q-mt-sm"
        >
          <div class="absolute-full flex flex-center">
            <q-badge 
              color="white" 
              text-color="black" 
              :label="`${phase.progress_percentage}%`"
            />
          </div>
        </q-linear-progress>

        <!-- Cost Info -->
        <div class="row q-mt-sm text-caption">
          <div class="col">
            Budget: ${{ formatNumber(phase.estimated_cost) }}
          </div>
          <div class="col-auto">
            Actual: ${{ formatNumber(phase.actual_cost || 0) }}
          </div>
        </div>
      </q-timeline-entry>
    </q-timeline>
  </div>
</template>

<script>
import { computed } from 'vue'
import { format } from 'date-fns'

export default {
  name: 'TimelineGantt',

  props: {
    phases: {
      type: Array,
      required: true
    }
  },

  setup(props) {
    const sortedPhases = computed(() => {
      return [...props.phases].sort((a, b) => a.phase_order - b.phase_order)
    })

    const formatDateRange = (phase) => {
      if (!phase.planned_start_date) return 'Not scheduled'
      
      const start = format(new Date(phase.planned_start_date), 'MMM dd')
      const end = phase.planned_end_date 
        ? format(new Date(phase.planned_end_date), 'MMM dd, yyyy')
        : 'TBD'
      
      return `${start} - ${end}`
    }

    const getPhaseIcon = (status) => {
      const icons = {
        completed: 'check_circle',
        in_progress: 'pending',
        not_started: 'schedule',
        delayed: 'warning'
      }
      return icons[status] || 'circle'
    }

    const getPhaseColor = (status) => {
      const colors = {
        completed: 'positive',
        in_progress: 'primary',
        not_started: 'grey',
        delayed: 'negative'
      }
      return colors[status] || 'grey'
    }

    const formatNumber = (value) => {
      return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
      }).format(value || 0)
    }

    return {
      sortedPhases,
      formatDateRange,
      getPhaseIcon,
      getPhaseColor,
      formatNumber
    }
  }
}
</script>
```

---

## **Step 6: Materials Page**

```vue
<!-- src/pages/MaterialsPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-md">
      <div class="col">
        <h5 class="q-ma-none">Materials</h5>
      </div>
      <div class="col-auto">
        <q-btn 
          color="primary" 
          label="Add Material" 
          icon="add"
          @click="addMaterialDialog = true"
        />
      </div>
    </div>

    <!-- Filters -->
    <q-card class="q-mb-md">
      <q-card-section>
        <div class="row q-col-gutter-md">
          <div class="col-12 col-md-3">
            <q-select
              v-model="filterCategory"
              :options="categories"
              label="Category"
              outlined
              dense
              clearable
            />
          </div>
          <div class="col-12 col-md-3">
            <q-select
              v-model="filterStatus"
              :options="statusOptions"
              label="Status"
              outlined
              dense
              clearable
            />
          </div>
          <div class="col-12 col-md-6">
            <q-input
              v-model="searchQuery"
              label="Search materials..."
              outlined
              dense
              clearable
            >
              <template v-slot:append>
                <q-icon name="search" />
              </template>
            </q-input>
          </div>
        </div>
      </q-card-section>
    </q-card>

    <!-- Materials Table -->
    <q-table
      :rows="filteredMaterials"
      :columns="columns"
      row-key="id"
      :pagination="pagination"
      :loading="loading"
      flat
      bordered
    >
      <!-- Material Name -->
      <template v-slot:body-cell-name="props">
        <q-td :props="props">
          <div class="text-weight-medium">{{ props.row.material.name }}</div>
          <div class="text-caption text-grey-7">{{ props.row.material.category }}</div>
        </q-td>
      </template>

      <!-- Quantity -->
      <template v-slot:body-cell-quantity="props">
        <q-td :props="props">
          {{ props.row.quantity_with_waste.toFixed(2) }} {{ props.row.material.unit }}
          <div class="text-caption text-grey-7">
            (includes {{ props.row.waste_factor }}% waste)
          </div>
        </q-td>
      </template>

      <!-- Cost -->
      <template v-slot:body-cell-cost="props">
        <q-td :props="props">
          <div class="text-weight-bold">
            ${{ formatCurrency(props.row.total_cost) }}
          </div>
          <div class="text-caption text-grey-7">
            ${{ props.row.unit_cost_at_time }}/{{ props.row.material.unit }}
          </div>
        </q-td>
      </template>

      <!-- Status -->
      <template v-slot:body-cell-status="props">
        <q-td :props="props">
          <q-badge 
            :color="getStatusColor(props.row.status)"
            :label="props.row.status.replace('_', ' ')"
          />
        </q-td>
      </template>

      <!-- Actions -->
      <template v-slot:body-cell-actions="props">
        <q-td :props="props">
          <q-btn
            flat
            dense
            round
            icon="more_vert"
          >
            <q-menu>
              <q-list>
                <q-item clickable v-close-popup @click="editMaterial(props.row)">
                  <q-item-section>Edit</q-item-section>
                </q-item>
                <q-item clickable v-close-popup @click="deleteMaterial(props.row)">
                  <q-item-section>Delete</q-item-section>
                </q-item>
              </q-list>
            </q-menu>
          </q-btn>
        </q-td>
      </template>

      <!-- Bottom: Total Cost -->
      <template v-slot:bottom>
        <div class="full-width row justify-end q-pa-md">
          <div class="text-h6">
            Total Materials Cost: 
            <span class="text-primary">
              ${{ formatCurrency(totalCost) }}
            </span>
          </div>
        </div>
      </template>
    </q-table>

  </q-page>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from 'boot/axios'
import { useQuasar } from 'quasar'

export default {
  name: 'MaterialsPage',

  setup() {
    const $q = useQuasar()
    
    const materials = ref([])
    const loading = ref(false)
    const searchQuery = ref('')
    const filterCategory = ref(null)
    const filterStatus = ref(null)
    const addMaterialDialog = ref(false)

    const pagination = ref({
      rowsPerPage: 25
    })

    const columns = [
      { name: 'name', label: 'Material', field: 'name', align: 'left', sortable: true },
      { name: 'quantity', label: 'Quantity', field: 'quantity_with_waste', align: 'right', sortable: true },
      { name: 'cost', label: 'Total Cost', field: 'total_cost', align: 'right', sortable: true },
      { name: 'status', label: 'Status', field: 'status', align: 'center', sortable: true },
      { name: 'phase', label: 'Phase', field: 'assigned_to_phase', align: 'left', sortable: true },
      { name: 'actions', label: 'Actions', field: 'actions', align: 'center' }
    ]

    const categories = [
      'lumber', 'concrete', 'roofing', 'electrical', 
      'plumbing', 'drywall', 'flooring', 'insulation'
    ]

    const statusOptions = [
      'planned', 'ordered', 'delivered', 'in_use', 'depleted'
    ]

    // Computed
    const filteredMaterials = computed(() => {
      let result = materials.value

      if (searchQuery.value) {
        result = result.filter(m => 
          m.material.name.toLowerCase().includes(searchQuery.value.toLowerCase())
        )
      }

      if (filterCategory.value) {
        result = result.filter(m => m.material.category === filterCategory.value)
      }

      if (filterStatus.value) {
        result = result.filter(m => m.status === filterStatus.value)
      }

      return result
    })

    const totalCost = computed(() => {
      return filteredMaterials.value.reduce((sum, m) => sum + m.total_cost, 0)
    })

    // Methods
    const loadMaterials = async () => {
      loading.value = true
      try {
        const response = await api.get('/projects/1/materials')
        materials.value = response.data.materials || response.data
      } catch (error) {
        $q.notify({
          type: 'negative',
          message: 'Failed to load materials'
        })
      } finally {
        loading.value = false
      }
    }

    const formatCurrency = (value) => {
      return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
      }).format(value)
    }

    const getStatusColor = (status) => {
      const colors = {
        planned: 'grey',
        ordered: 'orange',
        delivered: 'blue',
        in_use: 'green',
        depleted: 'grey-5'
      }
      return colors[status] || 'grey'
    }

    const editMaterial = (material) => {
      console.log('Edit:', material)
    }

    const deleteMaterial = (material) => {
      $q.dialog({
        title: 'Confirm',
        message: `Delete ${material.material.name}?`,
        cancel: true
      }).onOk(() => {
        // Delete API call
      })
    }

    onMounted(() => {
      loadMaterials()
    })

    return {
      materials,
      loading,
      searchQuery,
      filterCategory,
      filterStatus,
      addMaterialDialog,
      pagination,
      columns,
      categories,
      statusOptions,
      filteredMaterials,
      totalCost,
      formatCurrency,
      getStatusColor,
      editMaterial,
      deleteMaterial
    }
  }
}
</script>
```

---

## **Step 7: Run the Dashboard**

```bash
# Start Quasar dev server
quasar dev

# Opens at http://localhost:9000 (or 8080)

# Build for production
quasar build

# Preview production build
quasar serve dist/spa
```

---

## **Key Quasar Features Used**

✅ **QTable** - Beautiful, sortable, filterable tables  
✅ **QCard** - Material Design cards  
✅ **QTimeline** - Perfect for construction phases  
✅ **QLinearProgress** - Progress bars  
✅ **QCircularProgress** - Circular progress indicators  
✅ **QBadge** - Status indicators  
✅ **QBtnDropdown** - Export menu  
✅ **QDrawer** - Side navigation  
✅ **QNotify** - Toast notifications  
✅ **QLoading** - Loading overlay  
✅ **QDialog** - Modals and confirmations  

---

## **Next Steps**

1. ✅ Add routing (`src/router/routes.js`)
2. ✅ Create remaining pages (Budget, Resources, 3D Viewer)
3. ✅ Add Pinia store for state management
4. ✅ Connect all API endpoints
5. ✅ Add authentication (optional)
6. ✅ Deploy to production

This gives you a **professional, responsive dashboard** with Vue 3 + Quasar! 🚀

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
          v-model="selectedProjectId"
          :options="projectOptions"
          option-value="id"
          option-label="name"
          label="Select Project"
          dark
          outlined
          dense
          style="min-width: 250px"
          class="q-mr-md"
          @update:model-value="onProjectChange"
          :loading="projectsStore.loading"
        />

        <!-- Export Menu -->
        <q-btn-dropdown flat dense label="Export" icon="download" class="q-mr-sm">
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
                <q-item-label>Excel Report</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-btn-dropdown>

        <!-- Notifications -->
        <q-btn flat dense round icon="notifications" class="q-mr-sm">
          <q-badge color="negative" floating>3</q-badge>
          <q-menu>
            <q-list style="min-width: 300px">
              <q-item-label header>Notifications</q-item-label>
              <q-item clickable>
                <q-item-section avatar>
                  <q-icon name="warning" color="orange" />
                </q-item-section>
                <q-item-section>
                  <q-item-label>Material shortage alert</q-item-label>
                  <q-item-label caption>2 hours ago</q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>

        <!-- User Menu -->
        <q-btn flat dense round>
          <q-avatar size="32px">
            <q-icon name="person" />
          </q-avatar>
          <q-menu>
            <q-list style="min-width: 200px">
              <q-item clickable>
                <q-item-section>
                  <q-item-label>{{ authStore.fullName }}</q-item-label>
                  <q-item-label caption>{{ authStore.user?.email }}</q-item-label>
                </q-item-section>
              </q-item>
              <q-separator />
              <q-item clickable @click="toggleDarkMode">
                <q-item-section avatar>
                  <q-icon name="dark_mode" />
                </q-item-section>
                <q-item-section>
                  <q-item-label>Dark Mode</q-item-label>
                </q-item-section>
                <q-item-section side>
                  <q-toggle v-model="$q.dark.isActive" />
                </q-item-section>
              </q-item>
              <q-separator />
              <q-item clickable @click="logout">
                <q-item-section avatar>
                  <q-icon name="logout" />
                </q-item-section>
                <q-item-section>
                  <q-item-label>Logout</q-item-label>
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
        <q-item-label header class="text-primary">Navigation</q-item-label>

        <q-item clickable to="/" exact active-class="bg-primary-1">
          <q-item-section avatar>
            <q-icon name="dashboard" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Dashboard</q-item-label>
          </q-item-section>
        </q-item>

        <q-item clickable to="/timeline" active-class="bg-primary-1">
          <q-item-section avatar>
            <q-icon name="event" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Timeline</q-item-label>
          </q-item-section>
        </q-item>

        <q-item clickable to="/materials" active-class="bg-primary-1">
          <q-item-section avatar>
            <q-icon name="inventory" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Materials</q-item-label>
          </q-item-section>
        </q-item>

        <q-item clickable to="/budget" active-class="bg-primary-1">
          <q-item-section avatar>
            <q-icon name="attach_money" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Budget</q-item-label>
          </q-item-section>
        </q-item>

        <q-item clickable to="/resources" active-class="bg-primary-1">
          <q-item-section avatar>
            <q-icon name="engineering" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Resources</q-item-label>
          </q-item-section>
        </q-item>

        <q-item clickable to="/compliance" active-class="bg-primary-1">
          <q-item-section avatar>
            <q-icon name="gavel" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Compliance</q-item-label>
          </q-item-section>
        </q-item>

        <q-separator class="q-my-md" />

        <q-item-label header>Quick Actions</q-item-label>

        <q-item clickable @click="createNewProject" v-if="authStore.canManageProjects">
          <q-item-section avatar>
            <q-icon name="add" />
          </q-item-section>
          <q-item-section>
            <q-item-label>New Project</q-item-label>
          </q-item-section>
        </q-item>

        <q-item clickable @click="refreshData">
          <q-item-section avatar>
            <q-icon name="refresh" />
          </q-item-section>
          <q-item-section>
            <q-item-label>Refresh Data</q-item-label>
          </q-item-section>
        </q-item>
      </q-list>
    </q-drawer>

    <!-- Main Content -->
    <q-page-container>
      <router-view />
    </q-page-container>

    <!-- Footer -->
    <q-footer elevated class="bg-grey-8 text-white">
      <q-toolbar>
        <q-toolbar-title class="text-caption">
          VR Construction Platform v{{ appVersion }}
        </q-toolbar-title>
        <q-space />
        <div class="text-caption">
          {{ connectionStatus }}
        </div>
      </q-toolbar>
    </q-footer>
  </q-layout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import { useProjectsStore } from 'stores/projects'
import { useAuthStore } from 'stores/auth'
import { websocketService } from 'src/services/websocket'

const $q = useQuasar()
const router = useRouter()
const projectsStore = useProjectsStore()
const authStore = useAuthStore()

// Reactive state
const leftDrawerOpen = ref(true)
const selectedProjectId = ref<number | null>(null)

// Computed properties
const projectOptions = computed(() =>
  projectsStore.projects.map(project => ({
    id: project.id,
    name: project.name,
    label: `${project.name} (${project.project_type})`
  }))
)

const appVersion = computed(() => import.meta.env.VITE_APP_VERSION || '1.0.0')

const connectionStatus = computed(() => {
  const state = websocketService.getConnectionState()
  switch (state) {
    case 'connected':
      return '🟢 Connected'
    case 'connecting':
      return '🟡 Connecting...'
    case 'disconnected':
      return '🔴 Disconnected'
    default:
      return '⚪ Unknown'
  }
})

// Methods
const loadProjects = async () => {
  try {
    await projectsStore.fetchProjects()
    if (projectsStore.projects.length > 0 && !selectedProjectId.value) {
      selectedProjectId.value = projectsStore.projects[0].id
      await onProjectChange(projectsStore.projects[0].id)
    }
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: 'Failed to load projects'
    })
  }
}

const onProjectChange = async (projectId: number) => {
  if (!projectId) return

  try {
    await projectsStore.fetchProjectSummary(projectId)
    await websocketService.subscribeToProject(projectId)

    $q.notify({
      type: 'positive',
      message: `Loaded project: ${projectsStore.currentProject?.name}`
    })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: 'Failed to load project data'
    })
  }
}

const toggleDarkMode = () => {
  $q.dark.toggle()
}

const logout = async () => {
  try {
    await authStore.logout()
    router.push('/login')
  } catch (error) {
    console.error('Logout failed:', error)
  }
}

const exportPDF = async () => {
  if (!projectsStore.currentProject) return

  $q.loading.show({ message: 'Generating PDF...' })

  try {
    // This would integrate with your backend PDF generation
    const response = await fetch(`/api/projects/${projectsStore.currentProject.id}/report/pdf`)
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${projectsStore.currentProject.name}_Report.pdf`
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

const exportExcel = async () => {
  if (!projectsStore.currentProject) return

  $q.loading.show({ message: 'Generating Excel...' })

  try {
    // This would integrate with your backend Excel generation
    const response = await fetch(`/api/projects/${projectsStore.currentProject.id}/report/excel`)
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${projectsStore.currentProject.name}_Report.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)

    $q.notify({
      type: 'positive',
      message: 'Excel downloaded successfully'
    })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: 'Failed to generate Excel'
    })
  } finally {
    $q.loading.hide()
  }
}

const createNewProject = () => {
  // This would open a project creation dialog
  $q.notify({
    type: 'info',
    message: 'Project creation dialog would open here'
  })
}

const refreshData = async () => {
  $q.loading.show({ message: 'Refreshing data...' })

  try {
    await Promise.all([
      loadProjects(),
      selectedProjectId.value ? projectsStore.fetchProjectSummary(selectedProjectId.value) : Promise.resolve()
    ])

    $q.notify({
      type: 'positive',
      message: 'Data refreshed successfully'
    })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: 'Failed to refresh data'
    })
  } finally {
    $q.loading.hide()
  }
}

// WebSocket connection
const connectWebSocket = async () => {
  try {
    await websocketService.connect()
  } catch (error) {
    console.warn('WebSocket connection failed:', error)
  }
}

// Lifecycle
onMounted(async () => {
  await loadProjects()
  await connectWebSocket()
})

// Watch for authentication changes
watch(() => authStore.isAuthenticated, async (isAuthenticated) => {
  if (!isAuthenticated) {
    router.push('/login')
  }
})
</script>

<style lang="sass" scoped>
.q-drawer
  .q-item--active
    background-color: rgba(var(--q-primary-rgb), 0.1)
    color: var(--q-primary)
</style>

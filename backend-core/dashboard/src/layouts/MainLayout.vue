<template>
  <q-layout view="hHh LpR fFf">
    <q-header bordered class="app-header">
      <q-toolbar class="q-px-sm q-px-md-md" style="min-height: 60px">
        <q-btn flat dense round icon="menu" aria-label="Menu" class="q-mr-xs" @click="leftDrawerOpen = !leftDrawerOpen" />

        <router-link to="/" class="brand row items-center no-wrap q-mr-md">
          <q-avatar size="34px" color="primary" text-color="white" icon="architecture" font-size="20px" class="brand-mark" />
          <div class="gt-sm q-ml-sm">
            <div class="text-subtitle2 text-weight-bold leading-tight">VR AI Construction</div>
            <div class="text-caption text-muted leading-tight">Design · Build · Clients</div>
          </div>
        </router-link>

        <!-- Project switcher -->
        <q-select
          :model-value="projects.currentProjectId"
          :options="projectOptions"
          emit-value
          map-options
          outlined
          dense
          options-dense
          :loading="projects.loading"
          class="project-switcher"
          :display-value="projects.currentProject?.name ?? (projects.loading ? 'Loading…' : 'No project')"
          aria-label="Project"
          @update:model-value="onSelectProject"
        >
          <template #prepend><q-icon name="home_work" size="20px" /></template>
          <template #option="{ itemProps, opt }">
            <q-item v-bind="itemProps">
              <q-item-section>
                <q-item-label>{{ opt.label }}</q-item-label>
                <q-item-label caption>{{ opt.caption }}</q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-badge :color="statusColor('project', opt.status)" :label="titleCase(opt.status)" />
              </q-item-section>
            </q-item>
          </template>
          <template #after-options>
            <q-separator />
            <q-item clickable @click="ui.openNewProject()">
              <q-item-section avatar><q-icon name="add" color="primary" /></q-item-section>
              <q-item-section class="text-primary">New project</q-item-section>
            </q-item>
          </template>
          <template #no-option>
            <q-item clickable @click="ui.openNewProject()">
              <q-item-section avatar><q-icon name="add" color="primary" /></q-item-section>
              <q-item-section class="text-primary">New project</q-item-section>
            </q-item>
          </template>
        </q-select>

        <q-space />

        <q-btn
          v-if="headset && projects.currentProjectId"
          flat
          no-caps
          icon="view_in_ar"
          :label="$q.screen.gt.sm ? 'Load to VR' : undefined"
          class="q-mr-xs"
          @click="loadToVr(projects.currentProjectId, projects.currentProject?.name)"
        />

        <q-btn
          unelevated
          no-caps
          color="primary"
          icon="auto_awesome"
          :label="$q.screen.gt.xs ? 'Copilot' : undefined"
          class="q-mr-xs"
          @click="copilot.toggleOpen()"
        />

        <!-- What needs attention -->
        <q-btn flat round dense icon="notifications_none" aria-label="Needs attention">
          <q-badge v-if="attentionCount" color="negative" floating rounded>{{ attentionCount }}</q-badge>
          <q-menu anchor="bottom right" self="top right" :offset="[0, 6]">
            <q-list style="width: 340px; max-width: 92vw" separator>
              <q-item-label header class="text-weight-bold">Needs attention</q-item-label>
              <q-item v-for="(item, i) in attentionItems" :key="i" clickable v-close-popup @click="$router.push(item.route)">
                <q-item-section avatar>
                  <q-icon :name="item.icon" :color="statusColor('severity', item.severity)" />
                </q-item-section>
                <q-item-section>
                  <q-item-label class="ellipsis-2">{{ item.title }}</q-item-label>
                  <q-item-label v-if="item.detail" caption class="ellipsis">{{ item.detail }}</q-item-label>
                </q-item-section>
              </q-item>
              <q-item v-if="!attentionItems.length">
                <q-item-section class="text-muted text-body2">Nothing needs you right now.</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>

        <q-btn flat round dense :icon="$q.dark.isActive ? 'light_mode' : 'dark_mode'" class="q-ml-xs" aria-label="Toggle dark mode" @click="toggleDark">
          <q-tooltip>{{ $q.dark.isActive ? 'Light mode' : 'Dark mode' }}</q-tooltip>
        </q-btn>

        <q-btn flat round dense class="q-ml-xs" aria-label="Account">
          <q-avatar size="32px" color="primary" text-color="white" font-size="13px">{{ initials(auth.fullName || 'User') }}</q-avatar>
          <q-menu anchor="bottom right" self="top right">
            <q-list style="min-width: 220px">
              <q-item>
                <q-item-section>
                  <q-item-label class="text-weight-bold">{{ auth.fullName || 'Signed in' }}</q-item-label>
                  <q-item-label caption>{{ auth.user?.email || (devMode ? 'Development mode' : '') }}</q-item-label>
                </q-item-section>
              </q-item>
              <q-separator />
              <q-item v-if="!devMode" clickable v-close-popup @click="logout">
                <q-item-section avatar><q-icon name="logout" /></q-item-section>
                <q-item-section>Sign out</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
      </q-toolbar>
    </q-header>

    <q-drawer v-model="leftDrawerOpen" show-if-above bordered :width="252" class="app-drawer">
      <div class="column fit no-wrap">
        <q-scroll-area class="col">
          <q-list class="nav q-py-sm">
            <template v-for="section in navigation" :key="section.title">
              <q-item-label header class="nav-header">{{ section.title }}</q-item-label>
              <q-item
                v-for="item in section.items"
                :key="item.to"
                clickable
                :to="item.to"
                :exact="item.to === '/'"
                active-class="nav-active"
                class="nav-item"
              >
                <q-item-section avatar class="nav-icon"><q-icon :name="item.icon" size="20px" /></q-item-section>
                <q-item-section>{{ item.label }}</q-item-section>
                <q-item-section v-if="item.badge" side>
                  <q-badge :color="item.badgeColor ?? 'primary'" :label="item.badge" rounded />
                </q-item-section>
              </q-item>
            </template>
          </q-list>
        </q-scroll-area>
        <q-separator />
        <div class="q-px-md q-py-sm text-caption text-muted row items-center no-wrap">
          <q-icon name="circle" size="9px" :color="websocketService.connected.value ? 'positive' : 'grey-5'" class="q-mr-xs" />
          <span class="ellipsis">{{ websocketService.connected.value ? 'Live updates on' : 'Live updates off' }} · {{ serverHost }}</span>
        </div>
      </div>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>

    <ai-copilot-widget />
    <new-project-dialog />
  </q-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { useProjectsStore } from 'src/stores/projects'
import { useAuthStore } from 'src/stores/auth'
import { useCrmStore } from 'src/stores/crm'
import { useAiCopilotStore } from 'src/stores/aiCopilot'
import { useUiStore } from 'src/stores/ui'
import { websocketService } from 'src/services/websocket'
import { inHeadset, useLoadToVr } from 'src/composables/useLoadToVr'
import { initials, titleCase } from 'src/utils/format'
import { statusColor } from 'src/utils/status'
import AiCopilotWidget from 'src/components/ai/AiCopilotWidget.vue'
import NewProjectDialog from 'src/components/projects/NewProjectDialog.vue'

const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const projects = useProjectsStore()
const auth = useAuthStore()
const crm = useCrmStore()
const copilot = useAiCopilotStore()
const ui = useUiStore()
const loadToVr = useLoadToVr()

const leftDrawerOpen = ref(false)
const headset = inHeadset()
const devMode = import.meta.env.VITE_DEV_MODE === 'true'
const serverHost = (() => {
  try {
    return new URL(String(import.meta.env.VITE_API_BASE_URL)).host
  } catch {
    return 'local API'
  }
})()

// Light/dark: the user's choice is remembered per browser; until then, the system's.
const THEME_KEY = 'dashboard.theme'
try {
  const saved = localStorage.getItem(THEME_KEY)
  if (saved === 'dark' || saved === 'light') $q.dark.set(saved === 'dark')
} catch {
  // storage unavailable: follow the system
}
const toggleDark = () => {
  $q.dark.toggle()
  try {
    localStorage.setItem(THEME_KEY, $q.dark.isActive ? 'dark' : 'light')
  } catch {
    // not remembered; fine
  }
}

const projectOptions = computed(() =>
  projects.projects.map(p => ({
    value: p.id,
    label: p.name,
    caption: p.address || p.description?.slice(0, 60) || `Project #${p.id}`,
    status: p.status
  }))
)

const attentionItems = computed(() => {
  const items = (projects.overview?.attention ?? []).map(a => ({
    ...a,
    icon: a.kind.startsWith('task') ? 'event_busy' : a.kind.startsWith('inspection') ? 'fact_check'
      : a.kind.startsWith('permit') ? 'gavel' : 'request_quote'
  }))
  for (const f of crm.pipeline?.follow_ups_due ?? []) {
    items.push({
      kind: 'follow_up', severity: 'medium', title: `Follow up with ${f.name}`,
      detail: f.next_action ?? '', route: `/crm?client=${f.id}`, icon: 'person_search'
    })
  }
  return items
})
const attentionCount = computed(() => attentionItems.value.length)

const pendingCos = computed(() =>
  (projects.overview?.attention ?? []).filter(a => a.kind === 'change_order_pending').length
)

const punchDue = computed(() => projects.overview?.punch_list?.overdue ?? 0)

const navigation = computed(() => [
  {
    title: 'Workspace',
    items: [
      { to: '/', label: 'Overview', icon: 'space_dashboard' },
      { to: '/design', label: 'Design studio', icon: 'architecture' }
    ]
  },
  {
    title: 'Clients',
    items: [
      {
        to: '/crm', label: 'Client CRM', icon: 'groups',
        badge: crm.followUpsDue ? String(crm.followUpsDue) : undefined, badgeColor: 'warning'
      }
    ]
  },
  {
    title: 'Project controls',
    items: [
      { to: '/timeline', label: 'Schedule', icon: 'calendar_month' },
      {
        to: '/budget', label: 'Budget & cost', icon: 'account_balance_wallet',
        badge: pendingCos.value ? String(pendingCos.value) : undefined, badgeColor: 'warning'
      },
      { to: '/materials', label: 'Materials (BOM)', icon: 'inventory_2' },
      { to: '/resources', label: 'Crew & equipment', icon: 'engineering' },
      { to: '/compliance', label: 'Permits & inspections', icon: 'verified' },
      {
        to: '/punch-list', label: 'Punch list', icon: 'checklist',
        badge: punchDue.value ? String(punchDue.value) : undefined, badgeColor: 'negative'
      }
    ]
  },
  {
    title: '3D libraries',
    items: [
      { to: '/plants', label: 'Plant models', icon: 'yard' },
      { to: '/furniture', label: 'Furniture models', icon: 'chair' }
    ]
  }
])

const onSelectProject = (id: number) => {
  projects.selectProject(id)
}

const refreshOverview = () => {
  projects.fetchOverview().catch(err => console.warn('[MainLayout] overview failed', err))
}

// The selected project: overview for the bell, live updates for its room.
watch(
  () => projects.currentProjectId,
  async id => {
    if (!id) return
    refreshOverview()
    if (websocketService.connected.value) websocketService.subscribeToProject(id)
  }
)
// Pages change things; the bell catches up when you move on.
watch(() => route.path, () => {
  if (projects.currentProjectId) refreshOverview()
})

const logout = async () => {
  try {
    await auth.logout()
  } finally {
    router.push('/login')
  }
}

onMounted(async () => {
  try {
    await projects.fetchProjects()
  } catch {
    $q.notify({ type: 'negative', message: 'Could not reach the backend', caption: String(import.meta.env.VITE_API_BASE_URL) })
  }
  crm.load().catch(err => console.warn('[MainLayout] CRM failed to load', err))
  websocketService.connect().catch(err => console.warn('[MainLayout] WebSocket connection failed:', err))
})

watch(() => auth.isAuthenticated, isAuthenticated => {
  if (!isAuthenticated && !devMode) router.push('/login')
})
</script>

<style lang="sass" scoped>
.app-header
  background: var(--app-surface)
  color: var(--app-text)
  border-color: var(--app-border)

.brand
  color: inherit
  text-decoration: none

.brand-mark
  border-radius: 10px

.leading-tight
  line-height: 1.15

.project-switcher
  width: 300px
  max-width: 46vw

.app-drawer
  background: var(--app-surface)

.nav-header
  font-size: 0.7rem
  font-weight: 700
  letter-spacing: 0.08em
  text-transform: uppercase
  color: var(--app-muted)
  padding: 14px 20px 6px

.nav-item
  margin: 1px 10px
  border-radius: 8px
  min-height: 38px
  color: var(--app-text)

.nav-icon
  min-width: 34px
  color: var(--app-muted)

.nav-active
  background: var(--app-accent-soft)
  color: var(--q-primary)
  font-weight: 600
  .nav-icon
    color: var(--q-primary)
</style>

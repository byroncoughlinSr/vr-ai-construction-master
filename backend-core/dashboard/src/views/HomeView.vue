<template>
  <q-page class="q-pa-md">
    <div class="page-container">
      <no-project v-if="!project" what="overview" />

      <template v-else>
        <page-header
          eyebrow="Project overview"
          :title="project.name"
          :subtitle="[project.address, titleCase(project.status)].filter(Boolean).join(' · ')"
          icon="home_work"
        >
          <template #actions>
            <q-btn outline no-caps color="primary" icon="auto_awesome" label="Brief me" @click="briefMe" />
            <q-btn outline no-caps color="primary" icon="edit" label="Edit project" @click="editOpen = true" />
            <q-btn unelevated no-caps color="primary" icon="architecture" label="Design studio" to="/design" />
            <q-btn
              v-if="headset"
              unelevated
              no-caps
              color="secondary"
              icon="view_in_ar"
              label="Load to VR"
              @click="loadToVr(project.id, project.name)"
            />
          </template>
        </page-header>

        <q-banner v-if="loadError" rounded class="banner-error q-mb-md">
          {{ loadError }}
          <template #action><q-btn flat no-caps label="Retry" @click="reload" /></template>
        </q-banner>

        <!-- KPIs -->
        <div class="row q-col-gutter-md q-mb-md">
          <div class="col-12 col-sm-6 col-md-3">
            <kpi-metric-card
              title="Schedule progress"
              :value="overview ? formatPercent(overview.schedule.progress) : '—'"
              icon="event_available"
              tone="primary"
              :progress="overview?.schedule.progress ?? null"
              :caption="scheduleCaption"
              hint="Earned from task status: half a task's duration when it starts, the rest when it is completed."
              to="/timeline"
            />
          </div>
          <div class="col-12 col-sm-6 col-md-3">
            <kpi-metric-card
              title="Cost performance (CPI)"
              :value="formatIndex(budget?.cpi)"
              icon="speed"
              :tone="indexColor(budget?.cpi)"
              :value-color="budget?.cpi != null ? indexColor(budget.cpi) : undefined"
              :caption="budget?.cpi != null
                ? `Earned ${formatCompactCurrency(budget.earned_value)} for ${formatCompactCurrency(budget.actual_cost)} spent`
                : 'Log expenses to measure it'"
              hint="Earned value ÷ actual cost. Above 1.00 the work is costing less than budgeted."
              to="/budget"
            />
          </div>
          <div class="col-12 col-sm-6 col-md-3">
            <kpi-metric-card
              title="Spent of budget"
              :value="budget ? formatCompactCurrency(budget.actual_cost) : '—'"
              icon="account_balance_wallet"
              tone="secondary"
              :progress="budget?.percent_spent ?? null"
              :caption="budget ? `of ${formatCompactCurrency(budget.bac)} (${formatPercent(budget.percent_spent)})` : undefined"
              to="/budget"
            />
          </div>
          <div class="col-12 col-sm-6 col-md-3">
            <kpi-metric-card
              title="Needs attention"
              :value="overview?.attention.length ?? '—'"
              icon="priority_high"
              :tone="overview?.attention.some(a => a.severity === 'high') ? 'negative' : 'warning'"
              :caption="overview ? `${overview.schedule.tasks.late} late tasks · ${overview.compliance.inspections_upcoming} inspections ahead` : undefined"
              to="/timeline"
            />
          </div>
        </div>

        <div class="row q-col-gutter-md">
          <!-- Left column -->
          <div class="col-12 col-md-8 column q-gutter-y-md">
            <!-- Floor plan -->
            <q-card flat class="app-card">
              <div class="app-card-header">
                <div class="app-card-title">House design</div>
                <q-btn flat dense no-caps color="primary" icon-right="arrow_forward" label="Open studio" to="/design" />
              </div>
              <q-card-section v-if="plan" class="row q-col-gutter-md">
                <div v-if="planImage" class="col-12 col-sm-5">
                  <q-img :src="planImage" :ratio="4 / 3" class="rounded-12 border-app" alt="Accepted rendering of the house" />
                </div>
                <div class="col">
                  <div class="text-h6 text-weight-bold">{{ plan.name }}</div>
                  <div class="text-caption text-muted q-mb-sm">
                    Version {{ plan.version }} · {{ plan.rooms.length }} rooms
                    <template v-if="plan.footprint_ft"> · {{ plan.footprint_ft[0] }} × {{ plan.footprint_ft[1] }} ft footprint</template>
                    · {{ formatDate(plan.created_at) }}
                  </div>
                  <div class="row q-gutter-xs q-mb-sm">
                    <q-chip v-for="room in plan.rooms.slice(0, 12)" :key="room" dense square class="bg-surface-2 q-ma-none">{{ room }}</q-chip>
                    <q-chip v-if="plan.rooms.length > 12" dense square class="q-ma-none">+{{ plan.rooms.length - 12 }}</q-chip>
                  </div>
                  <div v-if="plan.change_note" class="text-body2 text-muted ellipsis-2">
                    <q-icon name="history" size="16px" class="q-mr-xs" />{{ plan.change_note }}
                  </div>
                </div>
              </q-card-section>
              <empty-state
                v-else
                dense
                icon="architecture"
                title="No floor plan yet"
                message="Describe the house in the headset (hold A), or create the project with AI to get a plan."
              />
            </q-card>

            <!-- Phases -->
            <q-card flat class="app-card">
              <div class="app-card-header">
                <div class="app-card-title">Phases</div>
                <q-btn flat dense no-caps color="primary" icon-right="arrow_forward" label="Schedule" to="/timeline" />
              </div>
              <q-list v-if="schedule.phases.length" class="q-pb-sm">
                <q-item v-for="phase in schedule.phases" :key="phase.id" class="q-py-xs">
                  <q-item-section avatar style="min-width: 40px">
                    <q-circular-progress
                      :value="phase.progress"
                      size="34px"
                      :thickness="0.18"
                      :color="statusColor('phase', phase.status)"
                      track-color="grey-3"
                      show-value
                      font-size="9px"
                    >{{ Math.round(phase.progress) }}</q-circular-progress>
                  </q-item-section>
                  <q-item-section>
                    <q-item-label class="text-weight-medium">{{ phase.name }}</q-item-label>
                    <q-item-label caption>
                      {{ phase.tasks.filter(t => t.status === 'completed').length }}/{{ phase.tasks.length }} tasks
                      <template v-if="phase.planned_start"> · {{ formatShortDate(phase.planned_start) }} – {{ formatShortDate(phase.planned_end) }}</template>
                    </q-item-label>
                  </q-item-section>
                  <q-item-section side>
                    <q-badge v-if="phase.late" color="negative" label="Late" />
                    <q-badge v-else :color="statusColor('phase', phase.status)" :label="titleCase(phase.status)" outline />
                  </q-item-section>
                </q-item>
              </q-list>
              <empty-state v-else-if="!schedule.loading" dense icon="calendar_month" title="No phases yet" message="Phases and tasks come with an AI-generated plan, or add them on the Schedule page." />
            </q-card>

            <!-- Cost by phase -->
            <q-card v-if="budget && budget.by_phase.some(p => p.budgeted || p.actual)" flat class="app-card">
              <div class="app-card-header">
                <div class="app-card-title">Cost by phase</div>
                <q-btn flat dense no-caps color="primary" icon-right="table_rows" label="As a table" to="/budget" />
              </div>
              <q-card-section class="q-pt-none">
                <bar-chart
                  :labels="budget.by_phase.map(p => p.name)"
                  :series="[
                    { label: 'Budgeted', data: budget.by_phase.map(p => p.budgeted) },
                    { label: 'Earned', data: budget.by_phase.map(p => p.earned) },
                    { label: 'Actual', data: budget.by_phase.map(p => p.actual) }
                  ]"
                  :height="Math.max(180, budget.by_phase.length * 46 + 40)"
                  aria-label="Budgeted, earned and actual cost for each phase"
                />
              </q-card-section>
            </q-card>
          </div>

          <!-- Right column -->
          <div class="col-12 col-md-4 column q-gutter-y-md">
            <q-card flat class="app-card">
              <div class="app-card-header">
                <div class="app-card-title">Needs attention</div>
              </div>
              <q-list v-if="overview?.attention.length" separator>
                <q-item v-for="(item, i) in overview.attention.slice(0, 8)" :key="i" clickable :to="item.route">
                  <q-item-section avatar style="min-width: 32px">
                    <q-icon name="circle" size="10px" :color="statusColor('severity', item.severity)" />
                  </q-item-section>
                  <q-item-section>
                    <q-item-label class="ellipsis-2">{{ item.title }}</q-item-label>
                    <q-item-label v-if="item.detail" caption class="ellipsis">{{ item.detail }}</q-item-label>
                  </q-item-section>
                </q-item>
              </q-list>
              <empty-state v-else dense icon="task_alt" title="All clear" message="No late tasks, failed inspections, expiring permits or pending change orders." />
            </q-card>

            <q-card flat class="app-card">
              <div class="app-card-header">
                <div class="app-card-title">Client</div>
                <q-btn flat dense no-caps color="primary" icon-right="arrow_forward" label="CRM" to="/crm" />
              </div>
              <template v-if="clients.length">
                <q-item v-for="c in clients" :key="c.id" clickable :to="{ path: '/crm', query: { client: String(c.id) } }">
                  <q-item-section avatar>
                    <q-avatar color="primary" text-color="white" size="38px" font-size="14px">{{ initials(c.name) }}</q-avatar>
                  </q-item-section>
                  <q-item-section>
                    <q-item-label class="text-weight-medium">{{ c.name }}</q-item-label>
                    <q-item-label caption>{{ c.stage_label }}<template v-if="c.next_follow_up_at"> · follow up {{ formatRelativeDay(c.next_follow_up_at) }}</template></q-item-label>
                  </q-item-section>
                  <q-item-section side>
                    <q-badge v-if="c.sentiment" :color="SENTIMENT_COLORS[c.sentiment]" :label="titleCase(c.sentiment)" />
                  </q-item-section>
                </q-item>
                <q-card-section v-if="clients[0].ai_summary" class="q-pt-none text-body2 text-muted clamp-4">
                  <q-icon name="auto_awesome" color="primary" size="16px" class="q-mr-xs" />{{ clients[0].ai_summary }}
                </q-card-section>
              </template>
              <empty-state v-else dense icon="person_add" title="No client linked" message="Link the homeowner from their CRM record (Start project / link project).">
                <q-btn outline no-caps color="primary" label="Open CRM" to="/crm" />
              </empty-state>
            </q-card>

            <q-card flat class="app-card">
              <div class="app-card-header">
                <div class="app-card-title">Sales pipeline</div>
                <q-btn flat dense no-caps color="primary" icon-right="arrow_forward" label="Pipeline" to="/crm" />
              </div>
              <q-card-section v-if="crm.pipeline" class="row q-col-gutter-sm q-pt-xs">
                <div class="col-6">
                  <div class="text-caption text-muted">Open leads</div>
                  <div class="text-h6 text-weight-bold tabular">{{ crm.pipeline.open_count }}</div>
                </div>
                <div class="col-6">
                  <div class="text-caption text-muted">Weighted forecast</div>
                  <div class="text-h6 text-weight-bold tabular">{{ formatCompactCurrency(crm.pipeline.weighted_value) }}</div>
                </div>
                <div class="col-12 text-caption" :class="crm.pipeline.follow_ups_due.length ? 'text-warning' : 'text-muted'">
                  <q-icon name="schedule" size="15px" class="q-mr-xs" />
                  {{ crm.pipeline.follow_ups_due.length }} follow-up{{ crm.pipeline.follow_ups_due.length === 1 ? '' : 's' }} due
                </div>
              </q-card-section>
            </q-card>
          </div>
        </div>

        <project-edit-dialog v-model="editOpen" :project-id="project.id" />
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useProjectsStore } from 'src/stores/projects'
import { useScheduleStore } from 'src/stores/schedule'
import { useCrmStore, SENTIMENT_COLORS } from 'src/stores/crm'
import { useAiCopilotStore } from 'src/stores/aiCopilot'
import { useProjectData } from 'src/composables/useProjectData'
import { inHeadset, useLoadToVr } from 'src/composables/useLoadToVr'
import { apiClient } from 'src/services/api'
import { errorMessage } from 'src/utils/errors'
import {
  formatCompactCurrency, formatDate, formatIndex, formatPercent, formatRelativeDay, formatShortDate, initials, titleCase
} from 'src/utils/format'
import { indexColor, statusColor } from 'src/utils/status'
import PageHeader from 'src/components/common/PageHeader.vue'
import EmptyState from 'src/components/common/EmptyState.vue'
import NoProject from 'src/components/common/NoProject.vue'
import KpiMetricCard from 'src/components/dashboard/KpiMetricCard.vue'
import BarChart from 'src/components/charts/BarChart.vue'
import ProjectEditDialog from 'src/components/projects/ProjectEditDialog.vue'

const projects = useProjectsStore()
const schedule = useScheduleStore()
const crm = useCrmStore()
const copilot = useAiCopilotStore()
const loadToVr = useLoadToVr()
const headset = inHeadset()

const editOpen = ref(false)
const loadError = ref<string | null>(null)

const load = async (projectId: number) => {
  loadError.value = null
  try {
    await Promise.all([projects.fetchOverview(projectId), schedule.load(projectId)])
  } catch (err) {
    loadError.value = errorMessage(err, 'Could not load the project')
  }
}
const { project } = useProjectData(load, () => schedule.clear())
const reload = () => projects.currentProjectId && load(projects.currentProjectId)

const overview = computed(() => projects.overview)
const budget = computed(() => overview.value?.budget ?? null)
const plan = computed(() => overview.value?.floor_plan ?? null)
const clients = computed(() => crm.clientsForProject(projects.currentProjectId))

// Images are served by the backend outside /api/v1.
const planImage = computed(() => {
  const url = plan.value?.image_url
  if (!url) return null
  if (/^https?:/.test(url)) return url
  const base = String(apiClient.client.defaults?.baseURL ?? '').replace(/\/api\/v1\/?$/, '')
  return `${base}${url.startsWith('/') ? '' : '/'}${url}`
})

const scheduleCaption = computed(() => {
  const s = overview.value?.schedule
  if (!s) return undefined
  if (!s.phase_count) return 'No phases yet'
  const phase = s.current_phase ? s.current_phase.name : 'All phases complete'
  return s.baselined ? `${phase} · finish ${formatShortDate(s.planned_finish)}` : `${phase} · not baselined`
})

const briefMe = () => {
  copilot.setOpen(true)
  copilot.ask('Brief me on this project: where it stands on schedule and cost, what needs attention, and what I should do next.', {
    projectId: projects.currentProjectId
  })
}
</script>

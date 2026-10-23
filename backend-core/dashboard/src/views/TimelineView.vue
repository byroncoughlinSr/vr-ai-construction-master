<template>
  <q-page class="q-pa-md">
    <div class="page-container">
      <no-project v-if="!project" what="schedule" />

      <template v-else>
        <page-header eyebrow="Project controls" title="Schedule" :subtitle="`${project.name} — phases, tasks and earned progress`" icon="calendar_month">
          <template #actions>
            <q-btn-toggle
              v-model="view"
              unelevated
              no-caps
              toggle-color="primary"
              color="grey-3"
              text-color="grey-9"
              :options="[{ value: 'phases', icon: 'view_agenda', label: 'Phases' }, { value: 'list', icon: 'format_list_bulleted', label: 'All tasks' }]"
            />
            <q-btn outline no-caps color="primary" icon="event_repeat" :label="s?.baselined ? 'Re-baseline' : 'Baseline'" @click="baselineOpen = true" />
            <q-btn unelevated no-caps color="primary" icon="add" label="Phase" @click="addPhase" />
          </template>
        </page-header>

        <q-banner v-if="schedule.error" rounded class="banner-error q-mb-md">
          {{ schedule.error }}
          <template #action><q-btn flat no-caps label="Retry" @click="schedule.reload()" /></template>
        </q-banner>

        <template v-if="s">
          <div class="row q-col-gutter-md q-mb-md">
            <div class="col-6 col-md-3">
              <kpi-metric-card title="Progress" :value="formatPercent(s.progress)" icon="flag" tone="primary" :progress="s.progress"
                :caption="s.current_phase ? `Now: ${s.current_phase.name}` : s.phase_count ? 'All phases complete' : 'No phases'"
                hint="Earned with the 50/50 rule, weighted by task duration." />
            </div>
            <div class="col-6 col-md-3">
              <kpi-metric-card title="Tasks done" :value="`${s.tasks.completed}/${s.tasks.total}`" icon="task_alt" tone="positive"
                :caption="`${s.tasks.in_progress} in progress · ${s.tasks.blocked} blocked`" />
            </div>
            <div class="col-6 col-md-3">
              <kpi-metric-card title="Late tasks" :value="s.tasks.late" icon="event_busy" :tone="s.tasks.late ? 'negative' : 'blue-grey-5'"
                :caption="s.baselined ? 'Past their planned finish' : 'Baseline to track lateness'" />
            </div>
            <div class="col-6 col-md-3">
              <kpi-metric-card title="Planned finish" :value="s.baselined ? formatShortDate(s.planned_finish) : '—'" icon="sports_score" tone="secondary"
                :caption="s.baselined ? `Started ${formatDate(s.planned_start)} · ${Math.round(s.total_days)} days of work` : `${Math.round(s.total_days)} days of work, not dated yet`" />
            </div>
          </div>

          <q-banner v-if="!s.baselined && s.phase_count" rounded class="bg-surface-2 border-app q-mb-md">
            <template #avatar><q-icon name="event_repeat" color="primary" /></template>
            The schedule has durations but no dates yet. Baseline it from a start date to plan every task, see what is late,
            and get planned value (SPI) on the budget.
            <template #action><q-btn flat no-caps color="primary" label="Baseline now" @click="baselineOpen = true" /></template>
          </q-banner>

          <q-card v-if="s.phase_count" flat class="app-card q-mb-md">
            <div class="app-card-header"><div class="app-card-title">Timeline</div></div>
            <q-card-section class="q-pt-none">
              <gantt-chart :phases="schedule.phases" :baselined="s.baselined" />
            </q-card-section>
          </q-card>

          <!-- Phases -->
          <template v-if="view === 'phases'">
            <q-card v-for="phase in schedule.phases" :key="phase.id" flat class="app-card q-mb-sm">
              <q-expansion-item :default-opened="phase.status === 'in_progress'" header-class="q-py-sm">
                <template #header>
                  <q-item-section avatar style="min-width: 44px">
                    <q-circular-progress :value="phase.progress" size="36px" :thickness="0.18" :color="statusColor('phase', phase.status)" track-color="grey-3" show-value font-size="9px">
                      {{ Math.round(phase.progress) }}
                    </q-circular-progress>
                  </q-item-section>
                  <q-item-section>
                    <q-item-label class="text-weight-medium">{{ phase.phase_order }}. {{ phase.name }}</q-item-label>
                    <q-item-label caption>
                      {{ phase.tasks.filter(t => t.status === 'completed').length }}/{{ phase.tasks.length }} tasks · {{ Math.round(phase.duration_days) }} days
                      <template v-if="phase.planned_start"> · {{ formatShortDate(phase.planned_start) }} – {{ formatShortDate(phase.planned_end) }}</template>
                      · {{ formatCompactCurrency(phase.budgeted_cost) }} budget
                    </q-item-label>
                  </q-item-section>
                  <q-item-section side>
                    <div class="row items-center q-gutter-xs">
                      <q-badge v-if="phase.late" color="negative" label="Late" />
                      <q-badge :color="statusColor('phase', phase.status)" :label="titleCase(phase.status)" />
                    </div>
                  </q-item-section>
                </template>

                <q-separator />
                <div v-if="phase.description" class="q-px-md q-pt-sm text-body2 text-muted">{{ phase.description }}</div>
                <q-list separator>
                  <q-item v-for="task in phase.tasks" :key="task.id" class="q-py-xs">
                    <q-item-section avatar style="min-width: 36px">
                      <q-checkbox
                        :model-value="task.status === 'completed'"
                        dense
                        :aria-label="`Mark ${task.name} complete`"
                        @update:model-value="done => setStatus(task, done ? 'completed' : 'in_progress')"
                      />
                    </q-item-section>
                    <q-item-section>
                      <q-item-label :class="{ 'text-strike text-muted': task.status === 'completed' }">{{ task.name }}</q-item-label>
                      <q-item-label caption>
                        {{ task.duration_days }} day{{ task.duration_days === 1 ? '' : 's' }}
                        <template v-if="task.planned_start"> · {{ formatShortDate(task.planned_start) }} – {{ formatShortDate(task.planned_end) }}</template>
                        <template v-if="task.budgeted_cost"> · {{ formatCurrency(task.budgeted_cost) }}</template>
                        <template v-if="task.requires_inspection"> · <q-icon name="fact_check" size="13px" /> inspection</template>
                      </q-item-label>
                    </q-item-section>
                    <q-item-section side class="row no-wrap items-center">
                      <div class="row items-center no-wrap q-gutter-xs">
                        <q-badge v-if="task.late" color="negative" label="Late" />
                        <q-badge :color="statusColor('priority', task.priority)" :label="titleCase(task.priority)" outline />
                        <q-btn-dropdown dense flat no-caps size="sm" :color="statusColor('task', task.status)" :label="statusLabel(task.status)">
                          <q-list dense>
                            <q-item v-for="o in TASK_STATUS_OPTIONS" :key="o.value" clickable v-close-popup @click="setStatus(task, o.value as TaskStatus)">
                              <q-item-section>{{ o.label }}</q-item-section>
                            </q-item>
                          </q-list>
                        </q-btn-dropdown>
                        <q-btn flat round dense size="sm" icon="edit" @click="editTask(phase, task)" />
                      </div>
                    </q-item-section>
                  </q-item>
                </q-list>
                <div class="q-pa-sm">
                  <q-btn flat dense no-caps color="primary" icon="add" label="Add task" @click="editTask(phase, null)" />
                </div>
              </q-expansion-item>
            </q-card>
            <q-card v-if="!schedule.phases.length && !schedule.loading" flat class="app-card">
              <empty-state icon="calendar_month" title="No phases yet" message="An AI-generated project comes with phases and tasks. You can also add them here.">
                <q-btn unelevated no-caps color="primary" icon="add" label="Add a phase" @click="addPhase" />
              </empty-state>
            </q-card>
          </template>

          <!-- All tasks -->
          <q-card v-else flat class="app-card">
            <q-card-section class="row q-col-gutter-sm items-center q-pb-none">
              <div class="col-12 col-sm-4">
                <q-select v-model="statusFilter" outlined dense emit-value map-options clearable :options="TASK_STATUS_OPTIONS" label="Status" />
              </div>
              <div class="col-auto"><q-toggle v-model="lateOnly" label="Late only" /></div>
            </q-card-section>
            <q-table :rows="filteredTasks" :columns="columns" row-key="id" flat :pagination="{ rowsPerPage: 25 }">
              <template #body-cell-name="props">
                <q-td :props="props">
                  <div class="text-weight-medium">{{ props.row.name }}</div>
                  <div class="text-caption text-muted">{{ props.row.phase_name }}</div>
                </q-td>
              </template>
              <template #body-cell-status="props">
                <q-td :props="props">
                  <q-badge v-if="props.row.late" color="negative" label="Late" class="q-mr-xs" />
                  <q-badge :color="statusColor('task', props.row.status)" :label="statusLabel(props.row.status)" />
                </q-td>
              </template>
              <template #body-cell-priority="props">
                <q-td :props="props"><q-badge :color="statusColor('priority', props.row.priority)" :label="titleCase(props.row.priority)" outline /></q-td>
              </template>
              <template #body-cell-actions="props">
                <q-td :props="props" auto-width>
                  <q-btn flat round dense size="sm" icon="edit" @click="editTask(schedule.phases.find(p => p.id === props.row.phase_id)!, props.row)" />
                </q-td>
              </template>
            </q-table>
          </q-card>
        </template>

        <div v-else-if="schedule.loading" class="flex flex-center q-pa-xl"><q-spinner size="40px" color="primary" /></div>

        <!-- Baseline -->
        <q-dialog v-model="baselineOpen">
          <q-card class="app-card" style="width: 420px; max-width: 96vw">
            <q-card-section>
              <div class="text-h6 text-weight-bold">Baseline the schedule</div>
              <div class="text-body2 text-muted q-mt-xs">
                Lays every phase end to end from the start date, each phase's tasks one after another by their durations
                (calendar days). {{ s?.baselined ? 'This replaces the planned dates now in the schedule.' : '' }}
              </div>
            </q-card-section>
            <q-card-section class="q-pt-none">
              <q-input v-model="baselineStart" outlined dense type="date" stack-label label="Start date" />
            </q-card-section>
            <q-card-actions align="right" class="q-px-md q-pb-md">
              <q-btn flat no-caps label="Cancel" v-close-popup />
              <q-btn unelevated no-caps color="primary" label="Baseline" :disable="!baselineStart" :loading="baselining" @click="doBaseline" />
            </q-card-actions>
          </q-card>
        </q-dialog>

        <task-dialog v-model="taskOpen" :phase-id="taskPhase?.id ?? null" :phase-name="taskPhase?.name" :task="taskEditing" />
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useScheduleStore } from 'src/stores/schedule'
import { useProjectData } from 'src/composables/useProjectData'
import type { SchedulePhase, ScheduleTask, TaskStatus } from 'src/types/controls'
import { errorMessage } from 'src/utils/errors'
import { formatCompactCurrency, formatCurrency, formatDate, formatPercent, formatShortDate, titleCase, todayIso } from 'src/utils/format'
import { statusColor, TASK_STATUS_OPTIONS } from 'src/utils/status'
import PageHeader from 'src/components/common/PageHeader.vue'
import EmptyState from 'src/components/common/EmptyState.vue'
import NoProject from 'src/components/common/NoProject.vue'
import KpiMetricCard from 'src/components/dashboard/KpiMetricCard.vue'
import GanttChart from 'src/components/schedule/GanttChart.vue'
import TaskDialog from 'src/components/schedule/TaskDialog.vue'

const $q = useQuasar()
const schedule = useScheduleStore()
const { project } = useProjectData(id => schedule.load(id).catch(() => undefined), () => schedule.clear())

const s = computed(() => schedule.schedule)
const view = ref<'phases' | 'list'>('phases')
const statusFilter = ref<TaskStatus | null>(null)
const lateOnly = ref(false)

const baselineOpen = ref(false)
const baselineStart = ref(todayIso())
const baselining = ref(false)

const taskOpen = ref(false)
const taskPhase = ref<SchedulePhase | null>(null)
const taskEditing = ref<ScheduleTask | null>(null)

const statusLabel = (status: string) => TASK_STATUS_OPTIONS.find(o => o.value === status)?.label ?? titleCase(status)

const filteredTasks = computed(() =>
  schedule.tasks.filter(t => (!statusFilter.value || t.status === statusFilter.value) && (!lateOnly.value || t.late))
)

const columns = [
  { name: 'name', label: 'Task', field: 'name', align: 'left' as const, sortable: true },
  { name: 'status', label: 'Status', field: 'status', align: 'left' as const, sortable: true },
  { name: 'priority', label: 'Priority', field: (t: ScheduleTask) => ['low', 'medium', 'high', 'critical'].indexOf(t.priority), align: 'left' as const, sortable: true },
  { name: 'duration_days', label: 'Days', field: 'duration_days', align: 'right' as const, sortable: true },
  { name: 'planned_start', label: 'Start', field: 'planned_start', align: 'left' as const, sortable: true, format: formatShortDate },
  { name: 'planned_end', label: 'Finish', field: 'planned_end', align: 'left' as const, sortable: true, format: formatShortDate },
  { name: 'budgeted_cost', label: 'Budget', field: 'budgeted_cost', align: 'right' as const, sortable: true, format: formatCurrency },
  { name: 'actions', label: '', field: 'id', align: 'right' as const }
]

const fail = (err: unknown, fallback: string) => $q.notify({ type: 'negative', message: errorMessage(err, fallback) })

const setStatus = async (task: ScheduleTask, status: TaskStatus) => {
  if (task.status === status) return
  try {
    await schedule.updateTask(task.id, { status })
  } catch (err) {
    fail(err, 'Could not update the task')
  }
}

const editTask = (phase: SchedulePhase, task: ScheduleTask | null) => {
  taskPhase.value = phase
  taskEditing.value = task
  taskOpen.value = true
}

const addPhase = () => {
  $q.dialog({
    title: 'New phase',
    message: 'Added after the last phase.',
    prompt: { model: '', type: 'text', label: 'Phase name', outlined: true, dense: true, isValid: (v: string) => !!v.trim() },
    cancel: { flat: true, noCaps: true },
    ok: { unelevated: true, noCaps: true, label: 'Add' }
  }).onOk(async (name: string) => {
    try {
      await schedule.addPhase(name.trim())
    } catch (err) {
      fail(err, 'Could not add the phase')
    }
  })
}

const doBaseline = async () => {
  baselining.value = true
  try {
    await schedule.baseline(baselineStart.value)
    baselineOpen.value = false
    $q.notify({ type: 'positive', message: `Baselined: finishes ${formatDate(schedule.schedule?.planned_finish)}` })
  } catch (err) {
    fail(err, 'Could not baseline the schedule')
  } finally {
    baselining.value = false
  }
}
</script>

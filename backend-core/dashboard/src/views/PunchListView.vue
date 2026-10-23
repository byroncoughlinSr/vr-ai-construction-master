<template>
  <q-page class="q-pa-md">
    <div class="page-container">
      <no-project v-if="!project" what="punch list" />

      <template v-else>
        <page-header eyebrow="Project controls" title="Punch list" :subtitle="`${project.name} — what's left to fix before handover`" icon="checklist">
          <template #actions>
            <q-btn unelevated no-caps color="primary" icon="add" label="Punch item" @click="openItem(null)" />
          </template>
        </page-header>

        <q-banner v-if="punch.error" rounded class="banner-error q-mb-md">
          {{ punch.error }}
          <template #action><q-btn flat no-caps label="Retry" @click="punch.reload()" /></template>
        </q-banner>

        <div class="row q-col-gutter-md q-mb-md">
          <div class="col-6 col-md-3">
            <kpi-metric-card title="Open" :value="summary ? summary.open + summary.in_progress : '—'" icon="pending_actions" tone="warning" :caption="summary ? `${summary.high_priority_open} high priority` : undefined" />
          </div>
          <div class="col-6 col-md-3">
            <kpi-metric-card title="Overdue" :value="summary?.overdue ?? '—'" icon="schedule" :tone="summary?.overdue ? 'negative' : 'blue-grey-5'" caption="Past their due date" />
          </div>
          <div class="col-6 col-md-3">
            <kpi-metric-card title="Ready for sign-off" :value="summary?.ready ?? '—'" icon="fact_check" tone="info" caption="Fixed — check and close" />
          </div>
          <div class="col-6 col-md-3">
            <kpi-metric-card title="Closed" :value="summary ? `${summary.closed}/${summary.total}` : '—'" icon="task_alt" tone="positive" :progress="summary?.percent_closed ?? null" :caption="summary?.percent_closed != null ? `${formatPercent(summary.percent_closed)} of the list` : 'Nothing on the list yet'" />
          </div>
        </div>

        <div class="row q-col-gutter-md">
          <div class="col-12 col-md-3">
            <q-card flat class="app-card">
              <div class="app-card-header"><div class="app-card-title">Open by room</div></div>
              <q-list v-if="summary?.open_by_room.length" dense>
                <q-item clickable :active="!punch.filterRoom" active-class="text-primary" @click="punch.filterRoom = null">
                  <q-item-section>All rooms</q-item-section>
                </q-item>
                <q-item
                  v-for="r in summary.open_by_room"
                  :key="r.room"
                  clickable
                  :active="punch.filterRoom === r.room"
                  active-class="text-primary"
                  @click="punch.filterRoom = punch.filterRoom === r.room ? null : r.room"
                >
                  <q-item-section>{{ r.room }}</q-item-section>
                  <q-item-section side><q-badge outline color="warning" :label="r.open" /></q-item-section>
                </q-item>
              </q-list>
              <q-card-section v-else class="text-caption text-muted">No open items.</q-card-section>
            </q-card>
          </div>

          <div class="col-12 col-md-9">
            <q-card flat class="app-card">
              <div class="app-card-header row items-center q-gutter-sm">
                <q-btn-toggle v-model="punch.filterStatus" no-caps unelevated dense toggle-color="primary" :options="statusFilterOptions" />
                <q-space />
                <q-select v-model="punch.filterTrade" outlined dense clearable emit-value map-options :options="tradeOptions" label="Trade" style="min-width: 150px" />
                <q-input v-model="punch.searchQuery" outlined dense clearable placeholder="Search" style="min-width: 170px">
                  <template #prepend><q-icon name="search" /></template>
                </q-input>
              </div>
              <q-list v-if="punch.filteredItems.length" separator>
                <q-item v-for="i in punch.filteredItems" :key="i.id" clickable @click="openItem(i)">
                  <q-item-section avatar>
                    <q-icon :name="statusIcon[i.status]" :color="statusColor('punch', i.status)" />
                  </q-item-section>
                  <q-item-section>
                    <q-item-label class="text-weight-medium" :class="i.status === 'closed' ? 'text-strike text-muted' : ''">
                      <span class="text-muted tabular">{{ i.code }}</span> {{ i.title }}
                    </q-item-label>
                    <q-item-label caption>
                      {{ i.room || 'No room' }} · {{ titleCase(i.trade) }}
                      <template v-if="i.assignee"> · {{ i.assignee }}</template>
                      <template v-if="i.phase_name"> · {{ i.phase_name }}</template>
                    </q-item-label>
                    <q-item-label v-if="i.due_date && i.status !== 'closed'" caption :class="i.overdue ? 'text-negative text-weight-medium' : ''">
                      Due {{ formatDate(i.due_date) }} ({{ formatRelativeDay(i.due_date) }})
                    </q-item-label>
                  </q-item-section>
                  <q-item-section side>
                    <div class="row no-wrap items-center q-gutter-xs">
                      <q-badge v-if="i.priority !== 'medium' && i.status !== 'closed'" :color="statusColor('priority', i.priority)" :label="titleCase(i.priority)" />
                      <q-badge :color="statusColor('punch', i.status)" :label="statusLabel(i.status)" />
                      <q-btn
                        v-for="a in actionsFor(i)"
                        :key="a.status"
                        :flat="!a.primary"
                        :unelevated="a.primary"
                        dense
                        no-caps
                        size="sm"
                        :color="a.color"
                        :label="a.label"
                        class="q-px-sm"
                        @click.stop="move(i, a.status)"
                      />
                    </div>
                  </q-item-section>
                </q-item>
              </q-list>
              <empty-state
                v-else-if="punch.items.length"
                dense
                icon="filter_alt_off"
                title="Nothing matches"
                message="Try another status, room or trade."
              />
              <empty-state
                v-else
                dense
                icon="checklist"
                title="The punch list is empty"
                message="Walk the house — on site or in VR — and log what needs fixing, room by room."
              />
            </q-card>
          </div>
        </div>

        <q-dialog v-model="itemOpen">
          <q-card class="app-card" style="width: 560px; max-width: 96vw">
            <q-card-section class="text-h6 text-weight-bold q-pb-none">{{ editing ? `Edit ${editing.code}` : 'New punch item' }}</q-card-section>
            <q-form @submit.prevent="saveItem">
              <q-card-section class="row q-col-gutter-sm">
                <div class="col-12"><q-input v-model="form.title" outlined dense autofocus label="What needs fixing *" placeholder="Nail pops above the window" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space /></div>
                <div class="col-6">
                  <q-select
                    v-model="form.room"
                    outlined
                    dense
                    use-input
                    fill-input
                    hide-selected
                    clearable
                    new-value-mode="add-unique"
                    :options="roomChoices"
                    input-debounce="0"
                    label="Room"
                    @input-value="v => (form.room = v)"
                  />
                </div>
                <div class="col-6"><q-select v-model="form.trade" outlined dense emit-value map-options :options="tradeOptions" label="Trade" /></div>
                <div class="col-6"><q-select v-model="form.priority" outlined dense emit-value map-options :options="PRIORITY_OPTIONS" label="Priority" /></div>
                <div class="col-6"><q-select v-model="form.status" outlined dense emit-value map-options :options="PUNCH_STATUS_OPTIONS" label="Status" /></div>
                <div class="col-6"><q-input v-model="form.assignee" outlined dense label="Assigned to" placeholder="Sub or crew member" /></div>
                <div class="col-6"><q-input v-model="form.due_date" outlined dense type="date" stack-label label="Due" /></div>
                <div class="col-12"><q-input v-model="form.description" outlined dense autogrow label="Details" /></div>
              </q-card-section>
              <q-card-actions class="q-px-md q-pb-md">
                <q-btn v-if="editing" flat no-caps color="negative" icon="delete" label="Delete" @click="removeItem" />
                <q-space />
                <q-btn flat no-caps label="Cancel" v-close-popup />
                <q-btn unelevated no-caps color="primary" type="submit" label="Save" :loading="saving" />
              </q-card-actions>
            </q-form>
          </q-card>
        </q-dialog>
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'
import { usePunchListStore, type PunchItemFields } from 'src/stores/punchList'
import { useProjectsStore } from 'src/stores/projects'
import { useProjectData } from 'src/composables/useProjectData'
import type { PunchItem, PunchStatus, TaskPriority } from 'src/types/controls'
import { errorMessage } from 'src/utils/errors'
import { formatDate, formatPercent, formatRelativeDay, titleCase } from 'src/utils/format'
import { PRIORITY_OPTIONS, PUNCH_STATUS_OPTIONS, statusColor } from 'src/utils/status'
import PageHeader from 'src/components/common/PageHeader.vue'
import EmptyState from 'src/components/common/EmptyState.vue'
import NoProject from 'src/components/common/NoProject.vue'
import KpiMetricCard from 'src/components/dashboard/KpiMetricCard.vue'

const $q = useQuasar()
const punch = usePunchListStore()
const projects = useProjectsStore()
const { project } = useProjectData(id => punch.load(id).catch(() => undefined), () => punch.clear())

const summary = computed(() => punch.summary)
const saving = ref(false)

const statusFilterOptions = [
  { value: 'active', label: 'Active' },
  { value: 'ready', label: 'Ready' },
  { value: 'closed', label: 'Closed' },
  { value: 'all', label: 'All' }
]
const tradeOptions = computed(() => punch.trades.map(t => ({ value: t, label: titleCase(t) })))
const roomChoices = computed(() => [...punch.roomOptions, ...(punch.roomOptions.includes('Exterior') ? [] : ['Exterior'])])
const statusLabel = (s: PunchStatus) => PUNCH_STATUS_OPTIONS.find(o => o.value === s)?.label ?? s
const statusIcon: Record<PunchStatus, string> = {
  open: 'radio_button_unchecked', in_progress: 'build_circle', ready: 'fact_check', closed: 'check_circle'
}

/** The next steps for an item: start it, mark it fixed, then the PM closes or sends it back. */
const actionsFor = (i: PunchItem): Array<{ status: PunchStatus; label: string; color: string; primary?: boolean }> => {
  switch (i.status) {
    case 'open': return [{ status: 'in_progress', label: 'Start', color: 'primary' }]
    case 'in_progress': return [{ status: 'ready', label: 'Fixed', color: 'info', primary: true }]
    case 'ready': return [
      { status: 'closed', label: 'Close', color: 'positive', primary: true },
      { status: 'open', label: 'Reject', color: 'negative' }
    ]
    default: return [{ status: 'open', label: 'Reopen', color: 'grey-7' }]
  }
}

const fail = (err: unknown, fallback: string) => $q.notify({ type: 'negative', message: errorMessage(err, fallback) })
const afterChange = () => projects.fetchOverview()

const move = (i: PunchItem, status: PunchStatus) =>
  punch.setStatus(i.id, status).then(afterChange).catch(err => fail(err, 'Could not update the item'))

const itemOpen = ref(false)
const editing = ref<PunchItem | null>(null)
const blank = () => ({
  title: '', room: (punch.filterRoom && punch.filterRoom !== 'Unassigned' ? punch.filterRoom : '') as string | null,
  trade: 'general', priority: 'medium' as TaskPriority, status: 'open' as PunchStatus,
  assignee: '', due_date: '', description: ''
})
const form = reactive(blank())
const openItem = (i: PunchItem | null) => {
  editing.value = i
  Object.assign(form, i
    ? {
        title: i.title, room: i.room ?? '', trade: i.trade, priority: i.priority, status: i.status,
        assignee: i.assignee ?? '', due_date: i.due_date ?? '', description: i.description ?? ''
      }
    : blank())
  itemOpen.value = true
}
const saveItem = async () => {
  saving.value = true
  const text = (v: string | null) => v?.trim() || null
  const fields: PunchItemFields = {
    title: form.title.trim(), room: text(form.room), trade: form.trade, priority: form.priority, status: form.status,
    assignee: text(form.assignee), due_date: form.due_date || null, description: text(form.description)
  }
  try {
    await punch.save(fields, editing.value?.id)
    itemOpen.value = false
    afterChange()
  } catch (err) {
    fail(err, 'Could not save the punch item')
  } finally {
    saving.value = false
  }
}
const removeItem = () => {
  const i = editing.value
  if (!i) return
  $q.dialog({ title: 'Delete punch item?', message: `${i.code} ${i.title}`, cancel: { flat: true, noCaps: true }, ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Delete' } })
    .onOk(() => punch.remove(i.id).then(() => { itemOpen.value = false; afterChange() }).catch(err => fail(err, 'Could not delete')))
}
</script>

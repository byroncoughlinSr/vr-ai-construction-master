<template>
  <q-dialog :model-value="modelValue" position="right" full-height @update:model-value="emit('update:modelValue', $event)">
    <q-card v-if="client" class="client-panel column no-wrap">
      <!-- Header -->
      <q-card-section class="q-pb-sm">
        <div class="row items-start no-wrap">
          <q-avatar size="46px" font-size="17px" :color="stage.color" text-color="white" class="q-mr-md">{{ initials(client.name) }}</q-avatar>
          <div class="col min-width-0">
            <div class="text-h6 text-weight-bold ellipsis leading-tight">{{ client.name }}</div>
            <div class="text-caption text-muted ellipsis">{{ [client.company, titleCase(client.tier)].filter(Boolean).join(' · ') }}</div>
            <div class="row q-gutter-xs q-mt-xs">
              <q-chip v-for="t in client.tags" :key="t" dense square class="q-ma-none bg-surface-2">{{ t }}</q-chip>
            </div>
          </div>
          <q-btn flat round dense icon="more_vert">
            <q-menu anchor="bottom right" self="top right">
              <q-list dense style="min-width: 180px">
                <q-item clickable v-close-popup @click="emit('edit')"><q-item-section avatar><q-icon name="edit" /></q-item-section><q-item-section>Edit</q-item-section></q-item>
                <q-item clickable v-close-popup @click="remove"><q-item-section avatar><q-icon name="delete" color="negative" /></q-item-section><q-item-section class="text-negative">Delete</q-item-section></q-item>
              </q-list>
            </q-menu>
          </q-btn>
          <q-btn flat round dense icon="close" v-close-popup />
        </div>

        <div class="row items-center q-col-gutter-sm q-mt-sm">
          <div class="col-12 col-sm-7">
            <q-select
              :model-value="client.stage"
              :options="stageOptions"
              emit-value
              map-options
              outlined
              dense
              label="Stage"
              @update:model-value="moveStage"
            >
              <template #prepend><q-icon :name="stage.icon" :color="stage.color" size="18px" /></template>
            </q-select>
          </div>
          <div class="col-6 col-sm-auto">
            <div class="text-caption text-muted">Deal</div>
            <div class="text-weight-bold tabular">{{ formatCurrency(client.deal_value) }}</div>
          </div>
          <div class="col-6 col-sm-auto">
            <div class="text-caption text-muted">Win</div>
            <div class="text-weight-bold tabular">{{ Math.round(client.win_probability) }}%</div>
          </div>
        </div>

        <div class="row q-gutter-sm q-mt-sm">
          <q-btn unelevated dense no-caps color="primary" icon="drafts" label="Draft email" class="q-px-sm" @click="emit('compose')" />
          <q-btn v-if="client.phone" outline dense no-caps color="primary" icon="call" label="Call" class="q-px-sm" :href="`tel:${client.phone}`" />
          <q-btn v-if="client.email" outline dense no-caps color="primary" icon="mail" label="Email" class="q-px-sm" :href="`mailto:${client.email}`" />
        </div>
      </q-card-section>

      <q-tabs v-model="tab" dense align="left" no-caps active-color="primary" indicator-color="primary" class="q-px-sm">
        <q-tab name="overview" label="Overview" />
        <q-tab name="activity" :label="`Activity (${client.activities?.length ?? client.activity_count})`" />
        <q-tab name="ai" icon="auto_awesome" label="AI insights" />
      </q-tabs>
      <q-separator />

      <q-scroll-area class="col">
        <q-tab-panels v-model="tab" animated class="bg-transparent">
          <!-- Overview -->
          <q-tab-panel name="overview" class="q-gutter-y-md">
            <div class="next-step rounded-12 q-pa-sm" :class="{ due: followUpDue }">
              <div class="text-caption text-muted">Next step</div>
              <div class="row items-center no-wrap q-gutter-x-sm">
                <q-icon name="schedule" :color="followUpDue ? 'warning' : 'primary'" />
                <div class="col">
                  <div class="text-body2 text-weight-medium">{{ client.next_action || 'No next action set' }}</div>
                  <div class="text-caption" :class="followUpDue ? 'text-warning' : 'text-muted'">
                    {{ client.next_follow_up_at ? `${formatDate(client.next_follow_up_at)} (${formatRelativeDay(client.next_follow_up_at)})` : 'No follow-up date' }}
                  </div>
                </div>
                <q-btn flat dense round icon="edit_calendar" @click="emit('edit')"><q-tooltip>Set the next step</q-tooltip></q-btn>
              </div>
            </div>

            <q-list dense class="details">
              <detail-row icon="mail" :value="client.email" />
              <detail-row icon="call" :value="client.phone" />
              <detail-row icon="place" :value="client.site_address" />
              <detail-row icon="style" :value="client.preferred_style" label="Style" />
              <detail-row icon="square_foot" :value="client.target_square_feet ? `${client.target_square_feet.toLocaleString()} sq ft` : null" label="Size" />
              <detail-row icon="savings" :value="client.target_budget ? formatCurrency(client.target_budget) : null" label="Budget" />
              <detail-row icon="event" :value="client.target_completion_date ? formatDate(client.target_completion_date) : null" label="Move-in" />
              <detail-row icon="campaign" :value="client.source" label="Source" />
              <detail-row icon="history" :value="client.last_contact_at ? formatRelativeDay(client.last_contact_at) : 'Never'" label="Last contact" />
            </q-list>

            <div v-if="client.requirements">
              <div class="text-caption text-muted q-mb-xs">Requirements</div>
              <div class="text-body2" style="white-space: pre-wrap">{{ client.requirements }}</div>
            </div>

            <q-card flat class="app-card">
              <q-card-section class="q-pa-sm">
                <div class="text-caption text-muted q-mb-xs">Project</div>
                <div v-if="client.project_id" class="row items-center no-wrap">
                  <q-icon name="home_work" color="primary" class="q-mr-sm" />
                  <div class="col text-weight-medium ellipsis">{{ client.project_name }}</div>
                  <q-btn flat dense no-caps color="primary" label="Open" @click="openProject" />
                </div>
                <div v-else class="column q-gutter-y-sm">
                  <div class="text-body2 text-muted">No project yet. Start one when they're ready to design, or link an existing house.</div>
                  <div class="row q-gutter-sm">
                    <q-btn unelevated dense no-caps color="primary" icon="add" label="Start project" class="q-px-sm" @click="ui.openNewProject(client.id)" />
                    <q-btn-dropdown v-if="linkableProjects.length" outline dense no-caps color="primary" label="Link existing" class="q-px-sm">
                      <q-list dense style="max-height: 280px">
                        <q-item v-for="p in linkableProjects" :key="p.id" clickable v-close-popup @click="link(p.id)">
                          <q-item-section>{{ p.name }}</q-item-section>
                        </q-item>
                      </q-list>
                    </q-btn-dropdown>
                  </div>
                </div>
              </q-card-section>
            </q-card>
          </q-tab-panel>

          <!-- Activity -->
          <q-tab-panel name="activity">
            <q-form class="log-form q-pa-sm rounded-12 q-mb-md" @submit.prevent="logActivity">
              <div class="row q-gutter-xs q-mb-sm">
                <q-btn
                  v-for="k in ACTIVITY_KINDS"
                  :key="k.value"
                  dense
                  no-caps
                  :outline="log.kind !== k.value"
                  :unelevated="log.kind === k.value"
                  color="primary"
                  :icon="k.icon"
                  :label="k.label"
                  size="sm"
                  class="q-px-xs"
                  @click="log.kind = k.value"
                />
              </div>
              <q-input v-model="log.summary" outlined dense :label="log.kind === 'note' ? 'Note' : 'What happened'" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space />
              <q-input v-model="log.details" outlined dense autogrow label="Details (optional)" class="q-mt-sm" />
              <div class="row q-col-gutter-sm q-mt-xs">
                <div class="col-7">
                  <q-input v-model="log.actionItems" outlined dense label="Action items (one per line)" autogrow />
                </div>
                <div class="col-5">
                  <q-select v-model="log.sentiment" outlined dense emit-value map-options clearable :options="sentimentOptions" label="Mood" />
                </div>
              </div>
              <div class="row justify-end q-mt-sm">
                <q-btn unelevated dense no-caps color="primary" type="submit" label="Log it" class="q-px-md" :loading="logging" />
              </div>
            </q-form>

            <q-timeline v-if="client.activities?.length" color="primary" layout="dense" class="q-ml-xs">
              <q-timeline-entry
                v-for="a in client.activities"
                :key="a.id"
                :icon="activityIcon(a.kind)"
                :color="a.kind === 'stage_change' ? 'blue-grey-5' : 'primary'"
                :subtitle="`${formatDateTime(a.occurred_at)}${a.author ? ' · ' + a.author : ''}`"
              >
                <template #title>
                  <div class="row items-start no-wrap">
                    <div class="col text-body2 text-weight-medium">{{ a.summary }}</div>
                    <q-badge v-if="a.sentiment" :color="SENTIMENT_COLORS[a.sentiment]" :label="titleCase(a.sentiment)" class="q-ml-xs" />
                    <q-btn v-if="a.kind !== 'stage_change'" flat round dense size="xs" icon="close" class="q-ml-xs" @click="removeActivity(a.id)">
                      <q-tooltip>Delete entry</q-tooltip>
                    </q-btn>
                  </div>
                </template>
                <div v-if="a.details" class="text-body2 text-muted ellipsis-3" style="white-space: pre-wrap">{{ a.details }}</div>
                <ul v-if="a.action_items?.length" class="q-my-xs q-pl-md text-body2">
                  <li v-for="item in a.action_items" :key="item">{{ item }}</li>
                </ul>
              </q-timeline-entry>
            </q-timeline>
          </q-tab-panel>

          <!-- AI -->
          <q-tab-panel name="ai" class="q-gutter-y-md">
            <div class="row items-center no-wrap">
              <div class="col text-caption text-muted">
                {{ client.ai_updated_at ? `Written ${formatRelativeDay(client.ai_updated_at)} from ${client.activity_count} timeline entries.` : 'Let the AI read the record and timeline and summarise the client.' }}
              </div>
              <q-btn unelevated dense no-caps color="primary" icon="auto_awesome" :label="client.ai_summary ? 'Refresh' : 'Analyze client'" class="q-px-sm" :loading="analyzing" @click="analyze" />
            </div>
            <template v-if="client.ai_summary">
              <div class="text-body1">{{ client.ai_summary }}</div>
              <div v-if="client.ai_insights?.next_best_action" class="next-step rounded-12 q-pa-sm">
                <div class="text-caption text-muted">Next best action</div>
                <div class="text-body2 text-weight-medium">{{ client.ai_insights.next_best_action }}</div>
              </div>
              <div v-if="client.ai_insights?.preferences?.length">
                <div class="text-caption text-muted q-mb-xs">Preferences</div>
                <ul class="q-my-none q-pl-md text-body2"><li v-for="p in client.ai_insights.preferences" :key="p">{{ p }}</li></ul>
              </div>
              <div v-if="client.ai_insights?.risks?.length">
                <div class="text-caption text-muted q-mb-xs">Risks</div>
                <ul class="q-my-none q-pl-md text-body2"><li v-for="r in client.ai_insights.risks" :key="r">{{ r }}</li></ul>
              </div>
            </template>
            <q-btn outline no-caps color="primary" icon="forum" label="Ask the copilot about this client" class="full-width" @click="askCopilot" />
          </q-tab-panel>
        </q-tab-panels>
      </q-scroll-area>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, h, type FunctionalComponent } from 'vue'
import { useRouter } from 'vue-router'
import { QIcon, QItem, QItemLabel, QItemSection, useQuasar } from 'quasar'
import {
  useCrmStore, ACTIVITY_KINDS, PIPELINE_STAGES, SENTIMENT_COLORS, activityIcon, stageConfig
} from 'src/stores/crm'
import { useProjectsStore } from 'src/stores/projects'
import { useAiCopilotStore } from 'src/stores/aiCopilot'
import { useAuthStore } from 'src/stores/auth'
import { useUiStore } from 'src/stores/ui'
import type { ActivityKind, Client, ClientSentiment, LeadStage } from 'src/types/crm'
import { errorMessage } from 'src/utils/errors'
import {
  formatCurrency, formatDate, formatDateTime, formatRelativeDay, initials, isPastDay, titleCase
} from 'src/utils/format'

const props = defineProps<{ modelValue: boolean; client: Client | null }>()
const emit = defineEmits<{
  (e: 'update:modelValue', open: boolean): void
  (e: 'edit'): void
  (e: 'compose'): void
}>()

// One line of contact/brief details; skipped when there is no value.
const DetailRow: FunctionalComponent<{ icon: string; value: string | null | undefined; label?: string }> = p =>
  p.value
    ? h(QItem, { class: 'q-px-none', style: 'min-height: 30px' }, () => [
        h(QItemSection, { avatar: true, style: 'min-width: 30px' }, () => h(QIcon, { name: p.icon, size: '18px', class: 'text-muted' })),
        h(QItemSection, () => [
          p.label ? h(QItemLabel, { caption: true }, () => p.label) : null,
          h(QItemLabel, { class: 'text-body2' }, () => p.value)
        ])
      ])
    : null

const $q = useQuasar()
const router = useRouter()
const crm = useCrmStore()
const projects = useProjectsStore()
const copilot = useAiCopilotStore()
const auth = useAuthStore()
const ui = useUiStore()

const tab = ref<'overview' | 'activity' | 'ai'>('overview')
const logging = ref(false)
const analyzing = ref(false)
const log = reactive({ kind: 'call' as ActivityKind, summary: '', details: '', actionItems: '', sentiment: null as ClientSentiment | null })

const stage = computed(() => stageConfig(props.client?.stage ?? 'new_inquiry'))
const stageOptions = PIPELINE_STAGES.map(s => ({ value: s.id, label: s.label }))
const sentimentOptions = (['enthusiastic', 'positive', 'neutral', 'concerned'] as const).map(v => ({ value: v, label: titleCase(v) }))
const followUpDue = computed(() => {
  const at = props.client?.next_follow_up_at
  return !!at && (isPastDay(at) || formatRelativeDay(at) === 'today')
})
const linkedIds = computed(() => new Set(crm.clients.map(c => c.project_id).filter(Boolean)))
const linkableProjects = computed(() => projects.projects.filter(p => !linkedIds.value.has(p.id)))

const fail = (err: unknown, fallback: string) => $q.notify({ type: 'negative', message: errorMessage(err, fallback) })

const moveStage = async (value: LeadStage) => {
  if (!props.client || value === props.client.stage) return
  try {
    await crm.moveStage(props.client.id, value)
    $q.notify({ type: 'positive', message: `Moved to ${stageConfig(value).label}` })
  } catch (err) {
    fail(err, 'Could not change the stage')
  }
}

const logActivity = async () => {
  if (!props.client || !log.summary.trim()) return
  logging.value = true
  try {
    await crm.logActivity(props.client.id, {
      kind: log.kind,
      summary: log.summary.trim(),
      details: log.details.trim() || null,
      sentiment: log.sentiment,
      action_items: log.actionItems.split('\n').map(s => s.trim()).filter(Boolean),
      author: auth.fullName || null
    })
    Object.assign(log, { summary: '', details: '', actionItems: '', sentiment: null })
  } catch (err) {
    fail(err, 'Could not log it')
  } finally {
    logging.value = false
  }
}

const removeActivity = async (activityId: number) => {
  if (!props.client) return
  try {
    await crm.deleteActivity(props.client.id, activityId)
  } catch (err) {
    fail(err, 'Could not delete the entry')
  }
}

const analyze = async () => {
  if (!props.client) return
  analyzing.value = true
  try {
    await crm.generateInsights(props.client.id)
  } catch (err) {
    fail(err, 'The AI could not analyze the client')
  } finally {
    analyzing.value = false
  }
}

const link = async (projectId: number) => {
  if (!props.client) return
  try {
    await crm.startProject(props.client.id, { project_id: projectId })
    $q.notify({ type: 'positive', message: 'Project linked' })
  } catch (err) {
    fail(err, 'Could not link the project')
  }
}

const openProject = () => {
  if (!props.client?.project_id) return
  projects.selectProject(props.client.project_id)
  emit('update:modelValue', false)
  router.push('/')
}

const remove = () => {
  const client = props.client
  if (!client) return
  $q.dialog({
    title: 'Delete client?',
    message: `${client.name} and their whole timeline are deleted. Their project, if any, is kept.`,
    cancel: { flat: true, noCaps: true },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Delete' },
    persistent: true
  }).onOk(async () => {
    try {
      await crm.remove(client.id)
      emit('update:modelValue', false)
    } catch (err) {
      fail(err, 'Could not delete the client')
    }
  })
}

const askCopilot = () => {
  if (!props.client) return
  copilot.setOpen(true)
  copilot.ask(`What should I do next with ${props.client.name}, and what are the risks?`, {
    projectId: props.client.project_id ?? projects.currentProjectId,
    clientId: props.client.id
  })
}
</script>

<style lang="sass" scoped>
.client-panel
  width: 520px
  max-width: 100vw
  background: var(--app-surface)

.min-width-0
  min-width: 0

.leading-tight
  line-height: 1.2

.next-step
  background: var(--app-accent-soft)
  &.due
    background: rgba(217, 119, 6, 0.1)

.log-form
  background: var(--app-surface-2)
  border: 1px solid var(--app-border)

.ellipsis-3
  display: -webkit-box
  -webkit-line-clamp: 3
  -webkit-box-orient: vertical
  overflow: hidden
</style>

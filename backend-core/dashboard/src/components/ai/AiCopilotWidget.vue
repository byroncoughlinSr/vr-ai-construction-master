<template>
  <q-drawer
    v-model="copilot.isOpen"
    side="right"
    overlay
    bordered
    :width="$q.screen.lt.sm ? $q.screen.width : 420"
    class="copilot-drawer"
  >
    <div class="column fit no-wrap">
      <!-- Header -->
      <div class="copilot-header row items-center no-wrap q-px-md q-py-sm">
        <q-avatar icon="auto_awesome" size="34px" font-size="18px" color="primary" text-color="white" class="q-mr-sm" />
        <div class="col min-width-0">
          <div class="text-subtitle1 text-weight-bold leading-tight">AI copilot</div>
          <div class="text-caption text-muted ellipsis">{{ contextLabel }}</div>
        </div>
        <q-btn flat round dense icon="delete_sweep" :disable="!copilot.messages.length" @click="copilot.clearChat()">
          <q-tooltip>Clear the conversation</q-tooltip>
        </q-btn>
        <q-btn flat round dense icon="close" @click="copilot.setOpen(false)" />
      </div>
      <q-separator />

      <!-- Messages -->
      <q-scroll-area ref="scroller" class="col">
        <div class="q-pa-md">
          <div v-if="!copilot.messages.length" class="q-pt-md">
            <div class="text-body2 q-mb-md">
              Ask about the selected project, the schedule, the budget or your clients. Answers come from what is in the
              dashboard; when the copilot can do something (change the floor plan, add a task, draft an email) it offers a
              button and asks before doing it.
            </div>
            <div class="column q-gutter-sm">
              <q-btn
                v-for="s in COPILOT_SUGGESTIONS"
                :key="s"
                outline
                no-caps
                align="left"
                color="primary"
                class="suggestion"
                :label="s"
                @click="send(s)"
              />
            </div>
          </div>

          <div v-for="m in copilot.messages" :key="m.id" class="q-mb-md" :class="m.role === 'user' ? 'row justify-end' : ''">
            <div :class="['bubble', m.role, { error: m.error }]">
              <div v-if="m.role === 'user'" class="text-body2" style="white-space: pre-wrap">{{ m.content }}</div>
              <!-- eslint-disable-next-line vue/no-v-html -- renderMarkdown escapes everything first -->
              <div v-else class="markdown text-body2" v-html="renderMarkdown(m.content)" />
              <div v-if="m.actions?.length" class="column q-gutter-xs q-mt-sm">
                <q-btn
                  v-for="a in m.actions"
                  :key="a.label"
                  unelevated
                  dense
                  no-caps
                  align="left"
                  :color="m.done?.includes(a.label) ? 'grey-5' : 'primary'"
                  :icon="m.done?.includes(a.label) ? 'check' : actionIcon(a.type)"
                  :label="a.label"
                  :disable="m.done?.includes(a.label) || running"
                  class="q-px-sm"
                  @click="run(m.id, a)"
                />
              </div>
              <div v-if="m.source" class="text-caption text-muted q-mt-xs">via {{ m.source }}</div>
            </div>
          </div>

          <div v-if="copilot.isThinking" class="row items-center text-muted q-gutter-x-sm">
            <q-spinner-dots size="22px" color="primary" />
            <span class="text-caption">Looking at the project…</span>
          </div>
        </div>
      </q-scroll-area>

      <!-- Input -->
      <q-separator />
      <div class="q-pa-sm">
        <q-input
          v-model="draft"
          outlined
          dense
          autogrow
          :input-style="{ maxHeight: '140px' }"
          placeholder="Ask the copilot…  (Enter to send, Shift+Enter for a new line)"
          :disable="copilot.isThinking"
          @keydown.enter.exact.prevent="send()"
        >
          <template #after>
            <q-btn round unelevated color="primary" icon="send" size="sm" :disable="!draft.trim() || copilot.isThinking" @click="send()" />
          </template>
        </q-input>
      </div>
    </div>
  </q-drawer>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar, QScrollArea } from 'quasar'
import { apiClient } from 'src/services/api'
import { useAiCopilotStore, COPILOT_SUGGESTIONS, type CopilotAction } from 'src/stores/aiCopilot'
import { useProjectsStore } from 'src/stores/projects'
import { useCrmStore } from 'src/stores/crm'
import { useScheduleStore } from 'src/stores/schedule'
import { useBudgetStore } from 'src/stores/budget'
import { useUiStore } from 'src/stores/ui'
import { renderMarkdown } from 'src/utils/markdown'
import { errorMessage } from 'src/utils/errors'
import { formatCurrency } from 'src/utils/format'

const $q = useQuasar()
const router = useRouter()
const copilot = useAiCopilotStore()
const projects = useProjectsStore()
const crm = useCrmStore()
const schedule = useScheduleStore()
const budget = useBudgetStore()
const ui = useUiStore()

const draft = ref('')
const running = ref(false)
const scroller = ref<QScrollArea | null>(null)

const contextLabel = computed(() => {
  const parts = [projects.currentProject?.name ?? 'No project selected']
  if (crm.selected) parts.push(crm.selected.name)
  return parts.join(' · ')
})

const send = (text = draft.value) => {
  if (!text.trim()) return
  draft.value = ''
  copilot.ask(text, { projectId: projects.currentProjectId, clientId: crm.selected?.id ?? null })
}

watch(
  () => [copilot.messages.length, copilot.isThinking],
  async () => {
    await nextTick()
    scroller.value?.setScrollPercentage('vertical', 1, 150)
  }
)

const actionIcon = (type: CopilotAction['type']) =>
  ({
    refine_floor_plan: 'architecture',
    create_task: 'add_task',
    draft_email: 'drafts',
    create_change_order: 'request_quote',
    navigate: 'arrow_forward'
  })[type]

const confirm = (title: string, message: string) =>
  new Promise<boolean>(resolve => {
    $q.dialog({ title, message, cancel: { flat: true, noCaps: true }, ok: { unelevated: true, noCaps: true, label: 'Do it' }, persistent: true })
      .onOk(() => resolve(true))
      .onCancel(() => resolve(false))
  })

const run = async (messageId: string, action: CopilotAction) => {
  const projectId = projects.currentProjectId
  if (action.type === 'navigate') {
    router.push(action.route)
    return
  }
  if (action.type === 'draft_email') {
    router.push({ path: '/crm', query: { client: String(action.client_id), draft: action.purpose } })
    copilot.markDone(messageId, action.label)
    return
  }
  if (!projectId) {
    $q.notify({ type: 'warning', message: 'Select a project first' })
    return
  }

  let question: [string, string]
  if (action.type === 'refine_floor_plan') {
    question = ['Change the floor plan?', `“${action.instruction}” — the AI revises the house and saves a new version.`]
  } else if (action.type === 'create_task') {
    const phase = schedule.phases.find(p => p.id === action.phase_id)
    question = ['Add this task?', `${action.name} (${action.priority}, ${action.duration_days} day${action.duration_days === 1 ? '' : 's'})${phase ? ` to ${phase.name}` : ''}.`]
  } else {
    question = ['Create this change order?', `${action.title}${action.cost_impact ? ` — ${formatCurrency(action.cost_impact)}` : ''}. It is submitted for the owner's approval.`]
  }
  if (!(await confirm(...question))) return

  running.value = true
  try {
    if (action.type === 'refine_floor_plan') {
      $q.notify({ type: 'info', message: 'Revising the floor plan…', timeout: 1500 })
      const result = await apiClient.post<{ floor_plan?: { version: number } }>(
        `/projects/${projectId}/floor-plan/refine`, { instruction: action.instruction }
      )
      ui.floorPlanRevision++
      $q.notify({ type: 'positive', message: `Floor plan updated${result.floor_plan ? ` (version ${result.floor_plan.version})` : ''}` })
    } else if (action.type === 'create_task') {
      await apiClient.post(`/projects/${projectId}/phases/${action.phase_id}/tasks`, {
        name: action.name, priority: action.priority, planned_duration_days: action.duration_days
      })
      if (schedule.projectId === projectId) await schedule.reload()
      $q.notify({ type: 'positive', message: 'Task added to the schedule' })
    } else {
      await budget.addChangeOrder({
        title: action.title, description: action.description, cost_impact: action.cost_impact,
        schedule_impact_days: 0, requested_by: 'AI copilot'
      }, projectId)
      $q.notify({ type: 'positive', message: 'Change order submitted' })
    }
    copilot.markDone(messageId, action.label)
    projects.fetchOverview()
  } catch (err) {
    $q.notify({ type: 'negative', message: errorMessage(err, 'That did not work') })
  } finally {
    running.value = false
  }
}
</script>

<style lang="sass" scoped>
.copilot-header
  min-height: 56px

.leading-tight
  line-height: 1.2

.min-width-0
  min-width: 0

.suggestion
  border-radius: 10px

.bubble
  border-radius: 12px
  padding: 10px 12px
  max-width: 100%
  &.user
    max-width: 88%
    background: var(--q-primary)
    color: white
  &.assistant
    background: var(--app-surface-2)
    border: 1px solid var(--app-border)
  &.error
    border-color: var(--q-negative)
    color: var(--q-negative)

.markdown
  :deep(p)
    margin: 0 0 6px
  :deep(p:last-child)
    margin-bottom: 0
  :deep(ul), :deep(ol)
    margin: 4px 0 6px
    padding-left: 20px
  :deep(code)
    background: var(--app-accent-soft)
    border-radius: 4px
    padding: 0 4px
</style>

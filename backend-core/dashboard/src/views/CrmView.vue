<template>
  <q-page class="q-pa-md">
    <div class="page-container">
      <page-header
        eyebrow="Clients"
        title="Client CRM"
        subtitle="Every homeowner from first inquiry to handover: pipeline, timeline, follow-ups, and AI insights and emails."
        icon="groups"
      >
        <template #actions>
          <q-btn-toggle
            v-model="view"
            unelevated
            no-caps
            toggle-color="primary"
            color="grey-3"
            text-color="grey-9"
            :options="[
              { value: 'board', icon: 'view_kanban', label: 'Board' },
              { value: 'table', icon: 'table_rows', label: 'Table' }
            ]"
          />
          <q-btn unelevated no-caps color="primary" icon="person_add" label="New client" @click="openForm(null)" />
        </template>
      </page-header>

      <!-- Pipeline KPIs -->
      <div class="row q-col-gutter-md q-mb-md">
        <div class="col-6 col-md-3">
          <kpi-metric-card title="Open pipeline" :value="formatCompactCurrency(pipeline?.open_value)" icon="account_balance_wallet" tone="primary"
            :caption="pipeline ? `${pipeline.open_count} open opportunit${pipeline.open_count === 1 ? 'y' : 'ies'}` : undefined" />
        </div>
        <div class="col-6 col-md-3">
          <kpi-metric-card title="Weighted forecast" :value="formatCompactCurrency(pipeline?.weighted_value)" icon="trending_up" tone="secondary"
            caption="Deal value × win probability" hint="The open pipeline weighted by each client's chance of signing." />
        </div>
        <div class="col-6 col-md-3">
          <kpi-metric-card title="Won" :value="formatCompactCurrency(pipeline?.won_value)" icon="emoji_events" tone="positive"
            :caption="pipeline?.win_rate != null ? `${pipeline.win_rate}% win rate` : 'No decided deals yet'" />
        </div>
        <div class="col-6 col-md-3">
          <kpi-metric-card title="Follow-ups due" :value="pipeline?.follow_ups_due.length ?? '—'" icon="schedule"
            :tone="pipeline?.follow_ups_due.length ? 'warning' : 'blue-grey-5'"
            :caption="pipeline?.stale.length ? `${pipeline.stale.length} gone quiet (14+ days)` : 'Nobody has gone quiet'" />
        </div>
      </div>

      <!-- Follow-ups -->
      <q-card v-if="pipeline && (pipeline.follow_ups_due.length || pipeline.stale.length)" flat class="app-card q-mb-md">
        <q-card-section class="row items-center q-gutter-sm q-py-sm">
          <q-icon name="notifications_active" color="warning" size="20px" />
          <span class="text-weight-medium">To do:</span>
          <q-chip
            v-for="f in pipeline.follow_ups_due"
            :key="`due-${f.id}`"
            clickable
            outline
            color="warning"
            icon="schedule"
            class="q-ma-none"
            @click="openClient(f.id)"
          >{{ f.name }}<span class="text-muted q-ml-xs">· {{ f.next_action || formatRelativeDay(f.next_follow_up_at) }}</span></q-chip>
          <q-chip
            v-for="s in pipeline.stale"
            :key="`stale-${s.id}`"
            clickable
            outline
            color="blue-grey"
            icon="hourglass_empty"
            class="q-ma-none"
            @click="openClient(s.id)"
          >{{ s.name }}<span class="text-muted q-ml-xs">· no contact {{ s.last_contact_at ? formatRelativeDay(s.last_contact_at) : 'yet' }}</span></q-chip>
        </q-card-section>
      </q-card>

      <!-- Filters -->
      <div class="row q-col-gutter-sm q-mb-md items-center">
        <div class="col-12 col-sm-6 col-md-4">
          <q-input v-model="crm.searchQuery" outlined dense clearable placeholder="Search name, company, address, style, tag" debounce="150">
            <template #prepend><q-icon name="search" /></template>
          </q-input>
        </div>
        <div class="col-12 col-sm-6 col-md-3">
          <q-select v-model="crm.filterStage" outlined dense emit-value map-options :options="stageFilterOptions" label="Stage" />
        </div>
        <div class="col text-right text-caption text-muted">{{ crm.filteredClients.length }} of {{ crm.clients.length }} clients</div>
      </div>

      <q-banner v-if="crm.error && !crm.clients.length" rounded class="banner-error q-mb-md">
        Could not load the CRM: {{ crm.error }}
        <template #action><q-btn flat no-caps label="Retry" @click="crm.load()" /></template>
      </q-banner>

      <q-card v-if="crm.loaded && !crm.clients.length" flat class="app-card">
        <empty-state icon="groups" title="No clients yet" message="Add the people you're talking to. Log calls, VR walkthroughs and site visits; the AI summarises them and drafts follow-ups.">
          <q-btn unelevated no-caps color="primary" icon="person_add" label="Add your first client" @click="openForm(null)" />
        </empty-state>
      </q-card>

      <crm-kanban
        v-else-if="view === 'board'"
        :clients="crm.filteredClients"
        :stages="boardStages"
        :selected-id="crm.selected?.id"
        @open="openClient"
        @move="onMove"
      />

      <q-card v-else flat class="app-card">
        <q-table
          :rows="crm.filteredClients"
          :columns="columns"
          row-key="id"
          flat
          :loading="crm.loading"
          :pagination="{ rowsPerPage: 15, sortBy: 'next_follow_up_at' }"
          @row-click="(_e, row) => openClient(row.id)"
          class="clickable-table"
        >
          <template #body-cell-name="props">
            <q-td :props="props">
              <div class="row items-center no-wrap">
                <q-avatar size="30px" font-size="11px" :color="stageConfig(props.row.stage).color" text-color="white" class="q-mr-sm">{{ initials(props.row.name) }}</q-avatar>
                <div class="min-width-0">
                  <div class="text-weight-medium">{{ props.row.name }}</div>
                  <div class="text-caption text-muted ellipsis" style="max-width: 240px">{{ props.row.site_address || props.row.email || '—' }}</div>
                </div>
              </div>
            </q-td>
          </template>
          <template #body-cell-stage="props">
            <q-td :props="props"><q-badge :color="stageConfig(props.row.stage).color" :label="props.row.stage_label" /></q-td>
          </template>
          <template #body-cell-next_follow_up_at="props">
            <q-td :props="props" :class="isPastDay(props.row.next_follow_up_at) ? 'text-warning text-weight-medium' : ''">
              {{ props.row.next_follow_up_at ? formatRelativeDay(props.row.next_follow_up_at) : '—' }}
              <div v-if="props.row.next_action" class="text-caption text-muted ellipsis" style="max-width: 200px">{{ props.row.next_action }}</div>
            </q-td>
          </template>
          <template #body-cell-sentiment="props">
            <q-td :props="props">
              <q-badge v-if="props.row.sentiment" :color="SENTIMENT_COLORS[props.row.sentiment as ClientSentiment]" :label="titleCase(props.row.sentiment)" />
              <span v-else class="text-muted">—</span>
            </q-td>
          </template>
          <template #body-cell-actions="props">
            <q-td :props="props" auto-width>
              <q-btn flat round dense icon="drafts" color="primary" @click.stop="compose(props.row.id)"><q-tooltip>Draft email</q-tooltip></q-btn>
            </q-td>
          </template>
        </q-table>
      </q-card>
    </div>

    <client-detail-drawer
      v-model="detailOpen"
      :client="crm.selected"
      @edit="openForm(crm.selected)"
      @compose="compose(crm.selected?.id)"
    />
    <client-form-dialog v-model="formOpen" :client="editing" @saved="c => openClient(c.id)" />
    <ai-outreach-modal v-model="emailOpen" :client="crm.selected" :initial-purpose="draftPurpose" />
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { useCrmStore, OPEN_STAGES, PIPELINE_STAGES, SENTIMENT_COLORS, stageConfig } from 'src/stores/crm'
import type { Client, ClientSentiment, EmailPurpose, LeadStage } from 'src/types/crm'
import { errorMessage } from 'src/utils/errors'
import { formatCompactCurrency, formatCurrency, formatRelativeDay, initials, isPastDay, titleCase } from 'src/utils/format'
import PageHeader from 'src/components/common/PageHeader.vue'
import EmptyState from 'src/components/common/EmptyState.vue'
import KpiMetricCard from 'src/components/dashboard/KpiMetricCard.vue'
import CrmKanban from 'src/components/crm/CrmKanban.vue'
import ClientDetailDrawer from 'src/components/crm/ClientDetailDrawer.vue'
import ClientFormDialog from 'src/components/crm/ClientFormDialog.vue'
import AiOutreachModal from 'src/components/crm/AiOutreachModal.vue'

const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const crm = useCrmStore()

const VIEW_KEY = 'dashboard.crmView'
const view = ref<'board' | 'table'>((() => {
  try {
    return localStorage.getItem(VIEW_KEY) === 'table' ? 'table' : 'board'
  } catch {
    return 'board'
  }
})())
watch(view, v => {
  try {
    localStorage.setItem(VIEW_KEY, v)
  } catch {
    // not remembered
  }
})

const detailOpen = ref(false)
const formOpen = ref(false)
const emailOpen = ref(false)
const editing = ref<Client | null>(null)
const draftPurpose = ref<EmailPurpose>('follow_up')

const pipeline = computed(() => crm.pipeline)
// The board shows lost clients only when they're asked for.
const boardStages = computed(() => {
  const filter = crm.filterStage
  if (filter === 'all') return PIPELINE_STAGES.filter(s => s.id !== 'closed_lost')
  if (filter === 'open') return PIPELINE_STAGES.filter(s => OPEN_STAGES.includes(s.id))
  return PIPELINE_STAGES.filter(s => s.id === filter)
})
const stageFilterOptions = [
  { value: 'all', label: 'All active' },
  { value: 'open', label: 'Open opportunities' },
  ...PIPELINE_STAGES.map(s => ({ value: s.id, label: s.label }))
]

const columns = [
  { name: 'name', label: 'Client', field: 'name', align: 'left' as const, sortable: true },
  { name: 'stage', label: 'Stage', field: (r: Client) => PIPELINE_STAGES.findIndex(s => s.id === r.stage), align: 'left' as const, sortable: true },
  { name: 'deal_value', label: 'Deal', field: 'deal_value', align: 'right' as const, sortable: true, format: (v: number) => formatCurrency(v) },
  { name: 'win_probability', label: 'Win', field: 'win_probability', align: 'right' as const, sortable: true, format: (v: number) => `${Math.round(v)}%` },
  { name: 'next_follow_up_at', label: 'Follow up', field: (r: Client) => r.next_follow_up_at ?? '9999', align: 'left' as const, sortable: true },
  { name: 'sentiment', label: 'Mood', field: 'sentiment', align: 'left' as const },
  { name: 'project_name', label: 'Project', field: 'project_name', align: 'left' as const, format: (v: string | null) => v ?? '—' },
  { name: 'actions', label: '', field: 'id', align: 'right' as const }
]

const openClient = async (clientId: number) => {
  try {
    await crm.open(clientId)
    detailOpen.value = true
  } catch (err) {
    $q.notify({ type: 'negative', message: errorMessage(err, 'Could not open the client') })
  }
}

const openForm = (client: Client | null) => {
  editing.value = client
  formOpen.value = true
}

const compose = async (clientId?: number, purpose: EmailPurpose = 'follow_up') => {
  if (!clientId) return
  if (crm.selected?.id !== clientId) await crm.open(clientId)
  draftPurpose.value = purpose
  emailOpen.value = true
}

const onMove = async ({ clientId, stage }: { clientId: number; stage: LeadStage }) => {
  try {
    const client = await crm.moveStage(clientId, stage)
    $q.notify({ type: 'positive', message: `${client.name} → ${stageConfig(stage).label}` })
  } catch (err) {
    $q.notify({ type: 'negative', message: errorMessage(err, 'Could not move the client') })
  }
}

watch(detailOpen, open => {
  if (!open && !emailOpen.value && !formOpen.value) crm.close()
})

// ?client=ID opens a client; &draft=purpose opens the email drafter (copilot, bell).
const followQuery = async () => {
  const id = Number(route.query.client)
  if (!id) return
  const draft = route.query.draft as EmailPurpose | undefined
  router.replace({ query: {} })
  if (draft) await compose(id, draft)
  else await openClient(id)
}
watch(() => route.query.client, followQuery)

onMounted(async () => {
  if (!crm.loaded) await crm.load().catch(() => undefined)
  followQuery()
})
</script>

<style lang="sass" scoped>
.min-width-0
  min-width: 0

.clickable-table :deep(tbody tr)
  cursor: pointer
</style>

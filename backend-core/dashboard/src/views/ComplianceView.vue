<template>
  <q-page class="q-pa-md">
    <div class="page-container">
      <no-project v-if="!project" what="permits and inspections" />

      <template v-else>
        <page-header eyebrow="Project controls" title="Permits & inspections" :subtitle="`${project.name} — what's filed, issued, and inspected`" icon="verified">
          <template #actions>
            <q-btn outline no-caps color="primary" icon="event" label="Schedule inspection" @click="openInspection(null)" />
            <q-btn unelevated no-caps color="primary" icon="add" label="Permit" @click="openPermit(null)" />
          </template>
        </page-header>

        <q-banner v-if="compliance.error" rounded class="banner-error q-mb-md">
          {{ compliance.error }}
          <template #action><q-btn flat no-caps label="Retry" @click="compliance.reload()" /></template>
        </q-banner>

        <div class="row q-col-gutter-md q-mb-md">
          <div class="col-6 col-md-3">
            <kpi-metric-card title="Active permits" :value="summary ? `${summary.permits_active}/${summary.permits_total}` : '—'" icon="gavel" tone="primary" caption="Approved or issued" />
          </div>
          <div class="col-6 col-md-3">
            <kpi-metric-card title="Upcoming inspections" :value="summary?.inspections_upcoming ?? '—'" icon="event" tone="info" :caption="nextInspection ? `Next: ${nextInspection.inspection_type}, ${formatRelativeDay(nextInspection.scheduled_date)}` : 'None scheduled'" />
          </div>
          <div class="col-6 col-md-3">
            <kpi-metric-card title="Passed" :value="summary?.inspections_passed ?? '—'" icon="task_alt" tone="positive" :caption="summary?.pass_rate != null ? `${summary.pass_rate}% first-time pass rate` : 'No results yet'" />
          </div>
          <div class="col-6 col-md-3">
            <kpi-metric-card title="Failed" :value="summary?.inspections_failed ?? '—'" icon="report" :tone="summary?.inspections_failed ? 'negative' : 'blue-grey-5'" caption="Need corrections and re-inspection" />
          </div>
        </div>

        <div class="row q-col-gutter-md">
          <div class="col-12 col-md-6">
            <q-card flat class="app-card full-height">
              <div class="app-card-header"><div class="app-card-title">Permits</div></div>
              <q-list v-if="compliance.permits.length" separator>
                <q-item v-for="p in compliance.permits" :key="p.id" clickable @click="openPermit(p)">
                  <q-item-section>
                    <q-item-label class="text-weight-medium">
                      {{ permitLabel(p) }}
                      <q-badge v-if="p.task_id" outline color="primary" label="Gate" class="q-ml-xs">
                        <q-tooltip>Approving this permit completes its task in the schedule</q-tooltip>
                      </q-badge>
                    </q-item-label>
                    <q-item-label caption>
                      {{ p.jurisdiction || 'Jurisdiction not set' }}
                      <template v-if="p.issued_date"> · issued {{ formatDate(p.issued_date) }}</template>
                    </q-item-label>
                    <q-item-label v-if="p.expiration_date" caption :class="expiringSoon(p.expiration_date) ? 'text-warning text-weight-medium' : ''">
                      Expires {{ formatDate(p.expiration_date) }} ({{ formatRelativeDay(p.expiration_date) }})
                    </q-item-label>
                  </q-item-section>
                  <q-item-section side>
                    <q-badge :color="statusColor('permit', p.status)" :label="titleCase(p.status)" />
                    <div v-if="p.permit_fee" class="text-caption text-muted q-mt-xs tabular">{{ formatCurrency(p.permit_fee) }}</div>
                  </q-item-section>
                </q-item>
              </q-list>
              <empty-state v-else dense icon="gavel" title="No permits yet" message="Track building, electrical, plumbing and other permits with their expiry dates." />
            </q-card>
          </div>

          <div class="col-12 col-md-6">
            <q-card flat class="app-card full-height">
              <div class="app-card-header"><div class="app-card-title">Inspections</div></div>
              <q-list v-if="compliance.inspections.length" separator>
                <q-item v-for="i in compliance.inspections" :key="i.id">
                  <q-item-section avatar>
                    <q-icon :name="inspectionIcon(i.status)" :color="statusColor('inspection', i.status)" />
                  </q-item-section>
                  <q-item-section>
                    <q-item-label class="text-weight-medium">
                      {{ i.inspection_type }}
                      <q-badge v-if="i.task_id" outline color="primary" label="Gate" class="q-ml-xs">
                        <q-tooltip>Its schedule task can't be completed until this inspection passes</q-tooltip>
                      </q-badge>
                    </q-item-label>
                    <q-item-label caption>
                      {{ i.scheduled_date ? formatDateTime(i.scheduled_date) : 'Not scheduled' }}
                      <template v-if="i.inspector_name"> · {{ i.inspector_name }}</template>
                      <template v-if="i.permit_number"> · {{ i.permit_number }}</template>
                    </q-item-label>
                    <q-item-label v-if="i.critical_findings || i.result_details" caption class="ellipsis-2" :class="i.status === 'failed' || i.status === 'partial' ? 'text-negative' : ''">
                      {{ i.critical_findings || i.result_details }}
                    </q-item-label>
                  </q-item-section>
                  <q-item-section side>
                    <div class="row no-wrap items-center q-gutter-xs">
                      <template v-if="i.status === 'scheduled'">
                        <q-btn unelevated dense no-caps size="sm" color="positive" label="Passed" class="q-px-sm" @click="recordResult(i, 'passed')" />
                        <q-btn flat dense no-caps size="sm" color="negative" label="Failed" @click="recordResult(i, 'failed')" />
                      </template>
                      <q-badge v-else :color="statusColor('inspection', i.status)" :label="titleCase(i.status)" />
                      <q-btn flat round dense size="sm" icon="edit" @click="openInspection(i)" />
                    </div>
                  </q-item-section>
                </q-item>
              </q-list>
              <empty-state v-else dense icon="fact_check" title="No inspections yet" message="Schedule foundation, framing, MEP rough-in, insulation and final inspections." />
            </q-card>
          </div>
        </div>

        <!-- Permit -->
        <q-dialog v-model="permitOpen">
          <q-card class="app-card" style="width: 560px; max-width: 96vw">
            <q-card-section class="text-h6 text-weight-bold q-pb-none">{{ permitEditing ? 'Edit permit' : 'New permit' }}</q-card-section>
            <q-form @submit.prevent="savePermit">
              <q-card-section class="row q-col-gutter-sm">
                <div class="col-6"><q-input v-model="permit.permit_type" outlined dense label="Type *" placeholder="Building" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space /></div>
                <div class="col-6"><q-input v-model="permit.permit_number" outlined dense label="Number" hint="Once the jurisdiction issues one" /></div>
                <div class="col-12 col-sm-8"><q-input v-model="permit.jurisdiction" outlined dense label="Jurisdiction" placeholder="City building department" /></div>
                <div class="col-12 col-sm-4"><q-select v-model="permit.status" outlined dense emit-value map-options :options="permitStatusOptions" label="Status" /></div>
                <div class="col-4"><q-input v-model="permit.application_date" outlined dense type="date" stack-label label="Applied" /></div>
                <div class="col-4"><q-input v-model="permit.issued_date" outlined dense type="date" stack-label label="Issued" /></div>
                <div class="col-4"><q-input v-model="permit.expiration_date" outlined dense type="date" stack-label label="Expires" /></div>
                <div class="col-6"><q-input v-model.number="permit.permit_fee" outlined dense type="number" min="0" prefix="$" label="Fee" /></div>
                <div class="col-6"><q-input v-model="permit.contact_name" outlined dense label="Contact" /></div>
                <div class="col-12"><q-input v-model="permit.conditions" outlined dense autogrow label="Conditions" /></div>
              </q-card-section>
              <q-card-actions class="q-px-md q-pb-md">
                <q-btn v-if="permitEditing" flat no-caps color="negative" icon="delete" label="Delete" @click="removePermit" />
                <q-space />
                <q-btn flat no-caps label="Cancel" v-close-popup />
                <q-btn unelevated no-caps color="primary" type="submit" label="Save" :loading="saving" />
              </q-card-actions>
            </q-form>
          </q-card>
        </q-dialog>

        <!-- Inspection -->
        <q-dialog v-model="inspectionOpen">
          <q-card class="app-card" style="width: 540px; max-width: 96vw">
            <q-card-section class="text-h6 text-weight-bold q-pb-none">{{ inspectionEditing ? 'Edit inspection' : 'Schedule an inspection' }}</q-card-section>
            <q-form @submit.prevent="saveInspection">
              <q-card-section class="row q-col-gutter-sm">
                <div class="col-12">
                  <q-select
                    v-model="inspection.inspection_type"
                    outlined
                    dense
                    use-input
                    fill-input
                    hide-selected
                    new-value-mode="add-unique"
                    :options="INSPECTION_TYPES"
                    input-debounce="0"
                    label="Inspection *"
                    :rules="[v => !!(v && v.trim()) || 'Required']"
                    hide-bottom-space
                    @input-value="v => (inspection.inspection_type = v)"
                  />
                </div>
                <div class="col-6"><q-input v-model="inspection.date" outlined dense type="date" stack-label label="Date" /></div>
                <div class="col-6"><q-input v-model="inspection.time" outlined dense type="time" stack-label label="Time" /></div>
                <div class="col-6"><q-input v-model="inspection.inspector_name" outlined dense label="Inspector" /></div>
                <div class="col-6"><q-select v-model="inspection.permit_id" outlined dense emit-value map-options clearable :options="permitOptions" label="Permit" /></div>
                <template v-if="inspectionEditing">
                  <div class="col-6"><q-select v-model="inspection.status" outlined dense emit-value map-options :options="inspectionStatusOptions" label="Result" /></div>
                  <div class="col-12"><q-input v-model="inspection.result_details" outlined dense autogrow label="Findings" /></div>
                  <div class="col-12"><q-input v-model="inspection.critical_findings" outlined dense autogrow label="Corrections required" /></div>
                  <div v-if="inspection.status === 'failed'" class="col-12">
                    <q-toggle v-model="inspection.followup_completed" label="Corrections made (clears it from Needs attention)" />
                  </div>
                </template>
              </q-card-section>
              <q-card-actions class="q-px-md q-pb-md">
                <q-btn v-if="inspectionEditing" flat no-caps color="negative" icon="delete" label="Delete" @click="removeInspection" />
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
import { useComplianceStore, type InspectionFields, type PermitFields } from 'src/stores/compliance'
import { useProjectsStore } from 'src/stores/projects'
import { useProjectData } from 'src/composables/useProjectData'
import type { Inspection, InspectionStatus, Permit, PermitStatus } from 'src/types/controls'
import { errorMessage } from 'src/utils/errors'
import { formatCurrency, formatDate, formatDateTime, formatRelativeDay, isPastDay, parseDate, titleCase } from 'src/utils/format'
import { INSPECTION_STATUS_OPTIONS, PERMIT_STATUS_OPTIONS, statusColor } from 'src/utils/status'
import PageHeader from 'src/components/common/PageHeader.vue'
import EmptyState from 'src/components/common/EmptyState.vue'
import NoProject from 'src/components/common/NoProject.vue'
import KpiMetricCard from 'src/components/dashboard/KpiMetricCard.vue'

const INSPECTION_TYPES = [
  'Foundation (pre-pour)', 'Framing', 'Rough electrical', 'Rough plumbing', 'Rough mechanical',
  'Insulation', 'Drywall', 'Final electrical', 'Final plumbing', 'Final building / occupancy'
]

const $q = useQuasar()
const compliance = useComplianceStore()
const projects = useProjectsStore()
const { project } = useProjectData(id => compliance.load(id).catch(() => undefined), () => compliance.clear())

const summary = computed(() => compliance.summary)
const nextInspection = computed(() =>
  compliance.inspections.find(i => i.status === 'scheduled' && i.scheduled_date && !isPastDay(i.scheduled_date))
)
const saving = ref(false)

const permitStatusOptions = PERMIT_STATUS_OPTIONS
const inspectionStatusOptions = INSPECTION_STATUS_OPTIONS
const permitLabel = (p: Permit) => (p.permit_number ? `${p.permit_type} · ${p.permit_number}` : p.title)
const permitOptions = computed(() => compliance.permits.map(p => ({ value: p.id, label: permitLabel(p) })))

const expiringSoon = (iso: string) => {
  const d = parseDate(iso)
  return !!d && d.getTime() - Date.now() < 30 * 86_400_000
}
const inspectionIcon = (status: string) =>
  ({ passed: 'check_circle', failed: 'cancel', partial: 'error', cancelled: 'block', not_scheduled: 'event_busy' } as Record<string, string>)[status] ?? 'event'

const fail = (err: unknown, fallback: string) => $q.notify({ type: 'negative', message: errorMessage(err, fallback) })
const afterChange = () => projects.fetchOverview()

// --- permits
const permitOpen = ref(false)
const permitEditing = ref<Permit | null>(null)
const blankPermit = () => ({
  permit_type: '', permit_number: '', jurisdiction: '', status: 'applied' as PermitStatus,
  application_date: '', issued_date: '', expiration_date: '', permit_fee: 0, contact_name: '', conditions: ''
})
const permit = reactive(blankPermit())
const openPermit = (p: Permit | null) => {
  permitEditing.value = p
  Object.assign(permit, p
    ? {
        permit_type: p.permit_type, permit_number: p.permit_number ?? '', jurisdiction: p.jurisdiction ?? '', status: p.status,
        application_date: p.application_date ?? '', issued_date: p.issued_date ?? '', expiration_date: p.expiration_date ?? '',
        permit_fee: p.permit_fee, contact_name: p.contact_name ?? '', conditions: p.conditions ?? ''
      }
    : blankPermit())
  permitOpen.value = true
}
const savePermit = async () => {
  saving.value = true
  const text = (v: string) => v.trim() || null
  const fields: PermitFields = {
    permit_type: permit.permit_type.trim(), permit_number: text(permit.permit_number), jurisdiction: text(permit.jurisdiction),
    status: permit.status, application_date: permit.application_date || null, issued_date: permit.issued_date || null,
    expiration_date: permit.expiration_date || null, permit_fee: permit.permit_fee || 0,
    contact_name: text(permit.contact_name), conditions: text(permit.conditions)
  }
  try {
    await compliance.savePermit(fields, permitEditing.value?.id)
    permitOpen.value = false
    afterChange()
  } catch (err) {
    fail(err, 'Could not save the permit')
  } finally {
    saving.value = false
  }
}
const removePermit = () => {
  const p = permitEditing.value
  if (!p) return
  $q.dialog({ title: 'Delete permit?', message: `${permitLabel(p)}. Inspections that name it keep their own details.`, cancel: { flat: true, noCaps: true }, ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Delete' } })
    .onOk(() => compliance.deletePermit(p.id).then(() => { permitOpen.value = false; afterChange() }).catch(err => fail(err, 'Could not delete')))
}

// --- inspections
const inspectionOpen = ref(false)
const inspectionEditing = ref<Inspection | null>(null)
const blankInspection = () => ({
  inspection_type: '', date: '', time: '09:00', inspector_name: '', permit_id: null as number | null,
  status: 'scheduled' as InspectionStatus, result_details: '', critical_findings: '', followup_completed: false
})
const inspection = reactive(blankInspection())
const openInspection = (i: Inspection | null) => {
  inspectionEditing.value = i
  Object.assign(inspection, i
    ? {
        inspection_type: i.inspection_type, date: i.scheduled_date?.slice(0, 10) ?? '', time: i.scheduled_date?.slice(11, 16) || '09:00',
        inspector_name: i.inspector_name ?? '', permit_id: i.permit_id, status: i.status,
        result_details: i.result_details ?? '', critical_findings: i.critical_findings ?? '', followup_completed: false
      }
    : blankInspection())
  inspectionOpen.value = true
}
const saveInspection = async () => {
  saving.value = true
  const fields: Partial<InspectionFields> = {
    inspection_type: inspection.inspection_type.trim(),
    scheduled_date: inspection.date ? `${inspection.date}T${inspection.time || '09:00'}:00` : null,
    inspector_name: inspection.inspector_name.trim() || null,
    permit_id: inspection.permit_id
  }
  if (inspectionEditing.value) {
    Object.assign(fields, {
      status: inspection.status,
      result_details: inspection.result_details.trim() || null,
      critical_findings: inspection.critical_findings.trim() || null,
      requires_followup: inspection.status === 'failed' || inspection.status === 'partial',
      followup_completed: inspection.followup_completed
    })
  }
  try {
    const result = await compliance.saveInspection(fields, inspectionEditing.value?.id)
    inspectionOpen.value = false
    afterResult(result)
  } catch (err) {
    fail(err, 'Could not save the inspection')
  } finally {
    saving.value = false
  }
}
// A result can change the schedule: passing completes the inspection's task,
// failing adds a correction task it waits on.
const afterResult = (result: Inspection | undefined) => {
  afterChange()
  if (result?.completed_task) $q.notify({ type: 'positive', message: 'Inspection passed: its schedule task is complete' })
  if (result?.correction_task) $q.notify({ type: 'warning', message: 'A correction task was added to the schedule' })
}
const recordResult = (i: Inspection, status: 'passed' | 'failed') => {
  if (status === 'passed') {
    compliance.saveInspection({ status }, i.id).then(afterResult).catch(err => fail(err, 'Could not record the result'))
    return
  }
  $q.dialog({
    title: `${i.inspection_type}: failed`,
    message: 'What has to be corrected?',
    prompt: { model: '', type: 'textarea', outlined: true, autogrow: true },
    cancel: { flat: true, noCaps: true },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Record failure' }
  }).onOk((findings: string) => {
    compliance.saveInspection({ status, critical_findings: findings.trim() || null, requires_followup: true }, i.id)
      .then(afterResult).catch(err => fail(err, 'Could not record the result'))
  })
}
const removeInspection = () => {
  const i = inspectionEditing.value
  if (!i) return
  $q.dialog({ title: 'Delete inspection?', message: i.inspection_type, cancel: { flat: true, noCaps: true }, ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Delete' } })
    .onOk(() => compliance.deleteInspection(i.id).then(() => { inspectionOpen.value = false; afterChange() }).catch(err => fail(err, 'Could not delete')))
}
</script>

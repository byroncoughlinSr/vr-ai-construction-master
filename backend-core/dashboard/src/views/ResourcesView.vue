<template>
  <q-page class="q-pa-md">
    <div class="page-container">
      <page-header
        eyebrow="Project controls"
        title="Crew & equipment"
        :subtitle="project ? `Who and what is on ${project.name}, and what's free for it` : 'Your crew and equipment across projects'"
        icon="engineering"
      >
        <template #actions>
          <q-btn-toggle
            v-model="scope"
            unelevated
            no-caps
            toggle-color="primary"
            color="grey-3"
            text-color="grey-9"
            :options="[{ value: 'project', label: 'This project', disable: !project }, { value: 'all', label: 'Everything' }]"
          />
          <q-btn outline no-caps color="primary" icon="construction" label="Equipment" @click="openEquipment(null)" />
          <q-btn unelevated no-caps color="primary" icon="person_add" label="Crew member" @click="openCrew(null)" />
        </template>
      </page-header>

      <q-banner v-if="resources.error" rounded class="banner-error q-mb-md">
        {{ resources.error }}
        <template #action><q-btn flat no-caps label="Retry" @click="resources.load()" /></template>
      </q-banner>

      <div class="row q-col-gutter-md q-mb-md">
        <div class="col-6 col-md-3">
          <kpi-metric-card title="Crew on project" :value="project ? resources.crewOn(project.id).length : '—'" icon="groups" tone="primary"
            :caption="`${resources.crew.filter(m => m.is_available && !m.project_id).length} available unassigned`" />
        </div>
        <div class="col-6 col-md-3">
          <kpi-metric-card title="Daily labor" :value="project ? formatCompactCurrency(resources.dailyLaborCost(project.id)) : '—'" icon="payments" tone="secondary"
            caption="8 h × hourly rates on this project" />
        </div>
        <div class="col-6 col-md-3">
          <kpi-metric-card title="Equipment on project" :value="project ? resources.equipmentOn(project.id).length : '—'" icon="construction" tone="primary"
            :caption="project ? `${formatCompactCurrency(resources.equipmentOn(project.id).reduce((t, e) => t + e.daily_rate, 0))}/day rental` : undefined" />
        </div>
        <div class="col-6 col-md-3">
          <kpi-metric-card title="Maintenance due" :value="maintenanceDue.length" icon="build_circle" :tone="maintenanceDue.length ? 'warning' : 'blue-grey-5'"
            caption="Within 14 days, or in the shop" />
        </div>
      </div>

      <div class="row q-col-gutter-md">
        <div class="col-12 col-md-6">
          <q-card flat class="app-card full-height">
            <div class="app-card-header"><div class="app-card-title">Crew</div></div>
            <q-table :rows="crewRows" :columns="crewColumns" row-key="id" flat :loading="resources.loading" :pagination="{ rowsPerPage: 15 }" no-data-label="No crew here yet">
              <template #body-cell-name="props">
                <q-td :props="props">
                  <div class="text-weight-medium">{{ props.row.name }}</div>
                  <div class="text-caption text-muted">{{ props.row.role }}<template v-if="props.row.phone"> · {{ props.row.phone }}</template></div>
                </q-td>
              </template>
              <template #body-cell-project="props">
                <q-td :props="props">
                  <q-badge v-if="!props.row.is_available" color="blue-grey-5" label="Unavailable" />
                  <span v-else-if="props.row.project_name" class="text-body2">{{ props.row.project_name }}</span>
                  <span v-else class="text-positive text-body2">Free</span>
                </q-td>
              </template>
              <template #body-cell-actions="props">
                <q-td :props="props" auto-width>
                  <q-btn v-if="project && props.row.project_id !== project.id && props.row.is_available" flat dense no-caps size="sm" color="primary" label="Assign" @click="assignCrew(props.row, project.id)" />
                  <q-btn v-else-if="project && props.row.project_id === project.id" flat dense no-caps size="sm" label="Release" @click="assignCrew(props.row, null)" />
                  <q-btn flat round dense size="sm" icon="edit" @click="openCrew(props.row)" />
                </q-td>
              </template>
            </q-table>
          </q-card>
        </div>

        <div class="col-12 col-md-6">
          <q-card flat class="app-card full-height">
            <div class="app-card-header"><div class="app-card-title">Equipment</div></div>
            <q-table :rows="equipmentRows" :columns="equipmentColumns" row-key="id" flat :loading="resources.loading" :pagination="{ rowsPerPage: 15 }" no-data-label="No equipment here yet">
              <template #body-cell-name="props">
                <q-td :props="props">
                  <div class="text-weight-medium">{{ props.row.name }}</div>
                  <div class="text-caption text-muted">{{ [props.row.equipment_type, props.row.model, props.row.owned ? 'Owned' : props.row.rental_company || 'Rented'].filter(Boolean).join(' · ') }}</div>
                </q-td>
              </template>
              <template #body-cell-status="props">
                <q-td :props="props">
                  <q-badge :color="statusColor('equipment', props.row.status)" :label="titleCase(props.row.status)" />
                  <div v-if="props.row.next_maintenance_date" class="text-caption" :class="maintenanceDue.includes(props.row) ? 'text-warning' : 'text-muted'">
                    Service {{ formatRelativeDay(props.row.next_maintenance_date) }}
                  </div>
                </q-td>
              </template>
              <template #body-cell-actions="props">
                <q-td :props="props" auto-width>
                  <q-btn v-if="project && props.row.project_id !== project.id && props.row.status === 'available'" flat dense no-caps size="sm" color="primary" label="Assign" @click="assignEquipment(props.row, project.id)" />
                  <q-btn v-else-if="project && props.row.project_id === project.id" flat dense no-caps size="sm" label="Release" @click="assignEquipment(props.row, null)" />
                  <q-btn flat round dense size="sm" icon="edit" @click="openEquipment(props.row)" />
                </q-td>
              </template>
            </q-table>
          </q-card>
        </div>
      </div>
    </div>

    <!-- Crew member -->
    <q-dialog v-model="crewOpen">
      <q-card class="app-card" style="width: 520px; max-width: 96vw">
        <q-card-section class="text-h6 text-weight-bold q-pb-none">{{ crewEditing ? 'Edit crew member' : 'New crew member' }}</q-card-section>
        <q-form @submit.prevent="saveCrew">
          <q-card-section class="row q-col-gutter-sm">
            <div class="col-12 col-sm-6"><q-input v-model="crew.name" outlined dense label="Name *" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space /></div>
            <div class="col-12 col-sm-6"><q-input v-model="crew.role" outlined dense label="Trade / role *" placeholder="Carpenter" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space /></div>
            <div class="col-6"><q-input v-model="crew.phone" outlined dense label="Phone" /></div>
            <div class="col-6"><q-input v-model="crew.email" outlined dense label="Email" /></div>
            <div class="col-6"><q-input v-model.number="crew.hourly_rate" outlined dense type="number" min="0" prefix="$" suffix="/h" label="Rate" /></div>
            <div class="col-6"><q-select v-model="crew.project_id" outlined dense emit-value map-options clearable :options="projectOptions" label="On project" /></div>
            <div class="col-12"><q-toggle v-model="crew.is_available" label="Available for work" /></div>
          </q-card-section>
          <q-card-actions class="q-px-md q-pb-md">
            <q-btn v-if="crewEditing" flat no-caps color="negative" icon="delete" label="Delete" @click="removeCrew" />
            <q-space />
            <q-btn flat no-caps label="Cancel" v-close-popup />
            <q-btn unelevated no-caps color="primary" type="submit" label="Save" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Equipment -->
    <q-dialog v-model="equipmentOpen">
      <q-card class="app-card" style="width: 540px; max-width: 96vw">
        <q-card-section class="text-h6 text-weight-bold q-pb-none">{{ equipmentEditing ? 'Edit equipment' : 'New equipment' }}</q-card-section>
        <q-form @submit.prevent="saveEquipment">
          <q-card-section class="row q-col-gutter-sm">
            <div class="col-12 col-sm-7"><q-input v-model="equipment.name" outlined dense label="Name *" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space /></div>
            <div class="col-12 col-sm-5"><q-input v-model="equipment.equipment_type" outlined dense label="Type *" placeholder="Excavator" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space /></div>
            <div class="col-6"><q-input v-model="equipment.model" outlined dense label="Model" /></div>
            <div class="col-6"><q-input v-model="equipment.serial_number" outlined dense label="Serial #" /></div>
            <div class="col-6"><q-toggle v-model="equipment.owned" label="Company owned" /></div>
            <div class="col-6"><q-input v-if="!equipment.owned" v-model="equipment.rental_company" outlined dense label="Rental company" /></div>
            <div class="col-6"><q-input v-model.number="equipment.daily_rate" outlined dense type="number" min="0" prefix="$" suffix="/day" label="Daily rate" /></div>
            <div class="col-6"><q-select v-model="equipment.status" outlined dense emit-value map-options :options="equipmentStatusOptions" label="Status" /></div>
            <div class="col-6"><q-input v-model="equipment.next_maintenance_date" outlined dense type="date" stack-label label="Next service" /></div>
            <div class="col-6"><q-select v-model="equipment.project_id" outlined dense emit-value map-options clearable :options="projectOptions" label="On project" /></div>
            <div class="col-12"><q-input v-model="equipment.location" outlined dense label="Location" /></div>
          </q-card-section>
          <q-card-actions class="q-px-md q-pb-md">
            <q-btn v-if="equipmentEditing" flat no-caps color="negative" icon="delete" label="Delete" @click="removeEquipment" />
            <q-space />
            <q-btn flat no-caps label="Cancel" v-close-popup />
            <q-btn unelevated no-caps color="primary" type="submit" label="Save" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { useResourcesStore, type CrewFields, type EquipmentFields } from 'src/stores/resources'
import { useProjectsStore } from 'src/stores/projects'
import type { CrewMember, EquipmentItem } from 'src/types/controls'
import { errorMessage } from 'src/utils/errors'
import { formatCompactCurrency, formatCurrency, formatRelativeDay, isPastDay, parseDate, titleCase } from 'src/utils/format'
import { statusColor } from 'src/utils/status'
import PageHeader from 'src/components/common/PageHeader.vue'
import KpiMetricCard from 'src/components/dashboard/KpiMetricCard.vue'

const $q = useQuasar()
const resources = useResourcesStore()
const projects = useProjectsStore()

const project = computed(() => projects.currentProject)
const scope = ref<'project' | 'all'>(project.value ? 'project' : 'all')
watch(project, p => {
  if (!p) scope.value = 'all'
})
const saving = ref(false)

// "This project" also lists what is free to assign to it.
const crewRows = computed(() =>
  scope.value === 'all' || !project.value
    ? resources.crew
    : resources.crew.filter(m => m.project_id === project.value!.id || (!m.project_id && m.is_available))
)
const equipmentRows = computed(() =>
  scope.value === 'all' || !project.value
    ? resources.equipment
    : resources.equipment.filter(e => e.project_id === project.value!.id || (!e.project_id && e.status === 'available'))
)
const maintenanceDue = computed(() =>
  resources.equipment.filter(e => {
    if (e.status === 'maintenance') return true
    const date = parseDate(e.next_maintenance_date)
    return !!date && (isPastDay(e.next_maintenance_date) || date.getTime() - Date.now() < 14 * 86_400_000)
  })
)

const projectOptions = computed(() => projects.projects.map(p => ({ value: p.id, label: p.name })))
const equipmentStatusOptions = ['available', 'in_use', 'maintenance', 'out_of_service'].map(v => ({ value: v, label: titleCase(v) }))

const crewColumns = [
  { name: 'name', label: 'Name', field: 'name', align: 'left' as const, sortable: true },
  { name: 'hourly_rate', label: 'Rate', field: 'hourly_rate', align: 'right' as const, sortable: true, format: (v: number) => `${formatCurrency(v)}/h` },
  { name: 'project', label: 'On', field: 'project_name', align: 'left' as const, sortable: true },
  { name: 'actions', label: '', field: 'id', align: 'right' as const }
]
const equipmentColumns = [
  { name: 'name', label: 'Equipment', field: 'name', align: 'left' as const, sortable: true },
  { name: 'daily_rate', label: 'Rate', field: 'daily_rate', align: 'right' as const, sortable: true, format: (v: number) => (v ? `${formatCurrency(v)}/day` : '—') },
  { name: 'status', label: 'Status', field: 'status', align: 'left' as const, sortable: true },
  { name: 'project_name', label: 'On', field: 'project_name', align: 'left' as const, format: (v: string | null) => v ?? '—' },
  { name: 'actions', label: '', field: 'id', align: 'right' as const }
]

const fail = (err: unknown, fallback: string) => $q.notify({ type: 'negative', message: errorMessage(err, fallback) })

const assignCrew = (m: CrewMember, projectId: number | null) =>
  resources.saveCrew({ project_id: projectId }, m.id).catch(err => fail(err, 'Could not assign'))

// Equipment in use on a project is "in use"; released, it's available again.
const assignEquipment = (e: EquipmentItem, projectId: number | null) =>
  resources.saveEquipment({ project_id: projectId, status: projectId ? 'in_use' : 'available' }, e.id).catch(err => fail(err, 'Could not assign'))

// --- crew dialog
const crewOpen = ref(false)
const crewEditing = ref<CrewMember | null>(null)
const crew = reactive({ name: '', role: '', phone: '', email: '', hourly_rate: 0, is_available: true, project_id: null as number | null })
const openCrew = (m: CrewMember | null) => {
  crewEditing.value = m
  Object.assign(crew, m
    ? { name: m.name, role: m.role, phone: m.phone ?? '', email: m.email ?? '', hourly_rate: m.hourly_rate, is_available: m.is_available, project_id: m.project_id }
    : { name: '', role: '', phone: '', email: '', hourly_rate: 0, is_available: true, project_id: scope.value === 'project' ? project.value?.id ?? null : null })
  crewOpen.value = true
}
const saveCrew = async () => {
  saving.value = true
  const fields: CrewFields = { ...crew, name: crew.name.trim(), role: crew.role.trim(), phone: crew.phone.trim() || null, email: crew.email.trim() || null, hourly_rate: crew.hourly_rate || 0 }
  try {
    await resources.saveCrew(fields, crewEditing.value?.id)
    crewOpen.value = false
  } catch (err) {
    fail(err, 'Could not save the crew member')
  } finally {
    saving.value = false
  }
}
const removeCrew = () => {
  const m = crewEditing.value
  if (!m) return
  $q.dialog({ title: 'Delete crew member?', message: m.name, cancel: { flat: true, noCaps: true }, ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Delete' } })
    .onOk(() => resources.deleteCrew(m.id).then(() => (crewOpen.value = false)).catch(err => fail(err, 'Could not delete')))
}

// --- equipment dialog
const equipmentOpen = ref(false)
const equipmentEditing = ref<EquipmentItem | null>(null)
const blankEquipment = () => ({
  name: '', equipment_type: '', model: '', serial_number: '', owned: true, rental_company: '', daily_rate: 0,
  status: 'available', next_maintenance_date: '', location: '', project_id: null as number | null
})
const equipment = reactive(blankEquipment())
const openEquipment = (e: EquipmentItem | null) => {
  equipmentEditing.value = e
  Object.assign(equipment, e
    ? {
        name: e.name, equipment_type: e.equipment_type, model: e.model ?? '', serial_number: e.serial_number ?? '', owned: e.owned,
        rental_company: e.rental_company ?? '', daily_rate: e.daily_rate, status: e.status, next_maintenance_date: e.next_maintenance_date ?? '',
        location: e.location ?? '', project_id: e.project_id
      }
    : blankEquipment())
  equipmentOpen.value = true
}
const saveEquipment = async () => {
  saving.value = true
  const text = (v: string) => v.trim() || null
  const fields: EquipmentFields = {
    name: equipment.name.trim(), equipment_type: equipment.equipment_type.trim(), model: text(equipment.model),
    serial_number: text(equipment.serial_number), owned: equipment.owned, rental_company: equipment.owned ? null : text(equipment.rental_company),
    daily_rate: equipment.daily_rate || 0, status: equipment.status as EquipmentFields['status'],
    next_maintenance_date: equipment.next_maintenance_date || null, location: text(equipment.location), project_id: equipment.project_id
  }
  try {
    await resources.saveEquipment(fields, equipmentEditing.value?.id)
    equipmentOpen.value = false
  } catch (err) {
    fail(err, 'Could not save the equipment')
  } finally {
    saving.value = false
  }
}
const removeEquipment = () => {
  const e = equipmentEditing.value
  if (!e) return
  $q.dialog({ title: 'Delete equipment?', message: e.name, cancel: { flat: true, noCaps: true }, ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Delete' } })
    .onOk(() => resources.deleteEquipment(e.id).then(() => (equipmentOpen.value = false)).catch(err => fail(err, 'Could not delete')))
}

onMounted(() => {
  if (!resources.loaded) resources.load().catch(() => undefined)
})
</script>

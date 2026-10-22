<template>
  <q-page class="q-pa-md">
    <div class="page-container">
      <no-project v-if="!project" what="bill of materials" />

      <template v-else>
        <page-header eyebrow="Project controls" title="Materials (BOM)" :subtitle="`${project.name} — quantities, cost and procurement status`" icon="inventory_2">
          <template #actions>
            <q-btn outline no-caps color="primary" icon="download" label="Export CSV" :disable="!materials.items.length" @click="exportCsv" />
            <q-btn unelevated no-caps color="primary" icon="add" label="Add material" @click="openEdit(null)" />
          </template>
        </page-header>

        <div class="row q-col-gutter-md q-mb-md">
          <div class="col-6 col-md-3">
            <kpi-metric-card title="Materials cost" :value="formatCompactCurrency(materials.totalCost)" icon="payments" tone="primary" :caption="`${materials.items.length} line items`" />
          </div>
          <div class="col-6 col-md-3">
            <kpi-metric-card title="On order" :value="materials.countByStatus('ordered')" icon="local_shipping" tone="warning" caption="Ordered, not delivered" />
          </div>
          <div class="col-6 col-md-3">
            <kpi-metric-card title="Delivered / used" :value="materials.countByStatus('delivered') + materials.countByStatus('used')" icon="inventory" tone="positive" caption="On site or installed" />
          </div>
          <div class="col-6 col-md-3">
            <kpi-metric-card title="Shortages" :value="materials.shortages.length" icon="report" :tone="materials.shortages.length ? 'negative' : 'blue-grey-5'" caption="Less on hand than needed, not ordered" />
          </div>
        </div>

        <q-card flat class="app-card">
          <q-card-section class="row q-col-gutter-sm items-center q-pb-none">
            <div class="col-12 col-sm-5">
              <q-input v-model="search" outlined dense clearable placeholder="Search materials or suppliers" debounce="150">
                <template #prepend><q-icon name="search" /></template>
              </q-input>
            </div>
            <div class="col-12 col-sm-3">
              <q-select v-model="statusFilter" outlined dense emit-value map-options clearable :options="statusOptions" label="Status" />
            </div>
            <div class="col text-right text-caption text-muted">Planner quantities include waste; edit any line to match the takeoff.</div>
          </q-card-section>

          <q-table
            :rows="rows"
            :columns="columns"
            row-key="id"
            flat
            :loading="materials.loading"
            :pagination="{ rowsPerPage: 25, sortBy: 'total_cost', descending: true }"
            no-data-label="No materials yet — an AI-generated plan lists them, or add your own"
          >
            <template #body-cell-name="props">
              <q-td :props="props">
                <div class="text-weight-medium">{{ props.row.name }}</div>
                <div class="text-caption text-muted">{{ [titleCase(props.row.material_type), props.row.supplier_name].filter(Boolean).join(' · ') || '—' }}</div>
              </q-td>
            </template>
            <template #body-cell-quantity="props">
              <q-td :props="props" class="tabular">
                {{ formatQty(props.row.quantity_needed) }} {{ props.row.unit }}
                <div v-if="props.row.quantity_available" class="text-caption" :class="props.row.quantity_available < props.row.quantity_needed ? 'text-warning' : 'text-muted'">
                  {{ formatQty(props.row.quantity_available) }} on hand
                </div>
              </q-td>
            </template>
            <template #body-cell-status="props">
              <q-td :props="props">
                <q-btn-dropdown dense flat no-caps size="sm" :color="statusColor('bom', props.row.status)" :label="titleCase(props.row.status)">
                  <q-list dense>
                    <q-item v-for="o in statusOptions" :key="o.value" clickable v-close-popup @click="setStatus(props.row, o.value)">
                      <q-item-section>{{ o.label }}</q-item-section>
                    </q-item>
                  </q-list>
                </q-btn-dropdown>
              </q-td>
            </template>
            <template #body-cell-actions="props">
              <q-td :props="props" auto-width>
                <q-btn flat round dense size="sm" icon="edit" @click="openEdit(props.row)" />
              </q-td>
            </template>
            <template #bottom-row>
              <q-tr v-if="rows.length">
                <q-td colspan="3" class="text-weight-bold">Total{{ rows.length < materials.items.length ? ' (filtered)' : '' }}</q-td>
                <q-td class="text-right text-weight-bold tabular">{{ formatCurrency(rows.reduce((t, r) => t + r.total_cost, 0)) }}</q-td>
                <q-td colspan="2" />
              </q-tr>
            </template>
          </q-table>
        </q-card>

        <q-dialog v-model="editOpen">
          <q-card class="app-card" style="width: 560px; max-width: 96vw">
            <q-card-section class="text-h6 text-weight-bold q-pb-none">{{ editing ? 'Edit material' : 'Add material' }}</q-card-section>
            <q-form @submit.prevent="save">
              <q-card-section class="q-gutter-y-sm">
                <q-input v-model="form.name" outlined dense label="Material *" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space />
                <div class="row q-col-gutter-sm">
                  <div class="col-6"><q-input v-model="form.material_type" outlined dense label="Type" placeholder="wood, concrete…" /></div>
                  <div class="col-6"><q-input v-model="form.unit" outlined dense label="Unit *" placeholder="sq_ft, each…" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space /></div>
                  <div class="col-4"><q-input v-model.number="form.quantity_needed" outlined dense type="number" min="0" label="Needed" /></div>
                  <div class="col-4"><q-input v-model.number="form.quantity_available" outlined dense type="number" min="0" label="On hand" /></div>
                  <div class="col-4"><q-input v-model.number="form.unit_cost" outlined dense type="number" min="0" step="0.01" prefix="$" label="Unit cost" /></div>
                  <div class="col-6"><q-input v-model="form.supplier_name" outlined dense label="Supplier" /></div>
                  <div class="col-6"><q-select v-model="form.status" outlined dense emit-value map-options :options="statusOptions" label="Status" /></div>
                </div>
                <div class="text-caption text-muted">Line total: {{ formatCurrency((form.quantity_needed || 0) * (form.unit_cost || 0)) }}</div>
              </q-card-section>
              <q-card-actions class="q-px-md q-pb-md">
                <q-btn v-if="editing" flat no-caps color="negative" icon="delete" label="Delete" @click="remove" />
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
import { exportFile, useQuasar } from 'quasar'
import { useMaterialsStore } from 'src/stores/materials'
import { useProjectData } from 'src/composables/useProjectData'
import type { BomItem, BomStatus } from 'src/types/controls'
import { errorMessage } from 'src/utils/errors'
import { formatCompactCurrency, formatCurrency, titleCase } from 'src/utils/format'
import { statusColor } from 'src/utils/status'
import PageHeader from 'src/components/common/PageHeader.vue'
import NoProject from 'src/components/common/NoProject.vue'
import KpiMetricCard from 'src/components/dashboard/KpiMetricCard.vue'

const $q = useQuasar()
const materials = useMaterialsStore()
const { project } = useProjectData(id => materials.load(id).catch(() => undefined), () => materials.clear())

const search = ref('')
const statusFilter = ref<BomStatus | null>(null)
const statusOptions: Array<{ value: BomStatus; label: string }> = [
  { value: 'available', label: 'Planned' },
  { value: 'ordered', label: 'Ordered' },
  { value: 'delivered', label: 'Delivered' },
  { value: 'used', label: 'Used' }
]

const rows = computed(() => {
  const q = (search.value ?? '').toLowerCase().trim()
  return materials.items.filter(m =>
    (!statusFilter.value || m.status === statusFilter.value) &&
    (!q || [m.name, m.material_type, m.supplier_name].filter(Boolean).join(' ').toLowerCase().includes(q))
  )
})

const formatQty = (v: number) => (Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 }))

const columns = [
  { name: 'name', label: 'Material', field: 'name', align: 'left' as const, sortable: true },
  { name: 'quantity', label: 'Quantity', field: 'quantity_needed', align: 'left' as const, sortable: true },
  { name: 'unit_cost', label: 'Unit cost', field: 'unit_cost', align: 'right' as const, sortable: true, format: (v: number) => formatCurrency(v), classes: 'tabular' },
  { name: 'total_cost', label: 'Total', field: 'total_cost', align: 'right' as const, sortable: true, format: (v: number) => formatCurrency(v), classes: 'tabular text-weight-medium' },
  { name: 'status', label: 'Status', field: 'status', align: 'left' as const, sortable: true },
  { name: 'actions', label: '', field: 'id', align: 'right' as const }
]

const fail = (err: unknown, fallback: string) => $q.notify({ type: 'negative', message: errorMessage(err, fallback) })

const setStatus = async (row: BomItem, status: BomStatus) => {
  if (row.status === status) return
  try {
    await materials.update(row.id, { status })
  } catch (err) {
    fail(err, 'Could not update the status')
  }
}

const editOpen = ref(false)
const editing = ref<BomItem | null>(null)
const saving = ref(false)
const blank = () => ({ name: '', material_type: '', unit: 'each', quantity_needed: 0, quantity_available: 0, unit_cost: 0, supplier_name: '', status: 'available' as BomStatus })
const form = reactive(blank())

const openEdit = (row: BomItem | null) => {
  editing.value = row
  Object.assign(form, row
    ? { name: row.name, material_type: row.material_type ?? '', unit: row.unit ?? 'each', quantity_needed: row.quantity_needed, quantity_available: row.quantity_available, unit_cost: row.unit_cost, supplier_name: row.supplier_name ?? '', status: row.status }
    : blank())
  editOpen.value = true
}

const save = async () => {
  saving.value = true
  const fields = {
    ...form,
    name: form.name.trim(),
    unit: form.unit.trim(),
    material_type: form.material_type.trim() || null,
    supplier_name: form.supplier_name.trim() || null,
    quantity_needed: form.quantity_needed || 0,
    quantity_available: form.quantity_available || 0,
    unit_cost: form.unit_cost || 0
  }
  try {
    if (editing.value) await materials.update(editing.value.id, fields)
    else await materials.add(fields)
    editOpen.value = false
  } catch (err) {
    fail(err, 'Could not save the material')
  } finally {
    saving.value = false
  }
}

const remove = () => {
  const row = editing.value
  if (!row) return
  $q.dialog({
    title: 'Delete material?',
    message: row.name,
    cancel: { flat: true, noCaps: true },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Delete' }
  }).onOk(async () => {
    try {
      await materials.remove(row.id)
      editOpen.value = false
    } catch (err) {
      fail(err, 'Could not delete the material')
    }
  })
}

const exportCsv = () => {
  const cell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const header = ['Material', 'Type', 'Quantity needed', 'On hand', 'Unit', 'Unit cost', 'Total', 'Supplier', 'Status']
  const lines = materials.items.map(m =>
    [m.name, m.material_type, m.quantity_needed, m.quantity_available, m.unit, m.unit_cost.toFixed(2), m.total_cost.toFixed(2), m.supplier_name, m.status]
      .map(cell).join(',')
  )
  const name = (project.value?.name ?? 'project').replace(/[^\w-]+/g, '_')
  const ok = exportFile(`${name}_bill_of_materials.csv`, [header.map(cell).join(','), ...lines].join('\r\n'), 'text/csv')
  if (ok !== true) $q.notify({ type: 'negative', message: 'The browser blocked the download' })
}
</script>

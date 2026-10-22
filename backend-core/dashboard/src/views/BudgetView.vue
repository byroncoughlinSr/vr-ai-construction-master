<template>
  <q-page class="q-pa-md">
    <div class="page-container">
      <no-project v-if="!project" what="budget" />

      <template v-else>
        <page-header eyebrow="Project controls" title="Budget & cost" :subtitle="`${project.name} — earned value, expenses and change orders`" icon="account_balance_wallet">
          <template #actions>
            <q-btn outline no-caps color="primary" icon="request_quote" label="Change order" @click="openChangeOrder(null)" />
            <q-btn unelevated no-caps color="primary" icon="add" label="Log expense" @click="expenseOpen = true" />
          </template>
        </page-header>

        <q-banner v-if="budget.error" rounded class="banner-error q-mb-md">
          {{ budget.error }}
          <template #action><q-btn flat no-caps label="Retry" @click="budget.reload()" /></template>
        </q-banner>

        <template v-if="sum">
          <div class="row q-col-gutter-md q-mb-md">
            <div class="col-6 col-md">
              <kpi-metric-card title="Contract (BAC)" :value="formatCompactCurrency(sum.bac)" icon="description" tone="primary"
                :caption="sum.approved_change_orders ? `${formatCompactCurrency(sum.baseline)} + ${formatCompactCurrency(sum.approved_change_orders)} in change orders` : 'Phase budgets from the plan'"
                hint="Budget at completion: the phases' budgets plus approved change orders." />
            </div>
            <div class="col-6 col-md">
              <kpi-metric-card title="Actual cost (AC)" :value="formatCompactCurrency(sum.actual_cost)" icon="receipt_long" tone="secondary"
                :progress="sum.percent_spent" :caption="`${formatPercent(sum.percent_spent)} of BAC${sum.unpaid ? ` · ${formatCompactCurrency(sum.unpaid)} unpaid` : ''}`" />
            </div>
            <div class="col-6 col-md">
              <kpi-metric-card title="CPI" :value="formatIndex(sum.cpi)" icon="speed" :tone="indexColor(sum.cpi)" :value-color="sum.cpi != null ? indexColor(sum.cpi) : undefined"
                :caption="sum.cpi != null ? `${formatCompactCurrency(Math.abs(sum.cost_variance))} ${sum.cost_variance >= 0 ? 'under' : 'over'} for the work done` : 'Needs logged expenses'"
                hint="Cost performance = earned value ÷ actual cost. 1.00 is on budget." />
            </div>
            <div class="col-6 col-md">
              <kpi-metric-card title="SPI" :value="formatIndex(sum.spi)" icon="timer" :tone="indexColor(sum.spi)" :value-color="sum.spi != null ? indexColor(sum.spi) : undefined"
                :caption="sum.spi != null ? (sum.spi >= 1 ? 'Ahead of or on plan' : 'Behind plan') : 'Needs a baselined schedule'"
                hint="Schedule performance = earned value ÷ planned value. Below 1.00 less work is done than planned by today." />
            </div>
            <div class="col-12 col-md">
              <kpi-metric-card title="Forecast (EAC)" :value="formatCompactCurrency(sum.eac)" icon="query_stats" :tone="sum.vac < 0 ? 'negative' : 'positive'"
                :caption="`${formatCompactCurrency(Math.abs(sum.vac))} ${sum.vac >= 0 ? 'under' : 'over'} budget at completion`"
                hint="Estimate at completion = BAC ÷ CPI: where the project lands if costs keep running as they have." />
            </div>
          </div>

          <q-banner v-if="sum.target_budget && sum.eac > sum.target_budget" rounded class="banner-warning q-mb-md">
            <template #avatar><q-icon name="warning" /></template>
            The forecast ({{ formatCurrency(sum.eac) }}) is above the client's target budget of {{ formatCurrency(sum.target_budget) }}.
          </q-banner>

          <q-card flat class="app-card">
            <q-tabs v-model="tab" dense no-caps align="left" active-color="primary" indicator-color="primary" class="q-px-sm">
              <q-tab name="phases" icon="stacked_bar_chart" label="By phase" />
              <q-tab name="expenses" icon="receipt" :label="`Expenses (${budget.expenses.length})`" />
              <q-tab name="change_orders" icon="published_with_changes">
                <div class="row items-center no-wrap q-gutter-x-xs">
                  <span>Change orders</span>
                  <q-badge v-if="budget.pendingChangeOrders.length" color="warning" :label="budget.pendingChangeOrders.length" />
                </div>
              </q-tab>
            </q-tabs>
            <q-separator />

            <q-tab-panels v-model="tab" animated class="bg-transparent">
              <q-tab-panel name="phases">
                <div class="row q-col-gutter-lg">
                  <div class="col-12 col-md-7">
                    <q-table :rows="sum.by_phase" :columns="phaseColumns" row-key="phase_id" flat dense hide-pagination :pagination="{ rowsPerPage: 0 }">
                      <template #body-cell-actual="props">
                        <q-td :props="props" :class="props.row.actual > props.row.earned && props.row.actual ? 'text-negative text-weight-medium' : ''">
                          {{ formatCurrency(props.row.actual) }}
                        </q-td>
                      </template>
                      <template #bottom-row>
                        <q-tr class="text-weight-bold">
                          <q-td>Total</q-td>
                          <q-td class="text-right tabular">{{ formatCurrency(sum.baseline) }}</q-td>
                          <q-td class="text-right tabular">{{ formatCurrency(sum.earned_value) }}</q-td>
                          <q-td class="text-right tabular">{{ formatCurrency(phaseActualTotal) }}</q-td>
                        </q-tr>
                      </template>
                    </q-table>
                    <div class="text-caption text-muted q-mt-sm">
                      Earned = the phase's budget × its earned progress. Actual counts expenses logged against the phase{{
                        sum.actual_cost > phaseActualTotal ? ` (${formatCurrency(sum.actual_cost - phaseActualTotal)} is logged without a phase)` : '' }}.
                    </div>
                  </div>
                  <div class="col-12 col-md-5">
                    <div class="text-subtitle2 q-mb-sm">Spend by category</div>
                    <bar-chart
                      v-if="sum.by_category.length"
                      :labels="categoryRows.map(c => c.label)"
                      :series="[{ label: 'Spent', data: categoryRows.map(c => c.actual) }]"
                      :height="Math.max(140, categoryRows.length * 40 + 30)"
                      aria-label="Actual spend by category"
                    />
                    <empty-state v-else dense icon="receipt" title="Nothing spent yet" message="Logged expenses show up here by category." />
                  </div>
                </div>
              </q-tab-panel>

              <q-tab-panel name="expenses" class="q-pa-none">
                <q-table :rows="budget.expenses" :columns="expenseColumns" row-key="id" flat :pagination="{ rowsPerPage: 20 }" no-data-label="No expenses logged yet">
                  <template #body-cell-vendor="props">
                    <q-td :props="props">
                      <div class="text-weight-medium">{{ props.row.vendor }}</div>
                      <div v-if="props.row.description" class="text-caption text-muted ellipsis" style="max-width: 280px">{{ props.row.description }}</div>
                    </q-td>
                  </template>
                  <template #body-cell-status="props">
                    <q-td :props="props"><q-badge :color="statusColor('expense', props.row.status)" :label="titleCase(props.row.status)" /></q-td>
                  </template>
                  <template #body-cell-actions="props">
                    <q-td :props="props" auto-width>
                      <q-btn flat round dense size="sm" icon="delete" @click="removeExpense(props.row)"><q-tooltip>Delete</q-tooltip></q-btn>
                    </q-td>
                  </template>
                </q-table>
              </q-tab-panel>

              <q-tab-panel name="change_orders" class="q-pa-none">
                <div class="q-px-md q-pt-sm text-caption text-muted">
                  Approved {{ formatCurrency(sum.approved_change_orders) }} (in the contract value) · awaiting approval {{ formatCurrency(sum.pending_change_orders) }}
                </div>
                <q-table :rows="budget.changeOrders" :columns="coColumns" row-key="id" flat :pagination="{ rowsPerPage: 20 }" no-data-label="No change orders yet">
                  <template #body-cell-title="props">
                    <q-td :props="props">
                      <div class="text-weight-medium">{{ props.row.title }}</div>
                      <div class="text-caption text-muted">
                        {{ props.row.requested_by || '—' }}<template v-if="props.row.floor_plan_version"> · floor plan v{{ props.row.floor_plan_version }}</template>
                      </div>
                    </q-td>
                  </template>
                  <template #body-cell-status="props">
                    <q-td :props="props"><q-badge :color="statusColor('changeOrder', props.row.status)" :label="titleCase(props.row.status)" /></q-td>
                  </template>
                  <template #body-cell-actions="props">
                    <q-td :props="props" auto-width>
                      <div class="row no-wrap q-gutter-xs">
                        <template v-if="props.row.status === 'submitted' || props.row.status === 'draft'">
                          <q-btn unelevated dense no-caps size="sm" color="positive" label="Approve" class="q-px-sm" @click="decide(props.row, 'approved')" />
                          <q-btn flat dense no-caps size="sm" color="negative" label="Reject" @click="decide(props.row, 'rejected')" />
                        </template>
                        <q-btn flat round dense size="sm" icon="edit" @click="openChangeOrder(props.row)" />
                      </div>
                    </q-td>
                  </template>
                </q-table>
              </q-tab-panel>
            </q-tab-panels>
          </q-card>
        </template>
        <div v-else-if="budget.loading" class="flex flex-center q-pa-xl"><q-spinner size="40px" color="primary" /></div>

        <!-- Expense -->
        <q-dialog v-model="expenseOpen" @show="resetExpense">
          <q-card class="app-card" style="width: 520px; max-width: 96vw">
            <q-card-section class="text-h6 text-weight-bold q-pb-none">Log an expense</q-card-section>
            <q-form @submit.prevent="saveExpense">
              <q-card-section class="q-gutter-y-sm">
                <q-input v-model="expense.vendor" outlined dense label="Vendor / subcontractor *" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space />
                <div class="row q-col-gutter-sm">
                  <div class="col-6"><q-input v-model.number="expense.amount" outlined dense type="number" min="0" step="0.01" prefix="$" label="Amount *" :rules="[v => v > 0 || 'More than 0']" hide-bottom-space /></div>
                  <div class="col-6"><q-select v-model="expense.category" outlined dense emit-value map-options :options="categoryOptions" label="Category" /></div>
                  <div class="col-6"><q-select v-model="expense.phase_id" outlined dense emit-value map-options clearable :options="phaseOptions" label="Phase" /></div>
                  <div class="col-6"><q-input v-model="expense.incurred_on" outlined dense type="date" stack-label label="Date" /></div>
                  <div class="col-6"><q-input v-model="expense.invoice_number" outlined dense label="Invoice / PO #" /></div>
                  <div class="col-6"><q-select v-model="expense.status" outlined dense emit-value map-options :options="[{ value: 'paid', label: 'Paid' }, { value: 'pending', label: 'Unpaid' }]" label="Status" /></div>
                </div>
                <q-input v-model="expense.description" outlined dense autogrow label="Description" />
              </q-card-section>
              <q-card-actions align="right" class="q-px-md q-pb-md">
                <q-btn flat no-caps label="Cancel" v-close-popup />
                <q-btn unelevated no-caps color="primary" type="submit" label="Log expense" :loading="saving" />
              </q-card-actions>
            </q-form>
          </q-card>
        </q-dialog>

        <!-- Change order -->
        <q-dialog v-model="coOpen">
          <q-card class="app-card" style="width: 540px; max-width: 96vw">
            <q-card-section class="text-h6 text-weight-bold q-pb-none">{{ coEditing ? `Edit ${coEditing.code}` : 'New change order' }}</q-card-section>
            <q-form @submit.prevent="saveChangeOrder">
              <q-card-section class="q-gutter-y-sm">
                <q-input v-model="co.title" outlined dense label="What changes *" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space />
                <q-input v-model="co.description" outlined dense autogrow label="Scope" />
                <div class="row q-col-gutter-sm">
                  <div class="col-6"><q-input v-model.number="co.cost_impact" outlined dense type="number" prefix="$" label="Cost impact" hint="Negative for a credit" /></div>
                  <div class="col-6"><q-input v-model.number="co.schedule_impact_days" outlined dense type="number" suffix="days" label="Schedule impact" /></div>
                </div>
                <q-input v-model="co.requested_by" outlined dense label="Requested by" />
              </q-card-section>
              <q-card-actions align="right" class="q-px-md q-pb-md">
                <q-btn flat no-caps label="Cancel" v-close-popup />
                <q-btn unelevated no-caps color="primary" type="submit" :label="coEditing ? 'Save' : 'Submit for approval'" :loading="saving" />
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
import { useBudgetStore, type ChangeOrderFields, type ExpenseFields } from 'src/stores/budget'
import { useScheduleStore } from 'src/stores/schedule'
import { useProjectsStore } from 'src/stores/projects'
import { useProjectData } from 'src/composables/useProjectData'
import type { ChangeOrder, ChangeOrderStatus, Expense, ExpenseCategory } from 'src/types/controls'
import { errorMessage } from 'src/utils/errors'
import { formatCompactCurrency, formatCurrency, formatDate, formatIndex, formatPercent, titleCase, todayIso } from 'src/utils/format'
import { indexColor, statusColor } from 'src/utils/status'
import PageHeader from 'src/components/common/PageHeader.vue'
import EmptyState from 'src/components/common/EmptyState.vue'
import NoProject from 'src/components/common/NoProject.vue'
import KpiMetricCard from 'src/components/dashboard/KpiMetricCard.vue'
import BarChart from 'src/components/charts/BarChart.vue'

const $q = useQuasar()
const budget = useBudgetStore()
const schedule = useScheduleStore()
const projects = useProjectsStore()
const { project } = useProjectData(
  id => Promise.all([budget.load(id), schedule.projectId === id ? null : schedule.load(id)]).catch(() => undefined),
  () => budget.clear()
)

const sum = computed(() => budget.summary)
const tab = ref<'phases' | 'expenses' | 'change_orders'>('phases')
const saving = ref(false)

const CATEGORIES: ExpenseCategory[] = ['labor', 'materials', 'equipment', 'subcontract', 'permits', 'other']
const categoryOptions = CATEGORIES.map(c => ({ value: c, label: titleCase(c) }))
const phaseOptions = computed(() => schedule.phases.map(p => ({ value: p.id, label: p.name })))
const phaseActualTotal = computed(() => (sum.value?.by_phase ?? []).reduce((t, p) => t + p.actual, 0))
const categoryRows = computed(() =>
  [...(sum.value?.by_category ?? [])].sort((a, b) => b.actual - a.actual).map(c => ({ label: titleCase(c.category), actual: c.actual }))
)

const money = (v: number) => formatCurrency(v)
const phaseColumns = [
  { name: 'name', label: 'Phase', field: 'name', align: 'left' as const },
  { name: 'budgeted', label: 'Budgeted', field: 'budgeted', align: 'right' as const, format: money, classes: 'tabular' },
  { name: 'earned', label: 'Earned', field: 'earned', align: 'right' as const, format: money, classes: 'tabular' },
  { name: 'actual', label: 'Actual', field: 'actual', align: 'right' as const, classes: 'tabular' }
]
const expenseColumns = [
  { name: 'date', label: 'Date', field: 'date', align: 'left' as const, sortable: true, format: formatDate },
  { name: 'vendor', label: 'Vendor', field: 'vendor', align: 'left' as const, sortable: true },
  { name: 'category', label: 'Category', field: 'category', align: 'left' as const, sortable: true, format: titleCase },
  { name: 'phase_name', label: 'Phase', field: 'phase_name', align: 'left' as const, format: (v: string | null) => v ?? '—' },
  { name: 'invoice_number', label: 'Invoice', field: 'invoice_number', align: 'left' as const, format: (v: string | null) => v ?? '—' },
  { name: 'amount', label: 'Amount', field: 'amount', align: 'right' as const, sortable: true, format: money, classes: 'tabular' },
  { name: 'status', label: 'Status', field: 'status', align: 'left' as const },
  { name: 'actions', label: '', field: 'id', align: 'right' as const }
]
const coColumns = [
  { name: 'code', label: '#', field: 'code', align: 'left' as const, sortable: true },
  { name: 'title', label: 'Change', field: 'title', align: 'left' as const },
  { name: 'cost_impact', label: 'Cost', field: 'cost_impact', align: 'right' as const, sortable: true, format: money, classes: 'tabular' },
  { name: 'schedule_impact_days', label: 'Days', field: 'schedule_impact_days', align: 'right' as const, format: (v: number) => (v ? `${v > 0 ? '+' : ''}${v}` : '—') },
  { name: 'status', label: 'Status', field: 'status', align: 'left' as const },
  { name: 'actions', label: '', field: 'id', align: 'right' as const }
]

const fail = (err: unknown, fallback: string) => $q.notify({ type: 'negative', message: errorMessage(err, fallback) })
const afterChange = () => projects.fetchOverview()

// --- expenses
const expense = reactive<ExpenseFields>({ vendor: '', amount: 0, category: 'materials', status: 'paid' })
const expenseOpen = ref(false)
const resetExpense = () => Object.assign(expense, {
  vendor: '', amount: 0, category: 'materials', status: 'paid', description: '', invoice_number: '',
  incurred_on: todayIso(), phase_id: schedule.schedule?.current_phase?.id ?? null
})
const saveExpense = async () => {
  saving.value = true
  try {
    await budget.addExpense({ ...expense, vendor: expense.vendor.trim(), description: expense.description?.trim() || null, invoice_number: expense.invoice_number?.trim() || null })
    expenseOpen.value = false
    $q.notify({ type: 'positive', message: 'Expense logged' })
    afterChange()
  } catch (err) {
    fail(err, 'Could not log the expense')
  } finally {
    saving.value = false
  }
}
const removeExpense = (row: Expense) => {
  $q.dialog({
    title: 'Delete expense?',
    message: `${row.vendor}, ${formatCurrency(row.amount)}`,
    cancel: { flat: true, noCaps: true },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Delete' }
  }).onOk(() => budget.deleteExpense(row.id).then(afterChange).catch(err => fail(err, 'Could not delete the expense')))
}

// --- change orders
const coOpen = ref(false)
const coEditing = ref<ChangeOrder | null>(null)
const co = reactive<ChangeOrderFields>({ title: '', description: '', cost_impact: 0, schedule_impact_days: 0, requested_by: '' })
const openChangeOrder = (row: ChangeOrder | null) => {
  coEditing.value = row
  Object.assign(co, row
    ? { title: row.title, description: row.description ?? '', cost_impact: row.cost_impact, schedule_impact_days: row.schedule_impact_days, requested_by: row.requested_by ?? '' }
    : { title: '', description: '', cost_impact: 0, schedule_impact_days: 0, requested_by: '' })
  coOpen.value = true
}
const saveChangeOrder = async () => {
  saving.value = true
  const fields = { ...co, title: co.title.trim(), description: co.description?.trim() || null, requested_by: co.requested_by?.trim() || null }
  try {
    if (coEditing.value) await budget.updateChangeOrder(coEditing.value.id, fields)
    else await budget.addChangeOrder(fields)
    coOpen.value = false
    tab.value = 'change_orders'
    afterChange()
  } catch (err) {
    fail(err, 'Could not save the change order')
  } finally {
    saving.value = false
  }
}
const decide = async (row: ChangeOrder, status: ChangeOrderStatus) => {
  try {
    await budget.updateChangeOrder(row.id, { status })
    $q.notify({ type: status === 'approved' ? 'positive' : 'info', message: `${row.code} ${status}` })
    afterChange()
  } catch (err) {
    fail(err, 'Could not update the change order')
  }
}
</script>

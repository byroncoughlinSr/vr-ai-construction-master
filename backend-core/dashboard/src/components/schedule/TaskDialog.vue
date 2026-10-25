<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" @show="fill">
    <q-card class="app-card" style="width: 560px; max-width: 96vw">
      <q-card-section class="row items-center no-wrap q-pb-none">
        <div class="col">
          <div class="text-h6 text-weight-bold">{{ task ? 'Edit task' : 'New task' }}</div>
          <div class="text-caption text-muted">{{ phaseName }}</div>
        </div>
        <q-btn flat round dense icon="close" v-close-popup />
      </q-card-section>
      <q-form @submit.prevent="save">
        <q-card-section class="q-gutter-y-sm">
          <q-input v-model="form.name" outlined dense label="Task *" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space />
          <q-input v-model="form.description" outlined dense autogrow label="Scope / notes" />
          <div class="row q-col-gutter-sm">
            <div v-if="task" class="col-12 col-sm-6">
              <q-select v-model="form.status" outlined dense emit-value map-options :options="TASK_STATUS_OPTIONS" label="Status" />
            </div>
            <div class="col-12 col-sm-6">
              <q-select v-model="form.priority" outlined dense emit-value map-options :options="PRIORITY_OPTIONS" label="Priority" />
            </div>
            <div class="col-6 col-sm-4">
              <q-input v-model.number="form.duration" outlined dense type="number" min="0.5" step="0.5" suffix="days" label="Duration" />
            </div>
            <div class="col-6 col-sm-4">
              <q-input v-model="form.start" outlined dense type="date" stack-label label="Planned start" />
            </div>
            <div class="col-6 col-sm-4">
              <q-input v-model="form.end" outlined dense type="date" stack-label label="Planned finish" />
            </div>
            <div class="col-6 col-sm-6">
              <q-input v-model.number="form.budgeted" outlined dense type="number" min="0" prefix="$" label="Budgeted cost" />
            </div>
            <div v-if="task" class="col-6 col-sm-6">
              <q-input v-model.number="form.actual" outlined dense type="number" min="0" prefix="$" label="Actual cost" hint="Log invoices as expenses for the budget" />
            </div>
          </div>
          <q-toggle v-model="form.inspection" label="Needs an inspection">
            <q-tooltip>The task can only be completed once its inspection passes (Permits &amp; inspections)</q-tooltip>
          </q-toggle>
        </q-card-section>
        <q-card-section v-if="error" class="q-pt-none">
          <q-banner rounded dense class="banner-error">{{ error }}</q-banner>
        </q-card-section>
        <q-card-actions class="q-px-md q-pb-md">
          <q-btn v-if="task" flat no-caps color="negative" icon="delete" label="Delete" @click="remove" />
          <q-space />
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" type="submit" :label="task ? 'Save' : 'Add task'" :loading="saving" />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useScheduleStore, type TaskFields } from 'src/stores/schedule'
import type { ScheduleTask, TaskPriority, TaskStatus } from 'src/types/controls'
import { errorMessage } from 'src/utils/errors'
import { PRIORITY_OPTIONS, TASK_STATUS_OPTIONS } from 'src/utils/status'

const props = defineProps<{ modelValue: boolean; phaseId: number | null; phaseName?: string; task?: ScheduleTask | null }>()
const emit = defineEmits<{ (e: 'update:modelValue', open: boolean): void }>()

const $q = useQuasar()
const schedule = useScheduleStore()
const saving = ref(false)
const error = ref<string | null>(null)
const form = reactive({
  name: '', description: '', status: 'pending' as TaskStatus, priority: 'medium' as TaskPriority,
  duration: 1, start: '', end: '', budgeted: 0, actual: 0, inspection: false
})

const fill = () => {
  error.value = null
  const t = props.task
  Object.assign(form, t
    ? {
        name: t.name, description: t.description ?? '', status: t.status, priority: t.priority,
        duration: t.duration_days, start: t.planned_start ?? '', end: t.planned_end ?? '',
        budgeted: t.budgeted_cost, actual: t.actual_cost, inspection: t.requires_inspection
      }
    : { name: '', description: '', status: 'pending', priority: 'medium', duration: 1, start: '', end: '', budgeted: 0, actual: 0, inspection: false })
}

const save = async () => {
  saving.value = true
  error.value = null
  const fields: TaskFields = {
    name: form.name.trim(),
    description: form.description.trim() || null,
    priority: form.priority,
    planned_duration_days: form.duration > 0 ? form.duration : 1,
    planned_start_date: form.start || null,
    planned_end_date: form.end || null,
    budgeted_cost: form.budgeted || 0,
    requires_inspection: form.inspection
  }
  try {
    if (props.task) {
      await schedule.updateTask(props.task.id, { ...fields, status: form.status, actual_cost: form.actual || 0 })
    } else if (props.phaseId) {
      await schedule.addTask(props.phaseId, fields as TaskFields & { name: string })
    }
    emit('update:modelValue', false)
  } catch (err) {
    error.value = errorMessage(err, 'Could not save the task')
  } finally {
    saving.value = false
  }
}

const remove = () => {
  const task = props.task
  if (!task) return
  $q.dialog({
    title: 'Delete task?',
    message: `“${task.name}” is removed from the schedule and the phase's progress is re-earned.`,
    cancel: { flat: true, noCaps: true },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Delete' }
  }).onOk(async () => {
    try {
      await schedule.deleteTask(task.id)
      emit('update:modelValue', false)
    } catch (err) {
      error.value = errorMessage(err, 'Could not delete the task')
    }
  })
}
</script>

<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" @show="fill">
    <q-card class="app-card" style="width: 560px; max-width: 96vw">
      <q-card-section class="row items-center no-wrap q-pb-none">
        <div class="text-h6 text-weight-bold col">Project details</div>
        <q-btn flat round dense icon="close" v-close-popup />
      </q-card-section>
      <q-form @submit.prevent="save">
        <q-card-section class="q-gutter-y-sm">
          <q-input v-model="form.name" outlined dense label="Name *" :rules="[v => !!(v && v.trim()) || 'Required']" />
          <q-input v-model="form.address" outlined dense label="Site address" />
          <div class="row q-col-gutter-sm">
            <div class="col-12 col-sm-6">
              <q-select v-model="form.status" outlined dense emit-value map-options :options="PROJECT_STATUS_OPTIONS" label="Status" />
            </div>
            <div class="col-12 col-sm-6">
              <q-input v-model.number="form.budget" outlined dense type="number" min="0" prefix="$" label="Target budget" />
            </div>
            <div class="col-12 col-sm-6">
              <q-input v-model="form.start" outlined dense type="date" stack-label label="Start" />
            </div>
            <div class="col-12 col-sm-6">
              <q-input v-model="form.finish" outlined dense type="date" stack-label label="Target completion" />
            </div>
          </div>
          <q-input v-model="form.description" outlined dense autogrow label="Brief" />
          <div class="text-caption text-muted">Renaming here doesn't rename the house's floor plan; rename it in the Design studio to change both.</div>
        </q-card-section>
        <q-card-section v-if="error" class="q-pt-none">
          <q-banner rounded dense class="banner-error">{{ error }}</q-banner>
        </q-card-section>
        <q-card-actions class="q-px-md q-pb-md">
          <q-btn flat no-caps color="negative" icon="delete" label="Delete project" @click="remove" />
          <q-space />
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" type="submit" label="Save" :loading="saving" />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useProjectsStore } from 'src/stores/projects'
import { errorMessage } from 'src/utils/errors'
import { PROJECT_STATUS_OPTIONS } from 'src/utils/status'

const props = defineProps<{ modelValue: boolean; projectId: number }>()
const emit = defineEmits<{ (e: 'update:modelValue', open: boolean): void }>()

const $q = useQuasar()
const projects = useProjectsStore()
const saving = ref(false)
const error = ref<string | null>(null)
const form = reactive({ name: '', address: '', status: 'planning', budget: null as number | null, start: '', finish: '', description: '' })

const day = (value: string | null | undefined) => (value ? value.slice(0, 10) : '')

const fill = () => {
  error.value = null
  const raw = projects.raw[props.projectId]
  if (!raw) return
  Object.assign(form, {
    name: raw.name,
    address: raw.address ?? '',
    status: raw.status ?? 'planning',
    budget: raw.budget,
    start: day(raw.start_date),
    finish: day(raw.estimated_completion_date),
    description: raw.description ?? ''
  })
}

const save = async () => {
  saving.value = true
  error.value = null
  try {
    await projects.updateProject(props.projectId, {
      name: form.name.trim(),
      address: form.address.trim() || null,
      status: form.status,
      budget: form.budget || null,
      start_date: form.start ? `${form.start}T00:00:00` : null,
      estimated_completion_date: form.finish ? `${form.finish}T00:00:00` : null,
      description: form.description.trim() || null
    })
    $q.notify({ type: 'positive', message: 'Project saved' })
    emit('update:modelValue', false)
    projects.fetchOverview()
  } catch (err) {
    error.value = errorMessage(err, 'Could not save the project')
  } finally {
    saving.value = false
  }
}

const remove = () => {
  const name = projects.raw[props.projectId]?.name ?? 'this project'
  $q.dialog({
    title: 'Delete project?',
    message: `“${name}” is deleted with its floor plans, schedule, budget, permits and materials. Linked clients stay in the CRM. This can't be undone.`,
    options: {
      type: 'checkbox',
      model: [],
      items: [{
        label: 'Delete completely: also remove its construction plan from the shared pm-mcp board (otherwise archived there) and its rendered images',
        value: 'purge'
      }]
    },
    cancel: { flat: true, noCaps: true },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Delete' },
    persistent: true
  }).onOk(async (choices: string[]) => {
    const purge = choices.includes('purge')
    try {
      await projects.deleteProject(props.projectId, purge)
      emit('update:modelValue', false)
      $q.notify({ type: 'positive', message: `Deleted “${name}”${purge ? ' completely' : ''}` })
    } catch (err) {
      $q.notify({ type: 'negative', message: errorMessage(err, 'Could not delete the project') })
    }
  })
}
</script>

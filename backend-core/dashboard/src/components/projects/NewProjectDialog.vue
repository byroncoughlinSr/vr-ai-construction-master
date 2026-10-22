<template>
  <q-dialog v-model="ui.newProjectOpen" :persistent="busy" @show="onShow">
    <q-card class="app-card" style="width: 620px; max-width: 96vw">
      <q-card-section class="row items-center no-wrap q-pb-none">
        <div class="col">
          <div class="text-h6 text-weight-bold">New project</div>
          <div v-if="client" class="text-caption text-muted">For {{ client.name }} — the project is linked to their CRM record</div>
        </div>
        <q-btn flat round dense icon="close" :disable="busy" v-close-popup />
      </q-card-section>

      <q-tabs v-model="mode" dense align="left" active-color="primary" indicator-color="primary" class="q-px-md q-mt-sm" :class="{ 'disabled no-pointer-events': busy }">
        <q-tab name="ai" icon="auto_awesome" label="Generate with AI" no-caps />
        <q-tab name="blank" icon="edit_note" label="Blank project" no-caps />
      </q-tabs>
      <q-separator />

      <q-form @submit.prevent="submit">
        <q-card-section v-if="mode === 'ai'" class="q-gutter-y-md">
          <div class="text-body2 text-muted">
            Describe the house. The AI planner drafts the floor plan (walkable in VR), construction phases and tasks with
            costs and durations, and a bill of materials. It usually takes one to three minutes.
          </div>
          <q-input
            v-model="prompt"
            outlined
            autogrow
            :input-style="{ minHeight: '110px' }"
            label="Describe the house"
            placeholder="A 3-bedroom single-story craftsman, about 2,000 sq ft, open kitchen and living room, mudroom off the garage, covered back porch…"
            :disable="busy"
            :rules="[v => (v && v.trim().length >= 15) || 'A sentence or two, please']"
          />
          <q-input
            v-model.number="budget"
            outlined
            dense
            type="number"
            min="0"
            prefix="$"
            label="Target budget (optional)"
            :disable="busy"
            style="max-width: 260px"
          />
          <q-banner v-if="busy" rounded class="bg-surface-2 border-app">
            <template #avatar><q-spinner-dots color="primary" size="28px" /></template>
            Planning the house… you can keep this open; the project is selected when it is ready.
          </q-banner>
        </q-card-section>

        <q-card-section v-else class="q-gutter-y-sm">
          <q-input v-model="name" outlined dense label="Project name *" :disable="busy" :rules="[v => !!(v && v.trim()) || 'Required']" />
          <q-input v-model="address" outlined dense label="Site address" :disable="busy" />
          <div class="row q-col-gutter-sm">
            <div class="col-12 col-sm-6">
              <q-input v-model.number="budget" outlined dense type="number" min="0" prefix="$" label="Target budget" :disable="busy" />
            </div>
            <div class="col-12 col-sm-6">
              <q-input v-model="startDate" outlined dense type="date" stack-label label="Planned start" :disable="busy" />
            </div>
          </div>
          <q-input v-model="description" outlined dense autogrow label="Brief" :disable="busy" />
          <div class="text-caption text-muted">
            A blank project has no floor plan yet; describe the house in the headset, or start with AI instead.
          </div>
        </q-card-section>

        <q-card-section v-if="error" class="q-pt-none">
          <q-banner rounded dense class="banner-error">{{ error }}</q-banner>
        </q-card-section>

        <q-card-actions align="right" class="q-px-md q-pb-md">
          <q-btn flat no-caps label="Cancel" :disable="busy" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            type="submit"
            :icon="mode === 'ai' ? 'auto_awesome' : 'add'"
            :label="mode === 'ai' ? 'Generate project' : 'Create project'"
            :loading="busy"
          />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { useProjectsStore } from 'src/stores/projects'
import { useCrmStore } from 'src/stores/crm'
import { useUiStore } from 'src/stores/ui'
import { errorMessage } from 'src/utils/errors'

const $q = useQuasar()
const router = useRouter()
const ui = useUiStore()
const projects = useProjectsStore()
const crm = useCrmStore()

const mode = ref<'ai' | 'blank'>('ai')
const prompt = ref('')
const name = ref('')
const address = ref('')
const description = ref('')
const startDate = ref('')
const budget = ref<number | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)

const client = computed(() =>
  ui.newProjectClientId ? crm.clients.find(c => c.id === ui.newProjectClientId) ?? null : null
)

// Start from the client's brief when the project is for a CRM client.
const onShow = () => {
  error.value = null
  const c = client.value
  if (!c) return
  name.value = `${c.name} residence`
  address.value = c.site_address ?? ''
  budget.value = c.target_budget ?? null
  description.value = c.requirements ?? ''
  const parts = [
    c.preferred_style && `${c.preferred_style} style`,
    c.target_square_feet && `about ${c.target_square_feet.toLocaleString()} sq ft`,
    c.requirements
  ].filter(Boolean)
  if (parts.length && !prompt.value) prompt.value = `A house for ${c.name}: ${parts.join(', ')}.`
}

const reset = () => {
  prompt.value = ''
  name.value = ''
  address.value = ''
  description.value = ''
  startDate.value = ''
  budget.value = null
  ui.newProjectClientId = null
}

const submit = async () => {
  busy.value = true
  error.value = null
  const clientId = ui.newProjectClientId
  try {
    let projectId: number
    if (mode.value === 'ai') {
      const project = await projects.generateProject(prompt.value.trim(), budget.value)
      projectId = project.id
      if (address.value.trim()) await projects.updateProject(projectId, { address: address.value.trim() })
      if (clientId) await crm.startProject(clientId, { project_id: projectId })
    } else if (clientId) {
      projectId = await crm.startProject(clientId, { name: name.value.trim() })
      await projects.fetchProjects()
      projects.selectProject(projectId)
    } else {
      const project = await projects.createProject({
        name: name.value.trim(),
        address: address.value.trim() || null,
        description: description.value.trim() || null,
        budget: budget.value || null,
        start_date: startDate.value ? `${startDate.value}T00:00:00` : null
      })
      projectId = project.id
    }
    $q.notify({ type: 'positive', message: `Created "${projects.getProjectById(projectId)?.name ?? 'project'}"` })
    reset()
    ui.newProjectOpen = false
    router.push(mode.value === 'ai' ? '/design' : '/')
  } catch (err) {
    error.value = errorMessage(err, 'Could not create the project')
  } finally {
    busy.value = false
  }
}
</script>

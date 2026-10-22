<template>
  <q-page class="q-pa-md">
    <div class="page-container">
      <no-project v-if="!project" what="floor plan" />

      <template v-else>
        <page-header
          eyebrow="Design studio"
          :title="project.name"
          subtitle="Edit the floor plan, ask the AI for changes, and walk the result in the headset."
          icon="architecture"
        >
          <template #actions>
            <q-btn
              v-if="headset"
              unelevated
              no-caps
              color="secondary"
              icon="view_in_ar"
              label="Load to VR"
              @click="loadToVr(project.id, project.name)"
            />
            <q-chip v-else outline icon="view_in_ar" class="q-ma-none text-muted">
              Load to VR from the headset's dashboard
              <q-tooltip max-width="260px">In the Quest, this page opens inside the app and loads the house you are looking at.</q-tooltip>
            </q-chip>
          </template>
        </page-header>

        <div class="row q-col-gutter-md">
          <div class="col-12 col-md-9">
            <floor-plan-view
              ref="planView"
              :project-id="project.id"
              @renamed="onRenamed"
              @changed="onChanged"
            />
          </div>

          <div class="col-12 col-md-3 column q-gutter-y-md">
            <q-card flat class="app-card">
              <div class="app-card-header">
                <div class="app-card-title">Quick AI changes</div>
              </div>
              <q-card-section class="q-pt-xs">
                <div class="text-caption text-muted q-mb-sm">
                  Sent to the AI planner as a change to the current plan; each one saves a new version you can restore.
                </div>
                <div class="column q-gutter-xs">
                  <q-btn
                    v-for="s in suggestions"
                    :key="s.text"
                    flat
                    no-caps
                    align="left"
                    class="suggestion"
                    :icon="s.icon"
                    :disable="busy"
                    @click="applySuggestion(s.text)"
                  >
                    <div class="column items-start q-ml-xs text-left">
                      <span class="text-weight-medium">{{ s.title }}</span>
                      <span class="text-caption text-muted ellipsis-2">{{ s.text }}</span>
                    </div>
                  </q-btn>
                </div>
              </q-card-section>
            </q-card>

            <q-card flat class="app-card">
              <div class="app-card-header">
                <div class="app-card-title">Client</div>
              </div>
              <template v-if="client">
                <q-item clickable :to="{ path: '/crm', query: { client: String(client.id) } }">
                  <q-item-section avatar>
                    <q-avatar color="primary" text-color="white" size="36px" font-size="13px">{{ initials(client.name) }}</q-avatar>
                  </q-item-section>
                  <q-item-section>
                    <q-item-label class="text-weight-medium">{{ client.name }}</q-item-label>
                    <q-item-label caption>{{ client.stage_label }}</q-item-label>
                  </q-item-section>
                </q-item>
                <q-card-section v-if="client.ai_insights?.preferences?.length || client.preferred_style" class="q-pt-none">
                  <div class="text-caption text-muted q-mb-xs">What they asked for</div>
                  <ul class="prefs">
                    <li v-if="client.preferred_style">{{ client.preferred_style }}</li>
                    <li v-for="p in client.ai_insights?.preferences ?? []" :key="p">{{ p }}</li>
                  </ul>
                </q-card-section>
              </template>
              <empty-state v-else dense icon="person_off" title="No client linked" message="Link a CRM client to keep their preferences beside the plan." />
            </q-card>
          </div>
        </div>
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { useProjectsStore } from 'src/stores/projects'
import { useCrmStore } from 'src/stores/crm'
import { useBudgetStore } from 'src/stores/budget'
import { useUiStore } from 'src/stores/ui'
import { inHeadset, useLoadToVr } from 'src/composables/useLoadToVr'
import { errorMessage } from 'src/utils/errors'
import { initials } from 'src/utils/format'
import PageHeader from 'src/components/common/PageHeader.vue'
import EmptyState from 'src/components/common/EmptyState.vue'
import NoProject from 'src/components/common/NoProject.vue'
import FloorPlanView from 'src/components/FloorPlanView.vue'

const $q = useQuasar()
const projects = useProjectsStore()
const crm = useCrmStore()
const budget = useBudgetStore()
const ui = useUiStore()
const loadToVr = useLoadToVr()
const headset = inHeadset()

const planView = ref<InstanceType<typeof FloorPlanView> | null>(null)
const busy = ref(false)

const project = computed(() => projects.currentProject)
const client = computed(() => crm.clientsForProject(projects.currentProjectId)[0] ?? null)

const suggestions = [
  { title: 'Doors to the yard', icon: 'door_sliding', text: 'Add sliding glass doors from the living room to the back yard.' },
  { title: 'Bay window', icon: 'window', text: 'Add an angled bay window on the front of the living room.' },
  { title: 'Bigger primary suite', icon: 'bed', text: 'Make the primary bedroom about 3 feet longer and give it a walk-in closet.' },
  { title: 'Front garden', icon: 'yard', text: 'Plant a row of boxwood shrubs along the front of the house and a path to the front door.' },
  { title: 'Furnish the house', icon: 'chair', text: 'Furnish every room.' }
]

const applySuggestion = async (text: string) => {
  busy.value = true
  try {
    await planView.value?.refineWith(text)
  } finally {
    busy.value = false
  }
}

const onRenamed = (name: string) => {
  if (projects.currentProjectId) projects.renameLocally(projects.currentProjectId, name)
}

// A new version of the house is often a change to the contract: offer to log it.
const onChanged = (plan: { version: number; change_note: string | null; change_type: string | null }) => {
  projects.fetchOverview()
  if (plan.change_type !== 'refined' && plan.change_type !== 'edited') return
  $q.notify({
    type: 'positive',
    message: `Floor plan version ${plan.version} saved`,
    caption: plan.change_note ?? undefined,
    timeout: 8000,
    actions: [
      { label: 'Log as change order', color: 'white', noCaps: true, handler: () => logChangeOrder(plan) },
      { label: 'Dismiss', color: 'white', noCaps: true }
    ]
  })
}

const logChangeOrder = (plan: { version: number; change_note: string | null }) => {
  $q.dialog({
    title: 'Log a change order',
    message: `Price the change in floor plan version ${plan.version}. It is submitted for the owner's approval; edit it on the Budget page.`,
    prompt: { model: '', type: 'number', label: 'Cost impact ($)', outlined: true, dense: true },
    cancel: { flat: true, noCaps: true },
    ok: { unelevated: true, noCaps: true, label: 'Submit' }
  }).onOk(async (value: string) => {
    try {
      const co = await budget.addChangeOrder({
        title: (plan.change_note || `Floor plan version ${plan.version}`).slice(0, 255),
        description: plan.change_note,
        cost_impact: Number(value) || 0,
        schedule_impact_days: 0,
        requested_by: client.value?.name ?? 'Owner',
        floor_plan_version: plan.version
      }, projects.currentProjectId)
      $q.notify({ type: 'positive', message: `${co?.code ?? 'Change order'} submitted` })
      projects.fetchOverview()
    } catch (err) {
      $q.notify({ type: 'negative', message: errorMessage(err, 'Could not log the change order') })
    }
  })
}

// The copilot changed the plan: show the new version.
watch(() => ui.floorPlanRevision, () => planView.value?.reload())
</script>

<style lang="sass" scoped>
.suggestion
  border: 1px solid var(--app-border)
  border-radius: 10px
  padding: 6px 8px
  :deep(.q-btn__content)
    flex-wrap: nowrap
    justify-content: flex-start

.prefs
  margin: 0
  padding-left: 18px
  font-size: 0.85rem
</style>

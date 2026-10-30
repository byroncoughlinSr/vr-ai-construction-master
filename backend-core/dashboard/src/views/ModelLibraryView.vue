<template>
  <q-page class="q-pa-md">
    <div class="text-h4 q-mb-xs">{{ text.title }}</div>
    <div class="text-grey-7 q-mb-md">{{ text.intro }}</div>

    <q-banner v-if="status && !status.provider_ready" class="bg-orange-1 text-orange-10 q-mb-md" rounded>
      <template #avatar><q-icon name="warning" /></template>
      Models can't be made right now ({{ status.provider }}): {{ status.provider_problem }}
    </q-banner>

    <q-card class="q-mb-lg">
      <q-card-section>
        <div class="text-h6 q-mb-sm">{{ text.add }}</div>
        <q-form class="row q-col-gutter-md" @submit.prevent="addModel">
          <q-input
            v-model="form.name" class="col-12 col-sm-4" label="Name *" :hint="`What plans call it, e.g. ${text.example}`"
            outlined dense :rules="[v => !!v?.trim() || 'Give it a name']"
          />
          <q-input
            v-model.number="form.height" class="col-6 col-sm-2" type="number" min="0.1" step="0.5"
            label="Height (ft)" outlined dense
          />
          <q-file
            v-model="form.photo" class="col-12 col-sm-6" label="Photo" accept="image/*"
            :max-file-size="MAX_PHOTO_BYTES" outlined dense clearable
            @rejected="error = 'That photo is over 15 MB or not an image'"
          >
            <template #prepend><q-icon name="photo_camera" /></template>
          </q-file>
          <q-input
            v-model="form.description" class="col-12" type="textarea" autogrow outlined dense
            label="Description" :hint="text.describe"
          />
          <div class="col-12 row items-center q-gutter-sm">
            <q-btn
              type="submit" color="primary" icon="add" :label="text.add" :loading="adding"
              :disable="!canAdd"
            />
            <span v-if="!form.photo && !form.description?.trim()" class="text-grey-7">
              Add a photo or a description.
            </span>
          </div>
        </q-form>
        <div v-if="error" class="text-negative q-mt-sm">{{ error }}</div>
      </q-card-section>
    </q-card>

    <div v-if="loading && !models.length" class="text-center q-pa-lg"><q-spinner size="32px" /></div>
    <div v-else-if="!models.length" class="text-grey-6 text-center q-pa-lg">
      <q-icon :name="text.icon" size="48px" />
      <div class="q-mt-sm">{{ text.empty }}</div>
    </div>

    <div class="row q-col-gutter-md">
      <div v-for="m in models" :key="m.id" class="col-12 col-sm-6 col-md-4 col-lg-3">
        <q-card class="plant-card">
          <q-img v-if="m.image_url" :src="fileSrc(m.image_url)" :ratio="1" fit="contain" class="bg-white" />
          <div v-else class="plant-placeholder flex flex-center bg-grey-2"><q-icon :name="text.icon" size="48px" color="grey-5" /></div>
          <q-card-section class="q-pb-xs">
            <div class="row items-center no-wrap">
              <div class="text-subtitle1 ellipsis col">{{ m.name }}</div>
              <q-chip dense :color="STATUS[m.status]?.color ?? 'grey'" text-color="white" class="plant-status">
                <q-spinner v-if="isWorking(m)" size="12px" class="q-mr-xs" />
                {{ STATUS[m.status]?.label ?? m.status }}
              </q-chip>
            </div>
            <div class="text-caption text-grey-7">
              {{ m.source === 'description' ? 'Drawn from a description' : 'From a photo' }}
              <template v-if="m.height_ft"> · {{ m.height_ft }} ft</template>
              <template v-if="m.triangles"> · {{ m.triangles.toLocaleString() }} triangles</template>
              <template v-if="m.turn"> · turned {{ m.turn }}°</template>
              <template v-if="m.recolored"> · recoloured</template>
            </div>
            <div v-if="m.error" class="text-caption text-negative q-mt-xs">{{ m.error }}</div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn
              v-if="m.model_url" flat dense icon="download" label=".glb" :href="fileSrc(m.model_url)"
              target="_blank" download
            />
            <q-btn
              v-if="m.model_url && kind === 'furniture'" flat dense icon="rotate_right" label="Turn 90°"
              @click="turn(m)"
            >
              <q-tooltip>Turn it until its front (an island's seating side) faces the way the house places it</q-tooltip>
            </q-btn>
            <q-btn v-if="m.model_url" flat dense icon="palette" label="Recolour" @click="openRecolor(m)">
              <q-tooltip>Change one of its colours, e.g. tan cabinets to white</q-tooltip>
            </q-btn>
            <q-btn
              v-if="!isWorking(m)" flat dense icon="refresh" :label="m.status === 'ready' ? 'Remake' : 'Retry'"
              :disable="!status?.provider_ready" @click="retry(m)"
            />
            <q-btn flat dense color="negative" icon="delete" label="Delete" @click="remove(m)" />
          </q-card-actions>
        </q-card>
      </div>
    </div>

    <KitchenStyles v-if="kind === 'furniture'" :models="models" />

    <q-dialog v-model="recolor.open">
      <q-card v-if="recolor.model" class="recolor-card">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6 ellipsis col">Recolour {{ recolor.model.name }}</div>
          <q-btn flat round dense icon="close" v-close-popup />
        </q-card-section>
        <q-card-section>
          <div class="text-caption text-grey-7 q-mb-xs">Colour to change (most of the model first)</div>
          <div v-if="recolor.loading" class="q-pa-sm"><q-spinner size="24px" /></div>
          <div v-else class="row q-gutter-sm">
            <button
              v-for="c in recolor.colors" :key="c.color" type="button" class="swatch"
              :class="{ 'swatch--picked': recolor.from === c.color }" :style="{ background: c.color }"
              :aria-label="`${c.color}, ${Math.round(c.share * 100)}% of it`" @click="recolor.from = c.color"
            >
              <span class="swatch-share">{{ Math.round(c.share * 100) }}%</span>
            </button>
          </div>

          <div class="text-caption text-grey-7 q-mt-md q-mb-xs">New colour</div>
          <div class="row items-center q-gutter-sm">
            <button
              v-for="c in NEW_COLORS" :key="c.color" type="button" class="swatch swatch--small"
              :class="{ 'swatch--picked': recolor.to === c.color }" :style="{ background: c.color }"
              :aria-label="c.name" :title="c.name" @click="recolor.to = c.color"
            />
            <input v-model="recolor.to" type="color" class="color-input" aria-label="Any colour">
          </div>

          <div class="text-caption text-grey-7 q-mt-md">How close a shade still counts</div>
          <q-slider v-model="recolor.tolerance" :min="0" :max="1" :step="0.05" label :label-value="toleranceLabel" />
          <div v-if="recolor.message" class="text-caption q-mt-xs">{{ recolor.message }}</div>
          <div v-if="recolor.error" class="text-caption text-negative q-mt-xs">{{ recolor.error }}</div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-if="recolor.model.recolored" flat label="Reset to original" icon="restart_alt"
            :loading="recolor.busy" @click="resetColors"
          />
          <q-space />
          <q-btn flat label="Done" v-close-popup />
          <q-btn
            color="primary" label="Apply" icon="format_color_fill" :loading="recolor.busy"
            :disable="!recolor.from || !recolor.to" @click="applyRecolor"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { apiClient } from 'src/services/api'
import KitchenStyles from 'src/components/furniture/KitchenStyles.vue'

// A plant or piece of furniture in a library, as plant_model_service.serialize returns it.
export interface PlantModel {
  id: number
  kind?: 'plant' | 'furniture'
  name: string
  description: string | null
  source: string
  provider: string | null
  status: 'pending' | 'generating' | 'ready' | 'failed' | string
  error: string | null
  height_ft: number | null
  aspect: number | null
  triangles: number | null
  turn?: number
  recolored?: boolean
  image_url: string | null
  model_url: string | null
  created_at: string | null
}

interface ProviderStatus {
  provider: string
  provider_ready: boolean
  provider_problem: string | null
}

// One page for both libraries: /plants and /furniture (routes pass the kind).
const props = withDefaults(defineProps<{ kind?: 'plant' | 'furniture' }>(), { kind: 'plant' })

const TEXT = {
  plant: {
    title: 'Plant Library',
    intro: 'Add a plant you bought (a photo, or a description to draw it from) and it gets a 3D model. ' +
      'Any house whose landscaping names it, e.g. "coral rose", is then drawn with that model.',
    add: 'Add plant',
    example: 'Coral rose',
    describe: "Used to draw the plant when there's no photo, e.g. a coral-pink shrub rose in full bloom",
    empty: 'No plants yet. Houses use the drawn plants until you add one.',
    icon: 'yard',
    endpoint: '/plants/models'
  },
  furniture: {
    title: 'Furniture Library',
    intro: 'Add a piece you own or want (a photo, or a description to draw it from) and it gets a 3D model. ' +
      'Any room whose furniture names it, e.g. "Grandma\'s armchair", is then drawn with that model.',
    add: 'Add furniture',
    example: "Grandma's armchair",
    describe: "Used to draw the piece when there's no photo, e.g. a mid-century walnut armchair with green cushions",
    empty: 'No furniture yet. Houses use the drawn furniture until you add a piece.',
    icon: 'chair',
    endpoint: '/furniture/models'
  }
}
const text = computed(() => TEXT[props.kind])

const MAX_PHOTO_BYTES = 15 * 1024 * 1024
const POLL_MS = 5000
const STATUS: Record<string, { label: string; color: string }> = {
  pending: { label: 'Queued', color: 'blue-grey' },
  generating: { label: 'Making model', color: 'blue' },
  ready: { label: 'Ready', color: 'positive' },
  failed: { label: 'Failed', color: 'negative' }
}

const models = ref<PlantModel[]>([])
const status = ref<ProviderStatus | null>(null)
const loading = ref(false)
const adding = ref(false)
const error = ref('')
const form = reactive({ name: '', height: null as number | null, photo: null as File | null, description: '' })
let timer: ReturnType<typeof setTimeout> | undefined

const isWorking = (m: PlantModel) => m.status === 'pending' || m.status === 'generating'
const canAdd = computed(() =>
  !!form.name.trim() && (!!form.photo || !!form.description.trim()) && !!status.value?.provider_ready
)

// Photos and models are served by the backend (/plant_models/...), not under /api/v1.
const fileSrc = (path: string) => {
  const base = String(apiClient.client.defaults?.baseURL ?? '')
  return base.replace(/\/api\/v1\/?$/, '') + path
}

const errorMessage = (err: unknown, fallback: string) => {
  const e = err as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = e.response?.data?.detail
  return typeof detail === 'string' ? detail : e.message || fallback
}

// Reload while a model is being made, so its status and picture appear.
const schedulePoll = () => {
  clearTimeout(timer)
  if (models.value.some(isWorking)) timer = setTimeout(load, POLL_MS)
}

async function load() {
  loading.value = true
  try {
    const { data } = await apiClient.client.get(text.value.endpoint)
    models.value = data.models ?? []
    status.value = { provider: data.provider, provider_ready: data.provider_ready, provider_problem: data.provider_problem }
  } catch (err) {
    error.value = errorMessage(err, `Could not load the ${props.kind} library`)
  } finally {
    loading.value = false
    schedulePoll()
  }
}

async function addModel() {
  if (!canAdd.value) return
  adding.value = true
  error.value = ''
  const body = new FormData()
  body.append('name', form.name.trim())
  if (form.description.trim()) body.append('description', form.description.trim())
  if (form.height && form.height > 0) body.append('height_ft', String(form.height))
  if (form.photo) body.append('photo', form.photo)
  try {
    // The client defaults to JSON, and axios turns FormData into JSON under that header
    await apiClient.client.post(text.value.endpoint, body, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    Object.assign(form, { name: '', height: null, photo: null, description: '' })
    await load()
  } catch (err) {
    error.value = errorMessage(err, `Could not add the ${props.kind === 'plant' ? 'plant' : 'piece'}`)
  } finally {
    adding.value = false
  }
}

async function turn(m: PlantModel) {
  error.value = ''
  try {
    const { data } = await apiClient.client.patch(`${text.value.endpoint}/${m.id}`, { turn: ((m.turn ?? 0) + 90) % 360 })
    m.turn = data.turn
  } catch (err) {
    error.value = errorMessage(err, 'Could not turn the model')
  }
}

// Recolouring: the model's own colours to pick from, a new one, and how loosely to match.
const NEW_COLORS = [
  { name: 'White', color: '#f4f4f0' }, { name: 'Cream', color: '#efe6d2' }, { name: 'Light grey', color: '#c8c8c4' },
  { name: 'Charcoal', color: '#3a3a3a' }, { name: 'Black', color: '#151515' }, { name: 'Navy', color: '#1f2f4f' },
  { name: 'Sage', color: '#9caf88' }, { name: 'Walnut', color: '#5d4330' }, { name: 'Oak', color: '#b08a5a' }
]
const recolor = reactive({
  open: false,
  model: null as PlantModel | null,
  colors: [] as { color: string; share: number }[],
  from: '',
  to: '#f4f4f0',
  tolerance: 0.5,
  loading: false,
  busy: false,
  message: '',
  error: ''
})
const toleranceLabel = computed(() => recolor.tolerance < 0.3 ? 'exact' : recolor.tolerance > 0.7 ? 'loose' : 'normal')

async function loadColors() {
  if (!recolor.model) return
  recolor.loading = true
  try {
    const { data } = await apiClient.client.get(`${text.value.endpoint}/${recolor.model.id}/colors`)
    recolor.colors = data.colors
    if (!recolor.colors.some(c => c.color === recolor.from)) recolor.from = ''
  } catch (err) {
    recolor.error = errorMessage(err, 'Could not read its colours')
  } finally {
    recolor.loading = false
  }
}

function openRecolor(m: PlantModel) {
  Object.assign(recolor, { open: true, model: m, colors: [], from: '', message: '', error: '' })
  loadColors()
}

function updateModel(data: PlantModel) {
  const i = models.value.findIndex(x => x.id === data.id)
  if (i >= 0) models.value[i] = { ...models.value[i], ...data }
  recolor.model = i >= 0 ? models.value[i] : data
}

async function applyRecolor() {
  if (!recolor.model) return
  recolor.busy = true
  recolor.error = ''
  try {
    const { data } = await apiClient.client.post(`${text.value.endpoint}/${recolor.model.id}/recolor`, {
      from_color: recolor.from, to_color: recolor.to, tolerance: recolor.tolerance
    })
    updateModel(data)
    recolor.message = `Changed ${Math.round(data.changed * 100)}% of it. Houses show it the next time they load.`
    await loadColors()
  } catch (err) {
    recolor.error = errorMessage(err, 'Could not recolour it')
  } finally {
    recolor.busy = false
  }
}

async function resetColors() {
  if (!recolor.model) return
  recolor.busy = true
  recolor.error = ''
  try {
    const { data } = await apiClient.client.post(`${text.value.endpoint}/${recolor.model.id}/reset-colors`)
    updateModel(data)
    recolor.message = 'Back to the colours it was made with.'
    await loadColors()
  } catch (err) {
    recolor.error = errorMessage(err, 'Could not reset its colours')
  } finally {
    recolor.busy = false
  }
}

async function retry(m: PlantModel) {
  error.value = ''
  try {
    await apiClient.client.post(`${text.value.endpoint}/${m.id}/retry`)
    await load()
  } catch (err) {
    error.value = errorMessage(err, 'Could not restart the model')
  }
}

async function remove(m: PlantModel) {
  error.value = ''
  try {
    await apiClient.client.delete(`${text.value.endpoint}/${m.id}`)
    models.value = models.value.filter(x => x.id !== m.id)
  } catch (err) {
    error.value = errorMessage(err, `Could not delete the ${props.kind === 'plant' ? 'plant' : 'piece'}`)
  }
}

onMounted(load)
// The same component serves both routes: reload when moving between them.
watch(() => props.kind, () => {
  models.value = []
  error.value = ''
  load()
})
onBeforeUnmount(() => clearTimeout(timer))
</script>

<style scoped>
.plant-placeholder { aspect-ratio: 1; }
.plant-status { flex-shrink: 0; }
.recolor-card { width: 440px; max-width: 100%; }
.swatch {
  position: relative; width: 52px; height: 52px; border-radius: 8px; cursor: pointer;
  border: 1px solid rgba(128, 128, 128, 0.5); padding: 0;
}
.swatch--small { width: 32px; height: 32px; border-radius: 50%; }
.swatch--picked { outline: 3px solid var(--q-primary); outline-offset: 2px; }
.swatch-share {
  position: absolute; bottom: 2px; right: 3px; font-size: 10px; padding: 0 3px; border-radius: 4px;
  background: rgba(0, 0, 0, 0.55); color: #fff;
}
.color-input { width: 40px; height: 32px; border: none; background: none; cursor: pointer; padding: 0; }
</style>

<template>
  <q-page class="q-pa-md">
    <div class="text-h4 q-mb-xs">Plant Library</div>
    <div class="text-grey-7 q-mb-md">
      Add a plant you bought (a photo, or a description to draw it from) and it gets a 3D model.
      Any house whose landscaping names it, e.g. "coral rose", is then drawn with that model.
    </div>

    <q-banner v-if="status && !status.provider_ready" class="bg-orange-1 text-orange-10 q-mb-md" rounded>
      <template #avatar><q-icon name="warning" /></template>
      Models can't be made right now ({{ status.provider }}): {{ status.provider_problem }}
    </q-banner>

    <q-card class="q-mb-lg">
      <q-card-section>
        <div class="text-h6 q-mb-sm">Add a plant</div>
        <q-form class="row q-col-gutter-md" @submit.prevent="addPlant">
          <q-input
            v-model="form.name" class="col-12 col-sm-4" label="Name *" hint="What plans call it, e.g. Coral rose"
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
            label="Description" hint="Used to draw the plant when there's no photo, e.g. a coral-pink shrub rose in full bloom"
          />
          <div class="col-12 row items-center q-gutter-sm">
            <q-btn
              type="submit" color="primary" icon="add" label="Add plant" :loading="adding"
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
      <q-icon name="yard" size="48px" />
      <div class="q-mt-sm">No plants yet. Houses use the drawn plants until you add one.</div>
    </div>

    <div class="row q-col-gutter-md">
      <div v-for="m in models" :key="m.id" class="col-12 col-sm-6 col-md-4 col-lg-3">
        <q-card class="plant-card">
          <q-img v-if="m.image_url" :src="fileSrc(m.image_url)" :ratio="1" fit="contain" class="bg-white" />
          <div v-else class="plant-placeholder flex flex-center bg-grey-2"><q-icon name="yard" size="48px" color="grey-5" /></div>
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
            </div>
            <div v-if="m.error" class="text-caption text-negative q-mt-xs">{{ m.error }}</div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn
              v-if="m.model_url" flat dense icon="download" label=".glb" :href="fileSrc(m.model_url)"
              target="_blank" download
            />
            <q-btn
              v-if="!isWorking(m)" flat dense icon="refresh" :label="m.status === 'ready' ? 'Remake' : 'Retry'"
              :disable="!status?.provider_ready" @click="retry(m)"
            />
            <q-btn flat dense color="negative" icon="delete" label="Delete" @click="remove(m)" />
          </q-card-actions>
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { apiClient } from 'src/services/api'

// A plant in the library, as plant_model_service.serialize returns it.
export interface PlantModel {
  id: number
  name: string
  description: string | null
  source: string
  provider: string | null
  status: 'pending' | 'generating' | 'ready' | 'failed' | string
  error: string | null
  height_ft: number | null
  aspect: number | null
  triangles: number | null
  image_url: string | null
  model_url: string | null
  created_at: string | null
}

interface ProviderStatus {
  provider: string
  provider_ready: boolean
  provider_problem: string | null
}

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
    const { data } = await apiClient.client.get('/plants/models')
    models.value = data.models ?? []
    status.value = { provider: data.provider, provider_ready: data.provider_ready, provider_problem: data.provider_problem }
  } catch (err) {
    error.value = errorMessage(err, 'Could not load the plant library')
  } finally {
    loading.value = false
    schedulePoll()
  }
}

async function addPlant() {
  if (!canAdd.value) return
  adding.value = true
  error.value = ''
  const body = new FormData()
  body.append('name', form.name.trim())
  if (form.description.trim()) body.append('description', form.description.trim())
  if (form.height && form.height > 0) body.append('height_ft', String(form.height))
  if (form.photo) body.append('photo', form.photo)
  try {
    await apiClient.client.post('/plants/models', body)
    Object.assign(form, { name: '', height: null, photo: null, description: '' })
    await load()
  } catch (err) {
    error.value = errorMessage(err, 'Could not add the plant')
  } finally {
    adding.value = false
  }
}

async function retry(m: PlantModel) {
  error.value = ''
  try {
    await apiClient.client.post(`/plants/models/${m.id}/retry`)
    await load()
  } catch (err) {
    error.value = errorMessage(err, 'Could not restart the model')
  }
}

async function remove(m: PlantModel) {
  error.value = ''
  try {
    await apiClient.client.delete(`/plants/models/${m.id}`)
    models.value = models.value.filter(x => x.id !== m.id)
  } catch (err) {
    error.value = errorMessage(err, 'Could not delete the plant')
  }
}

onMounted(load)
onBeforeUnmount(() => clearTimeout(timer))
</script>

<style scoped>
.plant-placeholder { aspect-ratio: 1; }
.plant-status { flex-shrink: 0; }
</style>

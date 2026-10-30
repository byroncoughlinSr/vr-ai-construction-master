<template>
  <q-card class="q-mt-lg">
    <q-card-section>
      <div class="row items-center q-mb-xs">
        <div class="text-h6 col">Kitchen styles</div>
        <q-btn color="primary" icon="add" label="New style" @click="openEditor()" />
      </div>
      <div class="text-grey-7 q-mb-md">
        A saved look for kitchens: cabinets, doors, countertop, backsplash and your own appliances. Ask for it in any house,
        e.g. "kitchen in {{ styles[0]?.name || "Farmhouse kitchen" }} style". The counters still stretch to fit each kitchen.
      </div>
      <div v-if="error" class="text-negative q-mb-sm">{{ error }}</div>
      <div v-if="!styles.length" class="text-grey-6">No kitchen styles yet. Kitchens use plain white cabinets until you add one.</div>

      <div class="row q-col-gutter-md">
        <div v-for="s in styles" :key="s.id" class="col-12 col-sm-6 col-md-4">
          <q-card flat bordered class="style-card">
            <div class="elevation" :style="{ background: s.backsplash === 'none' ? '#e9e7e2' : s.backsplash_color }">
              <div class="upper" :style="{ background: s.cabinet }">
                <span v-for="k in 3" :key="k" class="door" :class="{ glass: s.uppers === 'glass' }" />
              </div>
              <div class="top" :style="{ background: s.top }" />
              <div class="base" :style="{ background: s.cabinet }">
                <span v-for="k in 3" :key="k" class="door" :class="`door--${s.door}`">
                  <i :style="{ background: s.handle }" />
                </span>
              </div>
            </div>
            <q-card-section class="q-pb-xs">
              <div class="text-subtitle1 ellipsis">{{ s.name }}</div>
              <div class="text-caption text-grey-7">{{ summary(s) }}</div>
            </q-card-section>
            <q-card-actions align="right">
              <q-btn flat dense icon="edit" label="Edit" @click="openEditor(s)" />
              <q-btn flat dense icon="delete" color="negative" :aria-label="`Delete ${s.name}`" @click="remove(s)" />
            </q-card-actions>
          </q-card>
        </div>
      </div>
    </q-card-section>

    <q-dialog v-model="editor.open">
      <q-card class="editor-card">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6 col">{{ editor.id ? `Edit ${editor.name}` : 'New kitchen style' }}</div>
          <q-btn flat round dense icon="close" v-close-popup />
        </q-card-section>
        <q-card-section class="q-gutter-y-sm">
          <q-input v-model="editor.name" label="Name *" hint="What you'll call it, e.g. Farmhouse kitchen" outlined dense />
          <div class="row q-col-gutter-sm">
            <label class="col-6 color-field">Cabinets <input v-model="editor.style.cabinet" type="color"></label>
            <label class="col-6 color-field">Handles <input v-model="editor.style.handle" type="color"></label>
            <label class="col-6 color-field">Countertop <input v-model="editor.style.top" type="color"></label>
            <label class="col-6 color-field">
              <q-checkbox v-model="hasFleck" dense label="Granite fleck" />
              <input v-if="hasFleck" v-model="editor.style.fleck" type="color" aria-label="Fleck colour">
            </label>
          </div>
          <div class="row q-col-gutter-sm">
            <q-select v-model="editor.style.door" :options="choices.door" label="Doors" class="col-6" outlined dense :option-label="o => LABELS[o] || o" />
            <q-select v-model="editor.style.uppers" :options="choices.uppers" label="Wall cabinets" class="col-6" outlined dense :option-label="o => LABELS[o] || o" />
            <q-select v-model="editor.style.backsplash" :options="choices.backsplash" label="Backsplash" class="col-6" outlined dense :option-label="o => LABELS[o] || o" />
            <label v-if="editor.style.backsplash !== 'none'" class="col-6 color-field">
              Backsplash colour <input v-model="editor.style.backsplash_color" type="color">
            </label>
          </div>
          <q-toggle v-model="editor.style.crown" label="Crown molding on the wall cabinets" />
          <div class="row q-col-gutter-sm">
            <q-select
              v-model="editor.style.stove_model_id" :options="modelOptions" label="Stove (photo model)" class="col-6"
              outlined dense emit-value map-options clearable hint="Leave empty for the drawn range"
            />
            <q-select
              v-model="editor.style.fridge_model_id" :options="modelOptions" label="Refrigerator (photo model)" class="col-6"
              outlined dense emit-value map-options clearable hint="Leave empty for the drawn fridge"
            />
          </div>
          <div v-if="editor.error" class="text-negative">{{ editor.error }}</div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancel" v-close-popup />
          <q-btn color="primary" label="Save" icon="save" :loading="editor.busy" :disable="!editor.name.trim()" @click="save" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-card>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { apiClient } from 'src/services/api'

// A saved kitchen look, as GET /kitchen-styles returns it (kitchen_style_service.as_dict).
export interface KitchenStyle {
  id: number
  name: string
  cabinet: string
  door: string
  uppers: string
  handle: string
  crown: boolean
  top: string
  fleck: string | null
  backsplash: string
  backsplash_color: string
  stove_model_id: number | null
  fridge_model_id: number | null
}
type StyleFields = Omit<KitchenStyle, 'id' | 'name'>

const props = defineProps<{ models: { id: number; name: string; status: string }[] }>()

const LABELS: Record<string, string> = {
  flat: 'Flat', shaker: 'Shaker', raised: 'Raised panel', solid: 'Solid doors', glass: 'Glass fronts',
  none: 'None', tile: 'Tile', mosaic: 'Mosaic strips'
}
const ENDPOINT = '/kitchen-styles'

const styles = ref<KitchenStyle[]>([])
const choices = reactive({ door: ['flat', 'shaker', 'raised'], uppers: ['solid', 'glass'], backsplash: ['none', 'tile', 'mosaic'] })
const defaults = ref<StyleFields | null>(null)
const error = ref('')
const editor = reactive({ open: false, id: 0, name: '', style: {} as StyleFields, busy: false, error: '' })

const modelOptions = computed(() =>
  props.models.filter(m => m.status === 'ready').map(m => ({ label: m.name, value: m.id }))
)
const hasFleck = computed({
  get: () => !!editor.style.fleck,
  set: (on: boolean) => { editor.style.fleck = on ? '#8f8a80' : null }
})

const errorMessage = (err: unknown, fallback: string) => {
  const e = err as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = e.response?.data?.detail
  return typeof detail === 'string' ? detail : e.message || fallback
}

const modelName = (id: number | null) => props.models.find(m => m.id === id)?.name
const summary = (s: KitchenStyle) => [
  `${LABELS[s.door] ?? s.door} doors`,
  s.uppers === 'glass' ? 'glass uppers' : null,
  s.backsplash !== 'none' ? `${s.backsplash} backsplash` : null,
  s.crown ? 'crown' : null,
  modelName(s.stove_model_id),
  modelName(s.fridge_model_id)
].filter(Boolean).join(' · ')

async function load() {
  try {
    const { data } = await apiClient.client.get(ENDPOINT)
    styles.value = data.styles ?? []
    if (data.choices) Object.assign(choices, data.choices)
    defaults.value = data.defaults ?? null
  } catch (err) {
    error.value = errorMessage(err, 'Could not load the kitchen styles')
  }
}

const FIELDS: (keyof StyleFields)[] = [
  'cabinet', 'door', 'uppers', 'handle', 'crown', 'top', 'fleck', 'backsplash', 'backsplash_color',
  'stove_model_id', 'fridge_model_id'
]

function openEditor(s?: KitchenStyle) {
  const from = (s ?? defaults.value ?? {}) as Partial<StyleFields>
  const style = Object.fromEntries(FIELDS.map(k => [k, from[k] ?? null])) as unknown as StyleFields
  Object.assign(editor, { open: true, id: s?.id ?? 0, name: s?.name ?? '', style, busy: false, error: '' })
}

async function save() {
  editor.busy = true
  editor.error = ''
  try {
    const body = { name: editor.name.trim(), style: editor.style }
    if (editor.id) await apiClient.client.put(`${ENDPOINT}/${editor.id}`, body)
    else await apiClient.client.post(ENDPOINT, body)
    editor.open = false
    await load()
  } catch (err) {
    editor.error = errorMessage(err, 'Could not save the style')
  } finally {
    editor.busy = false
  }
}

async function remove(s: KitchenStyle) {
  error.value = ''
  try {
    await apiClient.client.delete(`${ENDPOINT}/${s.id}`)
    styles.value = styles.value.filter(x => x.id !== s.id)
  } catch (err) {
    error.value = errorMessage(err, 'Could not delete the style')
  }
}

onMounted(load)
defineExpose({ load, save, openEditor, editor, styles })
</script>

<style scoped>
.style-card { overflow: hidden; }
.elevation { height: 120px; padding: 10px 14px 0; display: flex; flex-direction: column; }
.upper { height: 40px; display: flex; gap: 3px; padding: 3px; }
.top { height: 6px; margin-top: 18px; }
.base { flex: 1; display: flex; gap: 3px; padding: 4px 3px 0; }
.door { flex: 1; position: relative; border: 1px solid rgba(0, 0, 0, 0.18); }
.door.glass { background: #8fa3a8; border: 3px solid rgba(255, 255, 255, 0.35); }
.door--shaker, .door--raised { box-shadow: inset 0 0 0 5px rgba(0, 0, 0, 0.06); }
.door--raised::after { content: ''; position: absolute; inset: 8px; border: 1px solid rgba(255, 255, 255, 0.5); }
.door i { position: absolute; top: 6px; left: 50%; width: 14px; height: 3px; margin-left: -7px; border-radius: 2px; }
.editor-card { width: 520px; max-width: 100%; }
.color-field { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 40px; }
.color-field input[type='color'] { width: 44px; height: 30px; border: none; background: none; cursor: pointer; padding: 0; }
</style>

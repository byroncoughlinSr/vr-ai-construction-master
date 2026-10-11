<template>
  <q-card>
    <q-card-section class="row items-center">
      <div class="col">
        <div class="text-h6">
          Floor Plan
          <span v-if="floorPlan" class="text-subtitle1 text-grey-8">
            — {{ floorPlan.name }}
            <q-badge color="primary" class="q-ml-xs">v{{ floorPlan.version }}</q-badge>
          </span>
        </div>
        <div class="text-caption text-grey-7">
          Layout sent to the headset — doorways show how rooms connect
        </div>
      </div>
      <q-btn
        v-if="floorPlan && !editing"
        flat round icon="edit" :disable="loading || saving" @click="startEditing"
      >
        <q-tooltip>Edit floor plan</q-tooltip>
      </q-btn>
      <q-btn
        v-if="floorPlan && !editing"
        flat round icon="history" :disable="loading || saving" @click="toggleHistory"
      >
        <q-tooltip>Version history</q-tooltip>
      </q-btn>
      <q-btn flat round icon="refresh" :loading="loading" :disable="!projectId || editing" @click="load">
        <q-tooltip>Reload floor plan</q-tooltip>
      </q-btn>
    </q-card-section>

    <q-card-section>
      <div v-if="loading" class="flex flex-center q-pa-lg">
        <q-spinner size="40px" color="primary" />
      </div>
      <q-banner v-else-if="error" class="bg-negative text-white" dense>{{ error }}</q-banner>
      <div v-else-if="!rooms.length" class="text-center text-grey-6 q-pa-md">
        <q-icon name="home" size="48px" />
        <div class="q-mt-sm">No rooms in this project yet</div>
      </div>

      <template v-else>
        <q-banner v-if="saveError" class="bg-negative text-white q-mb-sm" dense>{{ saveError }}</q-banner>

        <div class="row q-col-gutter-md">
          <div :class="editing ? 'col-12 col-md-6' : 'col-12'">
            <svg
              class="floor-plan"
              :viewBox="viewBox"
              role="img"
              :aria-label="`Floor plan with ${rooms.length} rooms`"
            >
              <!-- Rooms -->
              <g v-for="room in rooms" :key="room.id">
                <rect
                  :x="room.bounds.x0"
                  :y="svgY(room.bounds.z1)"
                  :width="room.bounds.x1 - room.bounds.x0"
                  :height="room.bounds.z1 - room.bounds.z0"
                  :fill="roomColor(room.name)"
                  stroke="#37474F"
                  :stroke-width="WALL"
                />
                <text
                  :x="(room.bounds.x0 + room.bounds.x1) / 2"
                  :y="svgY((room.bounds.z0 + room.bounds.z1) / 2) - 0.1"
                  text-anchor="middle"
                  class="room-name"
                >{{ room.name }}</text>
                <text
                  :x="(room.bounds.x0 + room.bounds.x1) / 2"
                  :y="svgY((room.bounds.z0 + room.bounds.z1) / 2) + 0.4"
                  text-anchor="middle"
                  class="room-size"
                >{{ feet(room.dimensions.length) }} × {{ feet(room.dimensions.width) }} ft</text>
              </g>

              <!-- Windows: glazing line over the wall -->
              <g v-for="w in windows" :key="`w${w.id}`">
                <line v-bind="span(w)" stroke="#FFFFFF" :stroke-width="WALL * 1.4" />
                <line v-bind="span(w)" stroke="#4FC3F7" :stroke-width="WALL * 0.6" />
              </g>

              <!-- Doors: a gap in the wall with jamb ticks -->
              <g v-for="d in doors" :key="`d${d.id}`">
                <line v-bind="span(d)" stroke="#FFFFFF" :stroke-width="WALL * 1.6" />
                <line v-for="(tick, i) in jambs(d)" :key="i" v-bind="tick" stroke="#6D4C41" :stroke-width="0.06" />
              </g>

              <!-- Entry marker -->
              <g v-if="frontDoor">
                <text
                  :x="frontDoor.position.x"
                  :y="svgY(frontDoor.position.z) + 0.75"
                  text-anchor="middle"
                  class="entry"
                >▲ Entry</text>
              </g>
            </svg>

            <div class="row q-gutter-md text-caption text-grey-7 q-mt-sm">
              <span>{{ rooms.length }} rooms</span>
              <span>{{ interiorDoorCount }} doorways</span>
              <span>{{ windows.length }} windows</span>
              <span><span class="swatch" style="background:#4FC3F7" /> window</span>
              <span><span class="swatch" style="background:#6D4C41" /> doorway</span>
            </div>

            <div v-if="floorPlan?.image_url" class="q-mt-md">
              <div class="text-caption text-grey-7 q-mb-xs">Accepted rendering</div>
              <img :src="imageSrc(floorPlan.image_url)" alt="Rendering of the house" class="rendering" />
            </div>

            <!-- Describe a change: the AI revises the plan -->
            <div v-if="floorPlan && !editing" class="row items-start q-gutter-sm q-mt-md">
              <q-input
                v-model="instruction"
                class="col"
                dense outlined
                label="Describe a change (e.g. make the kitchen bigger)"
                :disable="saving"
                @keyup.enter="refine"
              />
              <q-btn
                color="primary" icon="auto_fix_high" label="Apply"
                :loading="saving" :disable="!instruction.trim()" @click="refine"
              />
            </div>
          </div>

          <!-- Editor -->
          <div v-if="editing && draft" class="col-12 col-md-6 editor">
            <q-input v-model="draft.name" dense outlined label="House name" class="q-mb-sm" />

            <div class="text-subtitle2 q-mt-sm">Footprint (ft)</div>
            <div class="row q-gutter-sm q-mb-sm">
              <q-input
                v-model.number="draft.layout.length" type="number" dense outlined
                class="col" label="Length (left to right)" min="8"
              />
              <q-input
                v-model.number="draft.layout.width" type="number" dense outlined
                class="col" label="Depth (front to back)" min="8"
              />
            </div>
            <q-select
              v-model="draft.layout.entry" :options="draftRoomNames" dense outlined
              label="Front door opens into" class="q-mb-md"
            />

            <div class="text-subtitle2">Room sizes (ft)</div>
            <div class="text-caption text-grey-7 q-mb-xs">
              Sizes within a group are scaled to fill it, so they don't have to add up exactly.
            </div>
            <div
              v-for="(row, i) in partRows" :key="i"
              class="row items-center q-mb-xs" :style="{ paddingLeft: `${row.depth * 16}px` }"
            >
              <div class="col">
                <q-input
                  v-if="row.part.room !== undefined"
                  :model-value="row.part.room" dense borderless
                  :aria-label="`Name of room ${i + 1}`"
                  @update:model-value="name => renameRoom(row.part, String(name ?? ''))"
                />
                <span v-else class="text-grey-8">
                  {{ row.part.split === 'x' ? 'Side-by-side group' : 'Front-to-back group' }}
                </span>
              </div>
              <q-input
                v-model.number="row.part.size" type="number" dense outlined style="width: 90px"
                :suffix="row.axis === 'x' ? 'wide' : 'deep'" min="1"
              />
            </div>

            <div class="text-subtitle2 q-mt-md">Doorways</div>
            <div v-for="(room, i) in draft.rooms" :key="i" class="q-mb-xs">
              <q-select
                :model-value="room.connects_to ?? []"
                :options="draftRoomNames.filter(n => n !== room.name)"
                :label="room.name" multiple use-chips dense outlined
                @update:model-value="names => setConnections(room.name, names as string[])"
              />
            </div>

            <div class="row q-gutter-sm q-mt-md">
              <q-btn color="primary" icon="save" label="Save as new version" :loading="saving" @click="saveDraft" />
              <q-btn flat label="Cancel" :disable="saving" @click="cancelEditing" />
            </div>
          </div>
        </div>

        <!-- Version history -->
        <q-list v-if="showHistory && !editing" bordered separator class="q-mt-md">
          <q-item-label header>Versions</q-item-label>
          <q-item v-for="v in history" :key="v.id">
            <q-item-section avatar>
              <q-badge :color="v.version === floorPlan?.version ? 'primary' : 'grey'">v{{ v.version }}</q-badge>
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ v.name }} — {{ v.change_type }}</q-item-label>
              <q-item-label caption lines="2">{{ v.change_note || '' }}</q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn
                v-if="v.version !== floorPlan?.version"
                flat dense label="Restore" :loading="saving" @click="restore(v)"
              />
            </q-item-section>
          </q-item>
        </q-list>
      </template>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { apiClient } from 'src/services/api'

interface Point { x: number; y: number; z: number }
interface Bounds { x0: number; x1: number; z0: number; z1: number }
interface PlanRoom {
  id: number
  name: string
  bounds: Bounds
  dimensions: { length: number; width: number; height: number }
  connects_to?: number[]
}
interface Opening {
  id: number
  position: Point
  width: number
  rotation: number
  door_type?: string
}
// The saved plan (sizes in feet), as GET /projects/{id}/floor-plan returns it.
interface LayoutNode {
  size?: number
  room?: string
  split?: 'x' | 'z'
  parts?: LayoutNode[]
  length?: number
  width?: number
  entry?: string
}
interface PlanRoomSpec {
  name: string
  connects_to?: string[]
  [key: string]: unknown
}
interface FloorPlan {
  id: number
  version: number
  name: string
  layout: LayoutNode | null
  rooms: PlanRoomSpec[]
  change_type: string
  change_note: string | null
  image_url: string | null
}
interface Draft {
  name: string
  layout: LayoutNode
  rooms: PlanRoomSpec[]
}

const props = defineProps<{ projectId?: number }>()
// The floor plan's name is the house (and project) name.
const emit = defineEmits<{ (e: 'renamed', name: string): void }>()

// Wall stroke width in plan units (metres).
const WALL = 0.2
const MARGIN = 1.2

const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const saveError = ref<string | null>(null)
const rooms = ref<PlanRoom[]>([])
const doors = ref<Opening[]>([])
const windows = ref<Opening[]>([])
const floorPlan = ref<FloorPlan | null>(null)
const history = ref<FloorPlan[]>([])
const showHistory = ref(false)
const editing = ref(false)
const draft = ref<Draft | null>(null)
const instruction = ref('')

const frontDoor = computed(() => doors.value.find(d => d.door_type === 'exterior'))
const interiorDoorCount = computed(() => doors.value.filter(d => d.door_type !== 'exterior').length)

const extent = computed(() => {
  const b = rooms.value.map(r => r.bounds)
  return {
    x0: Math.min(...b.map(r => r.x0)),
    x1: Math.max(...b.map(r => r.x1)),
    z0: Math.min(...b.map(r => r.z0)),
    z1: Math.max(...b.map(r => r.z1))
  }
})

// Front of the house (lowest z, where the entry is) is drawn at the bottom.
const svgY = (z: number) => extent.value.z1 - z

const viewBox = computed(() => {
  const e = extent.value
  return `${e.x0 - MARGIN} ${-MARGIN} ${e.x1 - e.x0 + 2 * MARGIN} ${e.z1 - e.z0 + 2 * MARGIN}`
})

// rotation 0 = wall runs along x, 90 = along z (same convention as the headset).
const along = (o: Opening) => (o.rotation % 180 === 0 ? { dx: 1, dz: 0 } : { dx: 0, dz: 1 })

const span = (o: Opening) => {
  const { dx, dz } = along(o)
  const h = o.width / 2
  return {
    x1: o.position.x - dx * h, y1: svgY(o.position.z - dz * h),
    x2: o.position.x + dx * h, y2: svgY(o.position.z + dz * h)
  }
}

const jambs = (o: Opening) => {
  const { dx, dz } = along(o)
  const h = o.width / 2
  const t = WALL
  return [-1, 1].map(side => {
    const x = o.position.x + dx * h * side
    const z = o.position.z + dz * h * side
    return { x1: x - dz * t, y1: svgY(z - dx * t), x2: x + dz * t, y2: svgY(z + dx * t) }
  })
}

const feet = (metres: number) => Math.round(metres / 0.3048)

const ROOM_COLORS: [string[], string][] = [
  [['bed'], '#E3F2FD'],
  [['bath', 'powder', 'laundry'], '#E0F7FA'],
  [['kitchen', 'dining', 'pantry'], '#FFF3E0'],
  [['living', 'family', 'great', 'den', 'office'], '#E8F5E9'],
  [['hall', 'corridor', 'foyer', 'entry'], '#F5F5F5'],
  [['garage'], '#EFEBE9']
]

const roomColor = (name: string) => {
  const n = name.toLowerCase()
  return ROOM_COLORS.find(([keys]) => keys.some(k => n.includes(k)))?.[1] ?? '#FAFAFA'
}

// Images are served by the backend (/generated_images/...), not under /api/v1.
const imageSrc = (path: string) => {
  const base = String(apiClient.client.defaults?.baseURL ?? '')
  return base.replace(/\/api\/v1\/?$/, '') + path
}

const errorMessage = (err: unknown, fallback: string) => {
  const e = err as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = e.response?.data?.detail
  return typeof detail === 'string' ? detail : e.message || fallback
}

const showGeometry = (geometry: any) => {
  rooms.value = (geometry?.rooms ?? []).filter((r: PlanRoom) => r.bounds)
  doors.value = geometry?.doors ?? []
  windows.value = geometry?.windows ?? []
}

const load = async () => {
  if (!props.projectId) return
  loading.value = true
  error.value = null
  saveError.value = null
  editing.value = false
  showHistory.value = false
  history.value = []
  try {
    const response = await apiClient.client.get(`/projects/${props.projectId}/generate-vr`)
    showGeometry(response.data?.geometry ?? {})
    floorPlan.value = null
    // Projects saved before floor plans existed have none: view only.
    if (response.data?.geometry?.floor_plan) {
      const plan = await apiClient.client.get(`/projects/${props.projectId}/floor-plan`)
      floorPlan.value = plan.data?.rooms ? plan.data : null
    }
  } catch (err) {
    error.value = errorMessage(err, 'Failed to load floor plan')
    rooms.value = []
  } finally {
    loading.value = false
  }
}

// --- Editing -------------------------------------------------------------

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

const startEditing = () => {
  if (!floorPlan.value?.layout) {
    saveError.value = 'This floor plan has no layout to edit; describe a change instead.'
    return
  }
  draft.value = {
    name: floorPlan.value.name,
    layout: clone(floorPlan.value.layout),
    rooms: clone(floorPlan.value.rooms)
  }
  saveError.value = null
  editing.value = true
}

const cancelEditing = () => {
  editing.value = false
  draft.value = null
  saveError.value = null
}

const draftRoomNames = computed(() => draft.value?.rooms.map(r => r.name) ?? [])

// Every part of every split, in drawing order, indented by depth.
const partRows = computed(() => {
  const rows: { part: LayoutNode; axis: 'x' | 'z'; depth: number }[] = []
  const walk = (node: LayoutNode, depth: number) => {
    if (!node.split || !node.parts) return
    for (const part of node.parts) {
      rows.push({ part, axis: node.split, depth })
      walk(part, depth + 1)
    }
  }
  if (draft.value) walk(draft.value.layout, 0)
  return rows
})

const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase()

/** Rename a room everywhere it is referenced: layout leaf, room list, doorways, entry. */
const renameRoom = (part: LayoutNode, name: string) => {
  const d = draft.value
  const old = part.room
  if (!d || old === undefined) return
  part.room = name
  for (const room of d.rooms) {
    if (same(room.name, old)) room.name = name
    room.connects_to = (room.connects_to ?? []).map(n => (same(n, old) ? name : n))
  }
  if (d.layout.entry && same(d.layout.entry, old)) d.layout.entry = name
}

/** Doorways are two-way: adding or removing one updates both rooms. */
const setConnections = (roomName: string, names: string[]) => {
  const d = draft.value
  if (!d) return
  for (const room of d.rooms) {
    if (same(room.name, roomName)) {
      room.connects_to = [...names]
      continue
    }
    const others = (room.connects_to ?? []).filter(n => !same(n, roomName))
    room.connects_to = names.some(n => same(n, room.name)) ? [...others, roomName] : others
  }
}

/** Store a new version and draw the geometry the backend returns for it. */
const applyNewVersion = (data: any) => {
  const renamed = floorPlan.value && data.floor_plan.name !== floorPlan.value.name
  floorPlan.value = data.floor_plan
  showGeometry(data.geometry)
  history.value = []
  showHistory.value = false
  if (renamed) emit('renamed', data.floor_plan.name)
}

const save = async (body: Record<string, unknown>) => {
  saving.value = true
  saveError.value = null
  try {
    const response = await apiClient.client.put(`/projects/${props.projectId}/floor-plan`, body)
    applyNewVersion(response.data)
    return true
  } catch (err) {
    saveError.value = errorMessage(err, 'Failed to save the floor plan')
    return false
  } finally {
    saving.value = false
  }
}

const saveDraft = async () => {
  if (!draft.value) return
  if (await save({ ...clone(draft.value), note: 'Edited in the dashboard' })) cancelEditing()
}

const refine = async () => {
  const text = instruction.value.trim()
  if (!text || saving.value) return
  saving.value = true
  saveError.value = null
  try {
    const response = await apiClient.client.post(
      `/projects/${props.projectId}/floor-plan/refine`, { instruction: text }
    )
    applyNewVersion(response.data)
    instruction.value = ''
  } catch (err) {
    saveError.value = errorMessage(err, 'Failed to change the floor plan')
  } finally {
    saving.value = false
  }
}

// --- History -------------------------------------------------------------

const toggleHistory = async () => {
  showHistory.value = !showHistory.value
  if (!showHistory.value || history.value.length) return
  try {
    const response = await apiClient.client.get(`/projects/${props.projectId}/floor-plans`)
    history.value = response.data?.floor_plans ?? []
  } catch (err) {
    saveError.value = errorMessage(err, 'Failed to load versions')
  }
}

const restore = (version: FloorPlan) =>
  save({
    name: version.name,
    layout: version.layout,
    rooms: version.rooms,
    note: `Restored version ${version.version}`
  })

watch(() => props.projectId, load, { immediate: true })
</script>

<style scoped>
.floor-plan {
  width: 100%;
  max-height: 480px;
  display: block;
}
.room-name {
  font-size: 0.42px;
  font-weight: 600;
  fill: #263238;
}
.room-size {
  font-size: 0.32px;
  fill: #607D8B;
}
.entry {
  font-size: 0.4px;
  font-weight: 600;
  fill: #2E7D32;
}
.swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  vertical-align: middle;
}
.rendering {
  max-width: 100%;
  max-height: 240px;
  border-radius: 4px;
}
.editor {
  max-height: 640px;
  overflow-y: auto;
}
</style>

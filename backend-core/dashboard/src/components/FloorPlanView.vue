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
              <!-- Open (outdoor) parts of the footprint: an L/U/T-shaped house -->
              <g v-for="(area, i) in openAreas" :key="`o${i}`">
                <rect
                  :x="area.bounds.x0"
                  :y="svgY(area.bounds.z1)"
                  :width="area.bounds.x1 - area.bounds.x0"
                  :height="area.bounds.z1 - area.bounds.z0"
                  fill="#F1F8E9"
                  stroke="#AED581"
                  stroke-width="0.06"
                  stroke-dasharray="0.3 0.2"
                />
                <text
                  :x="(area.bounds.x0 + area.bounds.x1) / 2"
                  :y="svgY((area.bounds.z0 + area.bounds.z1) / 2) + 0.15"
                  text-anchor="middle"
                  class="open-name"
                >Outside</text>
              </g>

              <!-- Yard: plants, paths, patios and fences, seen from above -->
              <g v-for="(part, i) in landscape" :key="`l${i}`" :transform="partTransform(part)">
                <ellipse
                  v-if="part.shape === 'sphere'"
                  :rx="part.size.x / 2" :ry="part.size.z / 2" :fill="rgb(part.color)"
                />
                <rect
                  v-else
                  :x="-part.size.x / 2" :y="-part.size.z / 2"
                  :width="part.size.x" :height="part.size.z" :fill="rgb(part.color)"
                />
              </g>

              <!-- Plants (vr_plants.py): hedges as their line, the rest by their spread -->
              <template v-for="(plant, i) in plantsToDraw">
                <line
                  v-if="plant.line"
                  :key="`h${i}`"
                  class="hedge"
                  :x1="plant.line.from.x" :y1="svgY(plant.line.from.z)"
                  :x2="plant.line.to.x" :y2="svgY(plant.line.to.z)"
                  :stroke="rgb(plant.color)" :stroke-width="plant.line.width" stroke-linecap="round"
                />
                <circle
                  v-else
                  :key="`p${i}`"
                  class="plant"
                  :cx="plant.position.x" :cy="svgY(plant.position.z)" :r="plant.scale.x / 2"
                  :fill="rgb(plant.color)" stroke="rgba(0,0,0,0.25)" stroke-width="0.04"
                ><title>{{ plant.name ?? '' }}</title></circle>
              </template>
              <!-- Plants drawn with a 3D model made from a photo -->
              <circle
                v-for="(model, i) in plantModels" :key="`m${i}`"
                class="plant-model"
                :cx="model.position.x" :cy="svgY(model.position.z)" :r="model.width / 2"
                fill="#C8E6C9" stroke="#2E7D32" stroke-width="0.06" stroke-dasharray="0.15 0.1"
              ><title>{{ model.name }} (from a photo)</title></circle>

              <!-- Bay window bump-outs -->
              <polygon
                v-for="room in baysToDraw" :key="`bay${room.id}`"
                :points="bayPoints(room)"
                :fill="roomColor(room.name)"
                stroke="#37474F"
                :stroke-width="WALL"
                stroke-linejoin="miter"
              />

              <!-- Rooms -->
              <rect
                v-for="room in rooms" :key="room.id"
                :x="room.bounds.x0"
                :y="svgY(room.bounds.z1)"
                :width="room.bounds.x1 - room.bounds.x0"
                :height="room.bounds.z1 - room.bounds.z0"
                :fill="roomColor(room.name)"
                stroke="#37474F"
                :stroke-width="WALL"
              />

              <!-- Furniture (vr_furniture.py), seen from above; rugs first, under the rest -->
              <polygon
                v-for="(piece, i) in furnitureToDraw" :key="`f${i}`"
                class="furniture"
                :class="{ rug: piece.type === 'rug', 'furniture-model': piece.model_id }"
                :points="outlinePoints(piece)"
                :fill="rgb(piece.color)"
                :stroke="piece.model_id ? '#6A1B9A' : 'rgba(0,0,0,0.45)'"
                stroke-width="0.03"
                :stroke-dasharray="piece.model_id ? '0.12 0.08' : undefined"
              ><title>{{ piece.name ?? words(piece.type) }}{{ piece.model_id ? ' (from a photo)' : '' }}</title></polygon>

              <!-- Room names over the furniture -->
              <g v-for="room in rooms" :key="`t${room.id}`">
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

              <!-- Walls taken out between open rooms: a dashed line where the wall was -->
              <g v-for="(o, i) in openWalls" :key="`ow${i}`">
                <line v-bind="wallLine(o)" stroke="#FAFAFA" :stroke-width="WALL * 1.1" />
                <line v-bind="wallLine(o)" stroke="#90A4AE" stroke-width="0.05" stroke-dasharray="0.25 0.2" />
              </g>

              <!-- Windows: glazing line over the wall -->
              <g v-for="w in windows" :key="`w${w.id}`">
                <line v-bind="span(w)" stroke="#FFFFFF" :stroke-width="WALL * 1.4" />
                <line v-bind="span(w)" stroke="#4FC3F7" :stroke-width="WALL * 0.6" />
              </g>

              <!-- Doors: a gap in the wall with jamb ticks; doors to the yard in green,
                   with the glass drawn in for a sliding glass or French door -->
              <g v-for="d in doors" :key="`d${d.id}`" :class="{ 'patio-door': d.door_type === 'patio' }">
                <line v-bind="span(d)" stroke="#FFFFFF" :stroke-width="WALL * 1.6" />
                <line
                  v-if="d.door_type === 'patio' && d.style !== 'hinged'"
                  v-bind="span(d)" stroke="#4FC3F7" :stroke-width="WALL * 0.4"
                />
                <line
                  v-for="(tick, i) in jambs(d)" :key="i" v-bind="tick"
                  :stroke="d.door_type === 'patio' ? '#2E7D32' : '#6D4C41'" :stroke-width="0.06"
                />
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
              <span v-if="patioDoors.length">{{ patioDoors.length }} to the yard</span>
              <span>{{ windows.length }} windows</span>
              <span><span class="swatch" style="background:#4FC3F7" /> window</span>
              <span><span class="swatch" style="background:#6D4C41" /> doorway</span>
              <span v-if="patioDoors.length"><span class="swatch" style="background:#2E7D32" /> door to the yard</span>
              <span v-if="openWalls.length"><span class="swatch" style="background:#90A4AE" /> open (no wall)</span>
            </div>
            <!-- Requested doors / bay windows that did not fit -->
            <div v-for="(note, i) in notes" :key="`n${i}`" class="text-caption text-orange-9 plan-note">
              ⚠ {{ note }}
            </div>

            <!-- The outside, as the AI last described it -->
            <div v-if="exterior" class="row q-gutter-md text-caption text-grey-8 q-mt-xs exterior-summary">
              <span v-if="exterior.roof">
                <span class="swatch" :style="{ background: exterior.roof.color }" />
                {{ words(exterior.roof.style) }} roof, {{ words(exterior.roof.material) }}
              </span>
              <span v-if="exterior.walls">
                <span class="swatch" :style="{ background: exterior.walls.color }" />
                {{ words(exterior.walls.material) }} walls
              </span>
              <span v-if="exterior.landscape?.length">{{ landscapeSummary }}</span>
            </div>
            <div v-if="furniture.length" class="text-caption text-grey-8 q-mt-xs furniture-summary">
              🛋 {{ furnitureSummary }}
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
                label="Describe a change (e.g. make the kitchen bigger, tile roof, palm trees out front)"
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
                <span v-else-if="row.part.open" class="text-green-8">Outside (open area)</span>
                <span v-else class="text-grey-8">
                  {{ row.part.split === 'x' ? 'Side-by-side group' : 'Front-to-back group' }}
                </span>
              </div>
              <q-btn
                v-if="row.part.room !== undefined || row.part.open"
                flat dense round size="sm" class="q-mr-xs"
                :icon="row.part.open ? 'meeting_room' : 'park'"
                :disable="row.part.room !== undefined && draft.rooms.length <= 1"
                @click="row.part.open ? makeRoom(row.part) : makeOpen(row.part)"
              >
                <q-tooltip>{{ row.part.open ? 'Make this a room' : 'Make this outside (changes the house shape)' }}</q-tooltip>
              </q-btn>
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

            <div class="text-subtitle2 q-mt-md">Bay windows</div>
            <div class="text-caption text-grey-7 q-mb-xs">
              Only on an outside wall; sizes in feet. A bay replaces the room's ordinary window.
            </div>
            <div v-for="(room, i) in draft.rooms" :key="`bay${i}`" class="row items-center q-gutter-xs q-mb-xs">
              <div class="ellipsis" style="width: 120px">{{ room.name }}</div>
              <q-select
                :model-value="room.bay_window?.side ?? 'none'"
                :options="BAY_SIDES" emit-value map-options dense outlined style="width: 90px"
                :aria-label="`Bay window side for ${room.name}`"
                @update:model-value="side => setBaySide(room, side)"
              />
              <template v-if="room.bay_window">
                <q-select
                  v-model="room.bay_window.style" :options="BAY_STYLES"
                  emit-value map-options dense outlined style="width: 95px"
                />
                <q-input
                  v-model.number="room.bay_window.width" type="number" dense outlined
                  style="width: 120px" suffix="ft wide" min="4" step="0.5"
                  :aria-label="`Bay window width for ${room.name}`"
                />
                <q-input
                  v-model.number="room.bay_window.depth" type="number" dense outlined
                  style="width: 120px" suffix="ft deep" min="1" max="6" step="0.5"
                  :aria-label="`Bay window depth for ${room.name}`"
                />
              </template>
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
  bay_window?: { outline: { x: number; z: number }[] } | null
}
// The outside of the house (vr_exterior.py): parts in metres, the spec in feet.
interface ExteriorPart {
  shape: 'box' | 'sphere'
  center: Point
  size: Point
  yaw: number
  color: { r: number; g: number; b: number }
  kind: string
}
// A plant: a shared mesh at a position and size, or one baked mesh (beds, hedges).
interface ExteriorPlant {
  mesh: string
  position: Point
  scale: Point
  color: { r: number; g: number; b: number }
  name?: string
  baked?: boolean
  line?: { from: { x: number; z: number }; to: { x: number; z: number }; width: number }
}
// A piece of furniture (vr_furniture.py): its plan outline in metres; model_id when
// it is drawn with a 3D model made from a photo.
interface FurniturePiece {
  type: string
  name?: string
  room: number
  outline: [number, number][]
  color: { r: number; g: number; b: number }
  model_id?: number
}
// A plant drawn with a 3D model made from a photo (plant_model_service.py).
interface ExteriorModel {
  model_id: number
  name: string
  position: Point
  width: number
}
interface ExteriorSpec {
  roof?: { style: string; material: string; color: string }
  walls?: { material: string; color: string }
  landscape?: { type: string; plant?: string }[]
}
interface Opening {
  id: number
  position: Point
  width: number
  rotation: number
  door_type?: string
  // Doors to the yard ("patio"): sliding_glass | french | hinged.
  style?: string
}
// The saved plan (sizes in feet), as GET /projects/{id}/floor-plan returns it.
interface LayoutNode {
  size?: number
  room?: string
  // An outdoor part of the footprint (gives the house an L/U/T shape).
  open?: boolean
  split?: 'x' | 'z'
  parts?: LayoutNode[]
  length?: number
  width?: number
  entry?: string
}
interface BayWindowSpec {
  side: 'front' | 'back' | 'left' | 'right'
  style?: 'angled' | 'box'
  width?: number
  depth?: number
}
// A wall taken out between two open rooms ("open_to").
interface OpenWall { rooms: number[]; start: Point; end: Point }
interface PlanRoomSpec {
  name: string
  connects_to?: string[]
  no_door_to?: string[]
  open_to?: string[]
  bay_window?: BayWindowSpec
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
const openWalls = ref<OpenWall[]>([])
const notes = ref<string[]>([])
const openAreas = ref<{ bounds: Bounds }[]>([])
const landscape = ref<ExteriorPart[]>([])
const plants = ref<ExteriorPlant[]>([])
const plantModels = ref<ExteriorModel[]>([])
// A flower bed's flowers are shown by the bed itself.
const plantsToDraw = computed(() => plants.value.filter(p => !p.baked || p.line))
const exterior = ref<ExteriorSpec | null>(null)
const furniture = ref<FurniturePiece[]>([])
const furnitureToDraw = computed(() =>
  [...furniture.value].sort((a, b) => Number(b.type === 'rug') - Number(a.type === 'rug')))
const floorPlan = ref<FloorPlan | null>(null)
const history = ref<FloorPlan[]>([])
const showHistory = ref(false)
const editing = ref(false)
const draft = ref<Draft | null>(null)
const instruction = ref('')

const frontDoor = computed(() => doors.value.find(d => d.door_type === 'exterior'))
const patioDoors = computed(() => doors.value.filter(d => d.door_type === 'patio'))
const interiorDoorCount = computed(() => doors.value.filter(d => d.door_type !== 'exterior' && d.door_type !== 'patio').length)

const extent = computed(() => {
  const b = [...rooms.value, ...openAreas.value].map(r => r.bounds)
  for (const room of rooms.value) {
    for (const p of room.bay_window?.outline ?? []) b.push({ x0: p.x, x1: p.x, z0: p.z, z1: p.z })
  }
  for (const p of landscape.value) {
    const r = Math.max(p.size.x, p.size.z) / 2
    b.push({ x0: p.center.x - r, x1: p.center.x + r, z0: p.center.z - r, z1: p.center.z + r })
  }
  for (const p of plantsToDraw.value) {
    if (p.line) {
      const { from, to } = p.line
      b.push({ x0: Math.min(from.x, to.x), x1: Math.max(from.x, to.x), z0: Math.min(from.z, to.z), z1: Math.max(from.z, to.z) })
    } else {
      const r = p.scale.x / 2
      b.push({ x0: p.position.x - r, x1: p.position.x + r, z0: p.position.z - r, z1: p.position.z + r })
    }
  }
  for (const m of plantModels.value) {
    const r = m.width / 2
    b.push({ x0: m.position.x - r, x1: m.position.x + r, z0: m.position.z - r, z1: m.position.z + r })
  }
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

// rotation is the wall's direction in degrees: 0 = along x, 90 = along z, and the
// faces of an angled bay window in between (same convention as the headset).
const along = (o: Opening) => {
  const rad = (o.rotation * Math.PI) / 180
  return { dx: Math.cos(rad), dz: Math.sin(rad) }
}

const outlinePoints = (piece: FurniturePiece) =>
  piece.outline.map(([x, z]) => `${x},${svgY(z)}`).join(' ')

const furnitureSummary = computed(() => {
  const counts = new Map<string, number>()
  for (const piece of furniture.value) {
    if (piece.type === 'rug') continue
    const name = words(piece.type)
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  const fromPhotos = furniture.value.filter(p => p.model_id).length
  const total = [...counts.values()].reduce((a, b) => a + b, 0)
  const top = [...counts].sort((a, b) => b[1] - a[1]).slice(0, 4)
    .map(([name, n]) => `${n} ${name}${n > 1 && !name.endsWith('s') ? 's' : ''}`)
  return `${total} pieces of furniture` + (top.length ? ` (${top.join(', ')}${counts.size > 4 ? ', …' : ''})` : '') +
    (fromPhotos ? `, ${fromPhotos} from photos` : '')
})

const wallLine = (o: OpenWall) => ({ x1: o.start.x, y1: svgY(o.start.z), x2: o.end.x, y2: svgY(o.end.z) })

const baysToDraw = computed(() => rooms.value.filter(r => r.bay_window?.outline?.length))
const bayPoints = (room: PlanRoom) =>
  (room.bay_window?.outline ?? []).map(p => `${p.x},${svgY(p.z)}`).join(' ')

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
    // Across the wall: perpendicular to (dx, dz).
    return { x1: x - dz * t, y1: svgY(z + dx * t), x2: x + dz * t, y2: svgY(z - dx * t) }
  })
}

const feet = (metres: number) => Math.round(metres / 0.3048)

const rgb = (c: ExteriorPart['color']) =>
  `rgb(${Math.round(c.r * 255)}, ${Math.round(c.g * 255)}, ${Math.round(c.b * 255)})`

// yaw turns the part's x axis toward +z; the plan is drawn with z flipped.
const partTransform = (p: ExteriorPart) =>
  `translate(${p.center.x} ${svgY(p.center.z)}) rotate(${-p.yaw})`

const words = (key: string) => key.replace(/_/g, ' ')

const landscapeSummary = computed(() => {
  const counts = new Map<string, number>()
  for (const item of exterior.value?.landscape ?? []) {
    const name = (item.plant || words(item.type)).toLowerCase()
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  const fromPhotos = plantModels.value.length
  return [...counts].map(([name, n]) => `${n} ${name}${n > 1 && !name.endsWith('s') ? 's' : ''}`).join(', ') +
    (fromPhotos ? ` (${fromPhotos} from photos)` : '')
})

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
  notes.value = geometry?.notes ?? []
  windows.value = geometry?.windows ?? []
  openWalls.value = geometry?.open_walls ?? []
  openAreas.value = (geometry?.open_areas ?? []).filter((a: { bounds?: Bounds }) => a.bounds)
  // Lowest first, so canopies cover their trunks and tiles their bed.
  landscape.value = ((geometry?.exterior?.parts ?? []) as ExteriorPart[])
    .filter(p => p.kind === 'landscape')
    .sort((a, b) => a.center.y + a.size.y / 2 - (b.center.y + b.size.y / 2))
  plants.value = geometry?.exterior?.plants ?? []
  plantModels.value = geometry?.exterior?.models ?? []
  exterior.value = geometry?.exterior?.spec ?? null
  furniture.value = [...(geometry?.furniture?.pieces ?? []), ...(geometry?.furniture?.models ?? [])]
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

// Room fields that hold other rooms' names (doorways, blocked doorways, open walls).
const ROOM_REFS = ['connects_to', 'no_door_to', 'open_to'] as const

/** Rename a room everywhere it is referenced: layout leaf, room list, doorways, entry. */
const renameRoom = (part: LayoutNode, name: string) => {
  const d = draft.value
  const old = part.room
  if (!d || old === undefined) return
  part.room = name
  for (const room of d.rooms) {
    if (same(room.name, old)) room.name = name
    for (const key of ROOM_REFS) {
      if (room[key]) room[key] = room[key]!.map(n => (same(n, old) ? name : n))
    }
  }
  if (d.layout.entry && same(d.layout.entry, old)) d.layout.entry = name
}

const BAY_SIDES = [
  { label: 'None', value: 'none' },
  { label: 'Front', value: 'front' },
  { label: 'Back', value: 'back' },
  { label: 'Left', value: 'left' },
  { label: 'Right', value: 'right' }
]
const BAY_STYLES = [
  { label: 'Angled', value: 'angled' },
  { label: 'Box', value: 'box' }
]

/** Add, move or remove a room's bay window. */
const setBaySide = (room: PlanRoomSpec, side: string) => {
  if (side === 'none') {
    delete room.bay_window
    return
  }
  room.bay_window = {
    style: 'angled', width: 8, depth: 2.5,
    ...room.bay_window,
    side: side as BayWindowSpec['side']
  }
}

/** Turn a room into an outdoor part of the footprint, dropping it from the room list. */
const makeOpen = (part: LayoutNode) => {
  const d = draft.value
  const name = part.room
  if (!d || name === undefined) return
  delete part.room
  part.open = true
  d.rooms = d.rooms.filter(r => !same(r.name, name))
  for (const room of d.rooms) {
    room.connects_to = (room.connects_to ?? []).filter(n => !same(n, name))
    for (const key of ['no_door_to', 'open_to'] as const) {
      if (room[key]) room[key] = room[key]!.filter(n => !same(n, name))
    }
  }
  if (d.layout.entry && same(d.layout.entry, name)) d.layout.entry = d.rooms[0]?.name
}

/** Turn an outdoor part back into a (new, unconnected) room. */
const makeRoom = (part: LayoutNode) => {
  const d = draft.value
  if (!d) return
  let n = d.rooms.length + 1
  while (d.rooms.some(r => same(r.name, `Room ${n}`))) n++
  delete part.open
  part.room = `Room ${n}`
  d.rooms.push({ name: part.room, dimensions: { height: 9 }, connects_to: [] })
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
.room-name,
.room-size {
  /* A halo, so the names read over the furniture */
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.75);
  stroke-width: 0.08px;
}
.room-name {
  font-size: 0.42px;
  font-weight: 600;
  fill: #263238;
}
.open-name {
  font-size: 0.45px;
  fill: #7CB342;
  font-style: italic;
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
.furniture {
  fill-opacity: 0.85;
}
.furniture.rug {
  fill-opacity: 0.45;
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

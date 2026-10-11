<template>
  <q-card>
    <q-card-section class="row items-center">
      <div class="col">
        <div class="text-h6">Floor Plan</div>
        <div class="text-caption text-grey-7">
          Layout sent to the headset — doorways show how rooms connect
        </div>
      </div>
      <q-btn flat round icon="refresh" :loading="loading" :disable="!projectId" @click="load">
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

const props = defineProps<{ projectId?: number }>()

// Wall stroke width in plan units (metres).
const WALL = 0.2
const MARGIN = 1.2

const loading = ref(false)
const error = ref<string | null>(null)
const rooms = ref<PlanRoom[]>([])
const doors = ref<Opening[]>([])
const windows = ref<Opening[]>([])

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

const load = async () => {
  if (!props.projectId) return
  loading.value = true
  error.value = null
  try {
    const response = await apiClient.client.get(`/projects/${props.projectId}/generate-vr`)
    const geometry = response.data?.geometry ?? {}
    rooms.value = (geometry.rooms ?? []).filter((r: PlanRoom) => r.bounds)
    doors.value = geometry.doors ?? []
    windows.value = geometry.windows ?? []
  } catch (err) {
    error.value = (err as Error).message || 'Failed to load floor plan'
    rooms.value = []
  } finally {
    loading.value = false
  }
}

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
</style>

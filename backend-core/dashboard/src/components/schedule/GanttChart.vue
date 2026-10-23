<template>
  <div class="gantt" role="table" aria-label="Schedule by phase">
    <!-- Scale -->
    <div class="gantt-row gantt-scale" role="row">
      <div class="gantt-label text-caption text-muted" role="columnheader">{{ baselined ? 'Phase' : 'Phase (by duration — not baselined)' }}</div>
      <div class="gantt-track" role="columnheader">
        <span v-for="tick in ticks" :key="tick.at" class="gantt-tick text-caption text-muted" :style="{ left: `${tick.at}%` }">{{ tick.label }}</span>
      </div>
    </div>

    <template v-for="row in rows" :key="row.key">
      <div class="gantt-row" :class="{ 'gantt-task': row.task }" role="row">
        <div class="gantt-label ellipsis" role="cell" :class="row.task ? 'text-body2 q-pl-md' : 'text-body2 text-weight-medium'">
          <q-icon v-if="!row.task" :name="expanded.has(row.id) ? 'expand_more' : 'chevron_right'" size="18px" class="cursor-pointer text-muted" @click="toggle(row.id)" />
          {{ row.name }}
        </div>
        <div class="gantt-track" role="cell">
          <div v-if="todayAt !== null" class="gantt-today" :style="{ left: `${todayAt}%` }" />
          <div
            class="gantt-bar"
            :class="[`bg-${row.color}`, { late: row.late, thin: row.task }]"
            :style="{ left: `${row.left}%`, width: `${Math.max(row.width, 0.8)}%` }"
          >
            <!-- the saturated part is earned; the rest is washed out -->
            <div class="gantt-unearned" :style="{ left: `${row.progress}%` }" />
            <q-tooltip>
              <div class="text-weight-bold">{{ row.name }}</div>
              <div>{{ row.statusLabel }} · {{ Math.round(row.progress) }}% earned{{ row.late ? ' · late' : '' }}</div>
              <div v-if="row.start">{{ formatDate(row.start) }} → {{ formatDate(row.end) }}</div>
              <div>{{ row.days }} day{{ row.days === 1 ? '' : 's' }}</div>
            </q-tooltip>
          </div>
        </div>
      </div>
    </template>

    <div class="row q-gutter-md q-mt-sm text-caption text-muted">
      <span v-for="l in legend" :key="l.label" class="row items-center no-wrap"><span :class="`legend-swatch bg-${l.color}`" />{{ l.label }}</span>
      <span class="row items-center no-wrap"><span class="legend-swatch legend-earned" />Earned (solid) / remaining (pale)</span>
      <span v-if="todayAt !== null" class="row items-center no-wrap"><span class="legend-today" />Today</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SchedulePhase } from 'src/types/controls'
import { formatDate, parseDate, titleCase } from 'src/utils/format'
import { statusColor } from 'src/utils/status'

const props = defineProps<{ phases: SchedulePhase[]; baselined: boolean }>()

const DAY = 86_400_000
const expanded = ref(new Set<number>())
const toggle = (id: number) => {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

interface Span { start: number; end: number }

// Each phase and task as [start, end] in days: from its planned dates when the
// schedule is baselined, else laid end to end by duration from day 0.
const spans = computed(() => {
  const result = new Map<string, Span>()
  let cursor = 0
  for (const phase of props.phases) {
    if (props.baselined && phase.planned_start && phase.planned_end) {
      result.set(`p${phase.id}`, { start: parseDate(phase.planned_start)!.getTime() / DAY, end: parseDate(phase.planned_end)!.getTime() / DAY })
      for (const t of phase.tasks) {
        if (t.planned_start && t.planned_end) {
          result.set(`t${t.id}`, { start: parseDate(t.planned_start)!.getTime() / DAY, end: parseDate(t.planned_end)!.getTime() / DAY })
        }
      }
    } else {
      const start = cursor
      for (const t of phase.tasks) {
        result.set(`t${t.id}`, { start: cursor, end: cursor + Math.ceil(t.duration_days) })
        cursor += Math.ceil(t.duration_days)
      }
      if (!phase.tasks.length) cursor += Math.ceil(phase.duration_days)
      result.set(`p${phase.id}`, { start, end: cursor })
    }
  }
  return result
})

const range = computed(() => {
  const all = [...spans.value.values()]
  if (!all.length) return { start: 0, end: 1 }
  const start = Math.min(...all.map(s => s.start))
  const end = Math.max(...all.map(s => s.end))
  return { start, end: Math.max(end, start + 1) }
})
const pct = (day: number) => ((day - range.value.start) / (range.value.end - range.value.start)) * 100

const rows = computed(() => {
  const out = []
  for (const phase of props.phases) {
    const span = spans.value.get(`p${phase.id}`)
    if (!span) continue
    out.push({
      key: `p${phase.id}`, id: phase.id, task: false, name: phase.name,
      left: pct(span.start), width: pct(span.end) - pct(span.start),
      progress: phase.progress, color: statusColor('phase', phase.status), statusLabel: titleCase(phase.status),
      late: phase.late, start: phase.planned_start, end: phase.planned_end, days: Math.round(span.end - span.start)
    })
    if (!expanded.value.has(phase.id)) continue
    for (const t of phase.tasks) {
      const ts = spans.value.get(`t${t.id}`)
      if (!ts) continue
      out.push({
        key: `t${t.id}`, id: t.id, task: true, name: t.name,
        left: pct(ts.start), width: pct(ts.end) - pct(ts.start),
        progress: t.status === 'completed' ? 100 : t.status === 'in_progress' ? 50 : 0,
        color: statusColor('task', t.status), statusLabel: titleCase(t.status),
        late: t.late, start: t.planned_start, end: t.planned_end, days: t.duration_days
      })
    }
  }
  return out
})

const todayAt = computed(() => {
  if (!props.baselined) return null
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / DAY
  const at = pct(today)
  return at >= 0 && at <= 100 ? at : null
})

const ticks = computed(() => {
  const { start, end } = range.value
  const length = end - start
  const count = Math.min(6, Math.max(2, Math.floor(length / 7)))
  return Array.from({ length: count + 1 }, (_, i) => {
    const day = start + (length * i) / count
    const label = props.baselined
      ? new Date(day * DAY).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : `Day ${Math.round(day)}`
    return { at: (i / count) * 100, label }
  }).filter((_, i, all) => i < all.length - 1)
})

const legend = [
  { color: statusColor('phase', 'pending'), label: 'Not started' },
  { color: statusColor('phase', 'in_progress'), label: 'In progress' },
  { color: statusColor('phase', 'completed'), label: 'Completed' },
  { color: statusColor('task', 'blocked'), label: 'Blocked / late (outlined)' }
]
</script>

<style lang="sass" scoped>
.gantt
  overflow-x: auto

.gantt-row
  display: grid
  grid-template-columns: minmax(160px, 26%) 1fr
  align-items: center
  min-height: 34px
  min-width: 640px
  border-bottom: 1px solid var(--app-border)
  &.gantt-task
    min-height: 28px
    background: var(--app-surface-2)

.gantt-scale
  min-height: 26px

.gantt-label
  padding-right: 12px

.gantt-track
  position: relative
  height: 100%
  min-height: inherit

.gantt-tick
  position: absolute
  top: 4px
  white-space: nowrap
  border-left: 1px solid var(--app-border)
  padding-left: 4px

.gantt-bar
  position: absolute
  top: 50%
  height: 16px
  transform: translateY(-50%)
  border-radius: 4px
  overflow: hidden
  &.thin
    height: 10px
  &.late
    outline: 2px solid var(--q-negative)
    outline-offset: 1px

.gantt-unearned
  position: absolute
  top: 0
  bottom: 0
  right: 0
  background: rgba(255, 255, 255, 0.62)

.body--dark .gantt-unearned
  background: rgba(19, 28, 46, 0.58)

.gantt-today
  position: absolute
  top: 0
  bottom: 0
  width: 2px
  background: var(--q-negative)
  opacity: 0.7

.legend-swatch
  display: inline-block
  width: 12px
  height: 10px
  border-radius: 2px
  margin-right: 6px

.legend-earned
  background: linear-gradient(90deg, var(--q-primary) 50%, rgba(37, 99, 235, 0.35) 50%)

.legend-today
  display: inline-block
  width: 2px
  height: 12px
  background: var(--q-negative)
  margin-right: 6px
</style>

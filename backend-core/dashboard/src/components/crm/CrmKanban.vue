<template>
  <div class="kanban row no-wrap q-gutter-x-md">
    <div
      v-for="stage in stages"
      :key="stage.id"
      class="kanban-column column no-wrap"
      :class="{ 'drop-target': dragOver === stage.id }"
      @dragover.prevent="dragOver = stage.id"
      @dragleave="dragOver === stage.id && (dragOver = null)"
      @drop.prevent="drop(stage.id)"
    >
      <div class="kanban-column-header row items-center no-wrap q-px-sm q-py-xs">
        <q-icon :name="stage.icon" :color="stage.color" size="18px" class="q-mr-xs" />
        <div class="col ellipsis text-weight-bold text-body2">{{ stage.label }}</div>
        <q-badge color="blue-grey-2" text-color="blue-grey-9" :label="byStage(stage.id).length" />
      </div>
      <div class="text-caption text-muted q-px-sm q-pb-xs tabular">{{ formatCompactCurrency(stageValue(stage.id)) }}</div>

      <div class="col kanban-cards q-px-xs q-pb-sm">
        <q-card
          v-for="client in byStage(stage.id)"
          :key="client.id"
          flat
          class="kanban-card q-mb-sm"
          :class="{ selected: client.id === selectedId }"
          draggable="true"
          tabindex="0"
          @dragstart="dragging = client.id"
          @dragend="dragging = dragOver = null"
          @click="emit('open', client.id)"
          @keyup.enter="emit('open', client.id)"
        >
          <q-card-section class="q-pa-sm">
            <div class="row items-center no-wrap">
              <q-avatar size="28px" font-size="11px" :color="stage.color" text-color="white" class="q-mr-sm">{{ initials(client.name) }}</q-avatar>
              <div class="col min-width-0">
                <div class="text-weight-medium ellipsis">{{ client.name }}</div>
                <div class="text-caption text-muted ellipsis">{{ client.company || client.site_address || client.preferred_style || '—' }}</div>
              </div>
              <q-icon v-if="client.sentiment" name="circle" size="9px" :color="SENTIMENT_COLORS[client.sentiment]">
                <q-tooltip>{{ titleCase(client.sentiment) }}</q-tooltip>
              </q-icon>
            </div>
            <div class="row items-center justify-between q-mt-xs text-caption">
              <span class="text-weight-bold tabular">{{ formatCompactCurrency(client.deal_value) }}</span>
              <span class="text-muted tabular">{{ Math.round(client.win_probability) }}%</span>
            </div>
            <div v-if="client.next_follow_up_at" class="text-caption q-mt-xs row items-center no-wrap" :class="isPastDay(client.next_follow_up_at) || isToday(client.next_follow_up_at) ? 'text-warning text-weight-medium' : 'text-muted'">
              <q-icon name="schedule" size="13px" class="q-mr-xs" />
              <span class="ellipsis">{{ formatRelativeDay(client.next_follow_up_at) }}<template v-if="client.next_action"> · {{ client.next_action }}</template></span>
            </div>
            <div v-if="client.project_name" class="text-caption text-primary q-mt-xs row items-center no-wrap">
              <q-icon name="home_work" size="13px" class="q-mr-xs" /><span class="ellipsis">{{ client.project_name }}</span>
            </div>
          </q-card-section>
        </q-card>
        <div v-if="!byStage(stage.id).length" class="kanban-empty text-caption text-muted text-center q-pa-md">
          {{ dragging ? 'Drop here' : 'No clients' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { Client, LeadStage, PipelineStageConfig } from 'src/types/crm'
import { SENTIMENT_COLORS } from 'src/stores/crm'
import { formatCompactCurrency, formatRelativeDay, initials, isPastDay, titleCase } from 'src/utils/format'

const props = defineProps<{ clients: Client[]; stages: PipelineStageConfig[]; selectedId?: number | null }>()
const emit = defineEmits<{
  (e: 'open', clientId: number): void
  (e: 'move', payload: { clientId: number; stage: LeadStage }): void
}>()

const dragging = ref<number | null>(null)
const dragOver = ref<LeadStage | null>(null)

const byStage = (stage: LeadStage) => props.clients.filter(c => c.stage === stage)
const stageValue = (stage: LeadStage) => byStage(stage).reduce((sum, c) => sum + (c.deal_value || 0), 0)
const isToday = (iso: string) => formatRelativeDay(iso) === 'today'

const drop = (stage: LeadStage) => {
  const clientId = dragging.value
  dragging.value = dragOver.value = null
  const client = props.clients.find(c => c.id === clientId)
  if (client && client.stage !== stage) emit('move', { clientId: client.id, stage })
}
</script>

<style lang="sass" scoped>
.kanban
  overflow-x: auto
  padding-bottom: 8px

.kanban-column
  flex: 0 0 248px
  background: var(--app-surface-2)
  border: 1px solid var(--app-border)
  border-radius: 12px
  min-height: 420px
  max-height: calc(100vh - 330px)
  transition: border-color 0.15s ease, background 0.15s ease
  &.drop-target
    border-color: var(--q-primary)
    background: var(--app-accent-soft)

.kanban-column-header
  min-height: 36px

.kanban-cards
  overflow-y: auto

.kanban-card
  background: var(--app-surface)
  border: 1px solid var(--app-border)
  border-radius: 10px
  cursor: grab
  transition: border-color 0.15s ease, box-shadow 0.15s ease
  &:hover, &:focus-visible
    border-color: var(--q-primary)
    outline: none
  &.selected
    border-color: var(--q-primary)
    box-shadow: 0 0 0 1px var(--q-primary)

.kanban-empty
  border: 1px dashed var(--app-border)
  border-radius: 10px

.min-width-0
  min-width: 0
</style>

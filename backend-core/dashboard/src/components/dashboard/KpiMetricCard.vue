<template>
  <q-card
    flat
    class="app-card kpi-card full-height"
    :class="{ 'kpi-clickable': !!to }"
    :tabindex="to ? 0 : undefined"
    @click="go"
    @keyup.enter="go"
  >
    <q-card-section class="q-pa-md">
      <div class="row items-start no-wrap">
        <div class="col min-width-0">
          <div class="kpi-title text-muted ellipsis">
            {{ title }}
            <q-icon v-if="hint" name="info_outline" size="14px" class="q-ml-xs">
              <q-tooltip max-width="280px">{{ hint }}</q-tooltip>
            </q-icon>
          </div>
          <div class="kpi-value tabular q-mt-xs" :class="valueColor ? `text-${valueColor}` : ''">{{ value }}</div>
        </div>
        <q-avatar :icon="icon" size="38px" font-size="20px" :class="`kpi-icon bg-${tone} text-white`" />
      </div>
      <q-linear-progress
        v-if="progress !== undefined && progress !== null"
        :value="Math.min(Math.max(progress, 0), 100) / 100"
        :color="tone"
        track-color="grey-3"
        size="6px"
        rounded
        class="q-mt-sm"
      />
      <div v-if="caption || $slots.caption" class="text-caption text-muted q-mt-xs ellipsis">
        <slot name="caption">{{ caption }}</slot>
      </div>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = withDefaults(defineProps<{
  title: string
  value: string | number
  icon: string
  caption?: string
  hint?: string
  progress?: number | null
  tone?: string
  valueColor?: string
  to?: string
}>(), {
  tone: 'primary'
})

const router = useRouter()
const go = () => {
  if (props.to) router.push(props.to)
}
</script>

<style lang="sass" scoped>
.kpi-title
  font-size: 0.75rem
  font-weight: 600
  text-transform: uppercase
  letter-spacing: 0.05em

.kpi-value
  font-size: 1.6rem
  font-weight: 700
  line-height: 1.2

.kpi-icon
  opacity: 0.92
  border-radius: 10px

.kpi-clickable
  cursor: pointer
  transition: border-color 0.15s ease, transform 0.15s ease
  &:hover, &:focus-visible
    border-color: var(--q-primary)
    transform: translateY(-1px)
    outline: none

.min-width-0
  min-width: 0

.body--dark .q-linear-progress
  :deep(.q-linear-progress__track)
    opacity: 0.15
</style>

<template>
  <div class="timeline-gantt">
    <div v-if="loading" class="flex flex-center q-pa-md">
      <q-spinner size="32px" color="primary" />
    </div>
    <div v-else-if="!phases || phases.length === 0" class="text-center text-grey-6 q-pa-md">
      <q-icon name="timeline" size="48px" />
      <div class="q-mt-sm">No timeline data available</div>
    </div>
    <div v-else class="q-pa-md">
      <!-- Simple timeline visualization -->
      <div class="timeline-container">
        <div
          v-for="phase in sortedPhases"
          :key="phase.id"
          class="timeline-item q-mb-md"
        >
          <div class="timeline-header">
            <div class="timeline-title">{{ phase.name }}</div>
            <q-badge
              :color="getPhaseStatusColor(phase.status)"
              :label="phase.status.replace('_', ' ')"
              class="q-ml-sm"
            />
          </div>
          <div class="timeline-description text-grey-7 q-mt-xs">
            {{ phase.description }}
          </div>
          <div class="timeline-progress q-mt-sm">
            <div class="progress-label">
              <span>Progress: {{ phase.progress_percentage }}%</span>
              <span class="text-grey-6">
                {{ phase.estimated_duration_days }} days estimated
              </span>
            </div>
            <q-linear-progress
              :value="phase.progress_percentage / 100"
              :color="getPhaseStatusColor(phase.status)"
              size="8px"
              rounded
              class="q-mt-xs"
            />
          </div>
          <div class="timeline-dates text-caption text-grey-6 q-mt-xs">
            <span v-if="phase.start_date">
              Started: {{ formatDate(phase.start_date) }}
            </span>
            <span v-if="phase.end_date" class="q-ml-md">
              Ends: {{ formatDate(phase.end_date) }}
            </span>
          </div>
        </div>
      </div>

      <!-- Legend -->
      <div class="timeline-legend q-mt-lg">
        <div class="text-subtitle2 q-mb-sm">Legend:</div>
        <div class="legend-items">
          <div class="legend-item">
            <div class="legend-color" style="background-color: #9C27B0"></div>
            <span>Pending</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background-color: #FF9800"></div>
            <span>In Progress</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background-color: #4CAF50"></div>
            <span>Completed</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background-color: #F44336"></div>
            <span>Delayed</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ConstructionPhase } from 'src/types/models'

interface Props {
  phases: ConstructionPhase[]
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false
})

const sortedPhases = computed(() =>
  [...props.phases].sort((a, b) => a.phase_order - b.phase_order)
)

const getPhaseStatusColor = (status: ConstructionPhase['status']): string => {
  const colors: Record<ConstructionPhase['status'], string> = {
    pending: 'purple',
    in_progress: 'orange',
    completed: 'green',
    delayed: 'red'
  }
  return colors[status]
}

const formatDate = (dateString: string): string => {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  })
}
</script>

<style lang="sass" scoped>
.timeline-gantt
  min-height: 200px

.timeline-container
  position: relative

  &::before
    content: ''
    position: absolute
    left: 15px
    top: 0
    bottom: 0
    width: 2px
    background: #e0e0e0

.timeline-item
  position: relative
  margin-left: 40px

  &::before
    content: ''
    position: absolute
    left: -27px
    top: 20px
    width: 12px
    height: 12px
    border-radius: 50%
    background: var(--q-primary)
    border: 3px solid white
    box-shadow: 0 0 0 2px var(--q-primary)

.timeline-header
  display: flex
  align-items: center
  flex-wrap: wrap

.timeline-title
  font-weight: 600
  font-size: 1.1em

.timeline-description
  line-height: 1.4

.timeline-progress
  .progress-label
    display: flex
    justify-content: space-between
    align-items: center
    font-size: 0.875em

.timeline-dates
  display: flex
  flex-wrap: wrap

.timeline-legend
  border-top: 1px solid #e0e0e0
  padding-top: 16px

.legend-items
  display: flex
  flex-wrap: wrap
  gap: 16px

.legend-item
  display: flex
  align-items: center
  gap: 8px

.legend-color
  width: 16px
  height: 16px
  border-radius: 2px

@media (max-width: 600px)
  .timeline-item
    margin-left: 30px

  .timeline-progress .progress-label
    flex-direction: column
    align-items: flex-start
    gap: 4px

  .timeline-dates
    flex-direction: column
    gap: 4px
</style>

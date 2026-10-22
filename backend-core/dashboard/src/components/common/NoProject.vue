<template>
  <q-card flat class="app-card">
    <empty-state
      icon="home_work"
      :title="projects.loading ? 'Loading projects…' : 'No project selected'"
      :message="projects.loading
        ? undefined
        : projects.projects.length
          ? 'Pick a project in the header to see its ' + what + '.'
          : 'Describe a house and the AI planner drafts the floor plan, phases, tasks and materials — or start a blank project.'"
    >
      <q-btn
        v-if="!projects.loading"
        unelevated
        color="primary"
        icon="add"
        label="New project"
        @click="ui.openNewProject()"
      />
    </empty-state>
  </q-card>
</template>

<script setup lang="ts">
import { useProjectsStore } from 'src/stores/projects'
import { useUiStore } from 'src/stores/ui'
import EmptyState from './EmptyState.vue'

withDefaults(defineProps<{ what?: string }>(), { what: 'details' })

const projects = useProjectsStore()
const ui = useUiStore()
</script>

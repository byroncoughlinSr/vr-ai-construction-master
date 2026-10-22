import { defineStore } from 'pinia'

/** Dialogs that more than one page can open. */
export const useUiStore = defineStore('ui', {
  state: () => ({
    newProjectOpen: false,
    newProjectClientId: null as number | null, // start the project for this CRM client
    // Bumped when the floor plan changes outside the Design Studio (copilot), so it reloads.
    floorPlanRevision: 0
  }),

  actions: {
    openNewProject(clientId: number | null = null) {
      this.newProjectClientId = clientId
      this.newProjectOpen = true
    }
  }
})

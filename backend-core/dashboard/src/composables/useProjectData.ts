import { computed, watch } from 'vue'
import { useProjectsStore } from 'src/stores/projects'

/**
 * Run `load` for the selected project now and whenever another project is
 * selected; `clear` when none is. Pages use it so their store always shows the
 * project picked in the header.
 */
export function useProjectData(load: (projectId: number) => unknown, clear?: () => void) {
  const projects = useProjectsStore()
  const projectId = computed(() => projects.currentProjectId)
  watch(
    projectId,
    id => {
      if (id) load(id)
      else clear?.()
    },
    { immediate: true }
  )
  return { projectId, project: computed(() => projects.currentProject) }
}

import { useQuasar } from 'quasar'

interface AndroidBridge {
  loadProject?: (projectId: number) => void
}

/** Whether the page is running in the headset's WebView, where
 * ImmersiveActivity exposes the `Android` bridge. */
export function inHeadset(): boolean {
  const android = (window as unknown as { Android?: AndroidBridge }).Android
  return typeof android?.loadProject === 'function'
}

/**
 * "Load to VR": hands the project to the headset through the WebView bridge
 * (`Android.loadProject`). Only the house is loaded — no picture is started —
 * so the headset can walk and take changes (grip) at once. Outside the headset
 * there is nothing to load into, so it says where to do it instead.
 */
export function useLoadToVr() {
  const $q = useQuasar()

  return (projectId: number | null | undefined, projectName = 'Project'): boolean => {
    if (!projectId) {
      $q.notify({ type: 'warning', message: 'Select a project first' })
      return false
    }
    const android = (window as unknown as { Android?: AndroidBridge }).Android
    if (typeof android?.loadProject !== 'function') {
      $q.notify({
        type: 'info',
        message: 'Open the dashboard in the headset to load a house',
        caption: 'Load to VR works from the Quest',
        timeout: 3000
      })
      return false
    }
    try {
      android.loadProject(projectId)
      $q.notify({ type: 'positive', message: `Loading "${projectName}" into VR`, caption: 'Check your Quest headset', timeout: 3000 })
      return true
    } catch (err) {
      console.error('Android.loadProject failed:', err)
      $q.notify({ type: 'negative', message: 'Failed to load the project into VR', caption: (err as Error).message })
      return false
    }
  }
}

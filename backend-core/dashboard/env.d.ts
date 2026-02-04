/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module 'virtual:svg-icons-register'
declare module 'quasar/wrappers' {
  import { Component } from 'vue'
  export interface QVueGlobals {
    loading: {
      show: (options?: any) => void
      hide: () => void
    }
    notify: (options: any) => void
    dark: {
      set: (value: boolean) => void
      isActive: boolean
    }
  }
}

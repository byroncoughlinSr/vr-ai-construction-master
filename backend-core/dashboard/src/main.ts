import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { Quasar, Dark, Dialog, Loading, Notify } from 'quasar'
import '@quasar/extras/material-icons/material-icons.css'
import 'quasar/src/css/index.sass'

import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(Quasar, {
  plugins: {
    Dark,
    Dialog,
    Loading,
    Notify
  },
  config: {
    // Follow the system's light/dark setting until the user picks one (MainLayout).
    dark: 'auto',
    notify: { position: 'top-right', timeout: 2500 },
    brand: {
      primary: '#2563EB',
      secondary: '#0D9488',
      accent: '#7C3AED',
      dark: '#131C2E',
      'dark-page': '#0B1220',
      positive: '#16A34A',
      negative: '#DC2626',
      info: '#0284C7',
      warning: '#D97706'
    }
  }
})

app.mount('#q-app')

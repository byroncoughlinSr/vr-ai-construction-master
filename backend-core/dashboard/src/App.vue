<template>
  <div id="q-app">
    <router-view />
  </div>
</template>

<script setup lang="ts">
// This is the main app component
</script>

<style lang="sass">
@import 'quasar/src/css/variables.sass'

// Surface tokens shared by every page; Quasar's own components follow
// $dark / $dark-page in quasar-variables.sass.
:root
  --app-bg: #f4f6fb
  --app-surface: #ffffff
  --app-surface-2: #f8fafc
  --app-border: #e2e8f0
  --app-muted: #64748b
  --app-text: #0f172a
  --app-accent-soft: rgba(37, 99, 235, 0.08)

body.body--dark
  --app-bg: #0b1220
  --app-surface: #131c2e
  --app-surface-2: #1a2438
  --app-border: #26324a
  --app-muted: #94a3b8
  --app-text: #e2e8f0
  --app-accent-soft: rgba(96, 165, 250, 0.12)

body
  margin: 0
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', sans-serif
  -webkit-font-smoothing: antialiased
  -moz-osx-font-smoothing: grayscale
  background: var(--app-bg)
  color: var(--app-text)

#q-app
  min-height: 100vh

// Page frame
.page-container
  max-width: 1440px
  margin: 0 auto

// Cards: flat, bordered, rounded
.app-card
  background: var(--app-surface)
  border: 1px solid var(--app-border)
  border-radius: 12px
  box-shadow: none

.app-card-header
  display: flex
  align-items: center
  justify-content: space-between
  gap: 8px
  padding: 14px 16px 6px

.app-card-title
  font-size: 0.95rem
  font-weight: 600
  letter-spacing: 0.01em

.text-muted
  color: var(--app-muted) !important

.bg-surface-2
  background: var(--app-surface-2)

.border-app
  border: 1px solid var(--app-border)

.rounded-12
  border-radius: 12px

.tabular
  font-variant-numeric: tabular-nums

.clickable-row
  cursor: pointer
  transition: background 0.15s ease
  &:hover
    background: var(--app-accent-soft)

// Banners that work on light and dark pages
.banner-error
  background: rgba(220, 38, 38, 0.1)
  color: var(--q-negative)

.banner-warning
  background: rgba(217, 119, 6, 0.12)
  color: #b45309

body.body--dark .banner-warning
  color: #fbbf24

body.body--dark .banner-error
  color: #f87171

.clamp-4
  display: -webkit-box
  -webkit-line-clamp: 4
  -webkit-box-orient: vertical
  overflow: hidden

.ellipsis-2
  display: -webkit-box
  -webkit-line-clamp: 2
  -webkit-box-orient: vertical
  overflow: hidden

// Quasar tables inside app cards: no second border
.app-card .q-table__card
  background: transparent
  box-shadow: none

.q-table th
  font-weight: 600
  color: var(--app-muted)
</style>

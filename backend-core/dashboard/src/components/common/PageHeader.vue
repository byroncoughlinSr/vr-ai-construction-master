<template>
  <div class="page-header row items-center q-col-gutter-sm q-mb-md">
    <div class="col-12 col-md">
      <div class="row items-center no-wrap q-gutter-x-sm">
        <q-avatar v-if="icon" :icon="icon" size="40px" font-size="22px" class="page-header-icon" />
        <div class="min-width-0">
          <div class="text-overline text-muted leading-none" v-if="eyebrow">{{ eyebrow }}</div>
          <h1 class="page-title ellipsis">{{ title }}</h1>
          <div v-if="subtitle" class="text-body2 text-muted ellipsis-2">{{ subtitle }}</div>
        </div>
      </div>
    </div>
    <div v-if="$slots.actions" class="col-12 col-md-auto">
      <div class="row items-center q-gutter-sm justify-md-end">
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; subtitle?: string; icon?: string; eyebrow?: string }>()
</script>

<style lang="sass" scoped>
.page-title
  margin: 0
  font-size: 1.45rem
  line-height: 1.25
  font-weight: 700
  letter-spacing: -0.01em

.page-header-icon
  background: var(--app-accent-soft)
  color: var(--q-primary)

.min-width-0
  min-width: 0

.leading-none
  line-height: 1.1

@media (min-width: 1024px)
  .justify-md-end
    justify-content: flex-end
</style>

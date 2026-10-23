<template>
  <div class="empty-state column items-center text-center" :class="dense ? 'q-pa-md' : 'q-pa-xl'">
    <q-icon :name="icon" :size="dense ? '32px' : '48px'" class="text-muted q-mb-sm" />
    <div class="text-subtitle1 text-weight-medium">{{ title }}</div>
    <div v-if="message" class="text-body2 text-muted q-mt-xs" style="max-width: 460px">{{ message }}</div>
    <div v-if="$slots.default" class="row q-gutter-sm justify-center q-mt-md">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ icon?: string; title: string; message?: string; dense?: boolean }>(), {
  icon: 'inbox',
  dense: false
})
</script>

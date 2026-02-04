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

body
  margin: 0
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif
  -webkit-font-smoothing: antialiased
  -moz-osx-font-smoothing: grayscale

#q-app
  min-height: 100vh
</style>

<template>
  <div class="bar-chart" :style="{ height: `${height}px` }">
    <canvas ref="canvas" role="img" :aria-label="ariaLabel" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { Chart, BarController, BarElement, CategoryScale, LinearScale, Legend, Tooltip } from 'chart.js'
import { formatCompactCurrency, formatCurrency } from 'src/utils/format'

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Legend, Tooltip)

// Categorical slots 1-3 (blue, orange, aqua), stepped per mode; validated as a
// set against both surfaces (dataviz palette). Series take them in order, never cycled.
const SERIES = {
  light: ['#2a78d6', '#eb6834', '#1baf7a'],
  dark: ['#3987e5', '#d95926', '#199e70']
}
const INK = {
  light: { text: '#52514e', grid: 'rgba(15, 23, 42, 0.07)' },
  dark: { text: '#c3c2b7', grid: 'rgba(226, 232, 240, 0.08)' }
}

const props = withDefaults(defineProps<{
  labels: string[]
  series: Array<{ label: string; data: number[] }>
  horizontal?: boolean
  height?: number
  ariaLabel?: string
}>(), {
  horizontal: true,
  height: 260,
  ariaLabel: 'Bar chart'
})

const $q = useQuasar()
const canvas = ref<HTMLCanvasElement | null>(null)
let chart: Chart<'bar'> | null = null

const mode = computed(() => ($q.dark.isActive ? 'dark' : 'light'))

const build = () => {
  if (!canvas.value) return
  chart?.destroy()
  const ink = INK[mode.value]
  const colors = SERIES[mode.value]
  const valueAxis = {
    beginAtZero: true,
    grid: { color: ink.grid },
    border: { display: false },
    ticks: { color: ink.text, callback: (v: string | number) => formatCompactCurrency(Number(v)), maxTicksLimit: 6 }
  }
  const categoryAxis = {
    grid: { display: false },
    border: { display: false },
    ticks: {
      color: ink.text,
      callback(this: { getLabelForValue: (v: number) => string }, v: string | number) {
        const label = this.getLabelForValue(Number(v))
        return label.length > 24 ? `${label.slice(0, 23)}…` : label
      }
    }
  }
  chart = new Chart(canvas.value, {
    type: 'bar',
    data: {
      labels: props.labels,
      datasets: props.series.slice(0, 3).map((s, i) => ({
        label: s.label,
        data: s.data,
        backgroundColor: colors[i],
        hoverBackgroundColor: colors[i],
        borderRadius: 4,
        borderSkipped: 'start',
        maxBarThickness: 18,
        categoryPercentage: 0.72,
        // < 1 leaves a sliver of surface between a group's bars
        barPercentage: 0.86
      }))
    },
    options: {
      indexAxis: props.horizontal ? 'y' : 'x',
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      interaction: { mode: 'index', intersect: false, axis: props.horizontal ? 'y' : 'x' },
      scales: props.horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis },
      plugins: {
        // One series: the card title names it, no legend box.
        legend: {
          display: props.series.length > 1,
          position: 'top',
          align: 'start',
          labels: { color: ink.text, boxWidth: 10, boxHeight: 10, useBorderRadius: true, borderRadius: 2 }
        },
        tooltip: {
          callbacks: { label: ctx => ` ${ctx.dataset.label}: ${formatCurrency(Number(ctx.raw))}` }
        }
      }
    }
  })
}

onMounted(build)
watch(() => [props.labels, props.series, mode.value], build, { deep: true })
onBeforeUnmount(() => chart?.destroy())
</script>

<style scoped>
.bar-chart {
  position: relative;
  width: 100%;
}
</style>

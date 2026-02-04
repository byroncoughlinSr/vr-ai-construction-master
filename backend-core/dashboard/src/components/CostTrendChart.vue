<template>
  <div class="cost-trend-chart">
    <div v-if="loading" class="flex flex-center q-pa-md">
      <q-spinner size="32px" color="primary" />
    </div>
    <div v-else-if="!expenses || expenses.length === 0" class="text-center text-grey-6 q-pa-md">
      <q-icon name="trending_up" size="48px" />
      <div class="q-mt-sm">No expense data available</div>
    </div>
    <div v-else>
      <canvas ref="chartCanvas"></canvas>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { Chart, registerables } from 'chart.js'

// Register Chart.js components
Chart.register(...registerables)

interface ExpenseData {
  date: string
  value: number
  category?: string
}

interface Props {
  expenses: ExpenseData[]
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false
})

const chartCanvas = ref<HTMLCanvasElement>()
let chart: Chart | null = null

const createChart = async () => {
  if (!chartCanvas.value || !props.expenses.length) return

  await nextTick()

  const ctx = chartCanvas.value.getContext('2d')
  if (!ctx) return

  // Destroy existing chart
  if (chart) {
    chart.destroy()
  }

  // Group expenses by category if categories exist
  const hasCategories = props.expenses.some(exp => exp.category)
  const categories = hasCategories
    ? [...new Set(props.expenses.map(exp => exp.category).filter(Boolean))]
    : ['Expenses']

  const datasets = hasCategories
    ? categories.map((category, index) => {
        const categoryExpenses = props.expenses.filter(exp => exp.category === category)
        return {
          label: category,
          data: categoryExpenses.map(exp => ({
            x: new Date(exp.date).getTime(),
            y: exp.value
          })),
          borderColor: `hsl(${(index * 137.5) % 360}, 70%, 50%)`,
          backgroundColor: `hsla(${(index * 137.5) % 360}, 70%, 50%, 0.1)`,
          tension: 0.4,
          fill: false
        }
      })
    : [{
        label: 'Expenses',
        data: props.expenses.map(exp => ({
          x: new Date(exp.date).getTime(),
          y: exp.value
        })),
        borderColor: '#1976D2',
        backgroundColor: 'rgba(25, 118, 210, 0.1)',
        tension: 0.4,
        fill: false
      }]

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          display: hasCategories,
          position: 'top'
        },
        tooltip: {
          callbacks: {
            title: (context) => {
              const xValue = context[0]?.parsed?.x
              return xValue ? new Date(xValue).toLocaleDateString() : ''
            },
            label: (context) => {
              const yValue = context.parsed?.y
              return `${context.dataset.label}: $${yValue ? yValue.toLocaleString() : '0'}`
            }
          }
        }
      },
      scales: {
        x: {
          type: 'time',
          time: {
            unit: 'day',
            displayFormats: {
              day: 'MMM dd'
            }
          },
          title: {
            display: true,
            text: 'Date'
          }
        },
        y: {
          title: {
            display: true,
            text: 'Amount ($)'
          },
          ticks: {
            callback: (value) => `$${Number(value).toLocaleString()}`
          }
        }
      }
    }
  })
}

const updateChart = () => {
  if (chart && props.expenses.length) {
    // Recreate chart for simplicity - could be optimized
    createChart()
  } else {
    createChart()
  }
}

watch(() => props.expenses, updateChart, { deep: true })
watch(() => props.loading, (newLoading) => {
  if (!newLoading && props.expenses.length) {
    createChart()
  }
})

onMounted(() => {
  if (!props.loading && props.expenses.length) {
    createChart()
  }
})
</script>

<style lang="sass" scoped>
.cost-trend-chart
  height: 300px
  width: 100%
</style>

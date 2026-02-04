<template>
  <div class="budget-pie-chart">
    <div v-if="loading" class="flex flex-center q-pa-md">
      <q-spinner size="32px" color="primary" />
    </div>
    <div v-else-if="!budgetData || budgetData.length === 0" class="text-center text-grey-6 q-pa-md">
      <q-icon name="pie_chart" size="48px" />
      <div class="q-mt-sm">No budget data available</div>
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

interface BudgetData {
  category: string
  budgeted_amount: number
  color?: string
}

interface Props {
  budgetData: BudgetData[]
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false
})

const chartCanvas = ref<HTMLCanvasElement>()
let chart: Chart | null = null

const createChart = async () => {
  if (!chartCanvas.value || !props.budgetData.length) return

  await nextTick()

  const ctx = chartCanvas.value.getContext('2d')
  if (!ctx) return

  // Destroy existing chart
  if (chart) {
    chart.destroy()
  }

  const labels = props.budgetData.map(item => item.category)
  const data = props.budgetData.map(item => item.budgeted_amount)
  const colors = props.budgetData.map((item, index) =>
    item.color || `hsl(${(index * 137.5) % 360}, 70%, 50%)`
  )

  chart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: colors,
        borderWidth: 2,
        borderColor: '#ffffff'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            padding: 20,
            usePointStyle: true
          }
        },
        tooltip: {
          callbacks: {
            label: (context) => {
              const value = context.parsed
              return `${context.label}: $${value.toLocaleString()}`
            }
          }
        }
      }
    }
  })
}

const updateChart = () => {
  if (chart && props.budgetData.length) {
    chart.data.labels = props.budgetData.map(item => item.category)
    chart.data.datasets[0].data = props.budgetData.map(item => item.budgeted_amount)
    chart.data.datasets[0].backgroundColor = props.budgetData.map((item, index) =>
      item.color || `hsl(${(index * 137.5) % 360}, 70%, 50%)`
    )
    chart.update()
  } else {
    createChart()
  }
}

watch(() => props.budgetData, updateChart, { deep: true })
watch(() => props.loading, (newLoading) => {
  if (!newLoading && props.budgetData.length) {
    createChart()
  }
})

onMounted(() => {
  if (!props.loading && props.budgetData.length) {
    createChart()
  }
})
</script>

<style lang="sass" scoped>
.budget-pie-chart
  height: 300px
  width: 100%
</style>

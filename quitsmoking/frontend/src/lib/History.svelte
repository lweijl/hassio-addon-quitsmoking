<script>
  import { onMount, onDestroy } from 'svelte'
  import { getHistory } from './api.js'
  import { Chart, BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend, LineController, LineElement, PointElement } from 'chart.js'

  Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend, LineController, LineElement, PointElement)

  let canvasEl = $state(null)
  let chart = null
  let historyData = $state(null)
  let range = $state(7)
  let loading = $state(true)
  let error = $state(null)

  onMount(async () => {
    await fetchHistory()
  })

  onDestroy(() => {
    if (chart) chart.destroy()
  })

  async function fetchHistory() {
    loading = true
    error = null
    try {
      historyData = await getHistory()
      renderChart()
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  function setRange(r) {
    range = r
    renderChart()
  }

  function renderChart() {
    if (!historyData || !canvasEl) return

    const days = historyData.days || []
    const sliced = range === 0 ? days : days.slice(-range)

    const labels = sliced.map(d => {
      const date = new Date(d.date)
      return date.toLocaleDateString('en', { weekday: 'short', day: 'numeric' })
    })

    const regularData = sliced.map(d => (d.count ?? 0) - (d.bonus_count ?? 0))
    const bonusData = sliced.map(d => d.bonus_count ?? 0)
    const allowanceData = sliced.map(d => d.allowance ?? 0)

    if (chart) chart.destroy()

    chart = new Chart(canvasEl, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Regular',
            data: regularData,
            backgroundColor: 'rgba(100, 210, 255, 0.7)',
            borderColor: 'rgba(100, 210, 255, 1)',
            borderWidth: 1,
            borderRadius: 4,
            order: 2
          },
          {
            label: 'Bonus',
            data: bonusData,
            backgroundColor: 'rgba(175, 82, 222, 0.7)',
            borderColor: 'rgba(175, 82, 222, 1)',
            borderWidth: 1,
            borderRadius: 4,
            order: 3
          },
          {
            label: 'Allowance',
            type: 'line',
            data: allowanceData,
            borderColor: 'rgba(255, 149, 0, 0.8)',
            borderWidth: 2,
            borderDash: [5, 5],
            pointRadius: 0,
            fill: false,
            order: 1
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          intersect: false,
          mode: 'index'
        },
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: '#8E8E93',
              padding: 16,
              usePointStyle: true,
              pointStyle: 'circle'
            }
          },
          tooltip: {
            backgroundColor: '#2C2C2E',
            titleColor: '#FFFFFF',
            bodyColor: '#8E8E93',
            borderColor: '#3A3A3C',
            borderWidth: 1,
            cornerRadius: 8,
            padding: 12
          }
        },
        scales: {
          x: {
            stacked: true,
            grid: { display: false },
            ticks: { color: '#8E8E93', font: { size: 11 } }
          },
          y: {
            stacked: true,
            beginAtZero: true,
            grid: { color: 'rgba(142, 142, 147, 0.1)' },
            ticks: {
              color: '#8E8E93',
              stepSize: 1,
              font: { size: 11 }
            }
          }
        }
      }
    })
  }

  // Re-render when canvasEl becomes available
  $effect(() => {
    if (canvasEl && historyData) {
      renderChart()
    }
  })
</script>

<div class="history fade-in">
  <div class="card">
    <div class="history-header">
      <h2 class="section-title">Daily Cigarettes</h2>
      <div class="range-selector">
        <button
          class="range-btn"
          class:active={range === 7}
          onclick={() => setRange(7)}
          aria-label="Show 7 days"
        >7d</button>
        <button
          class="range-btn"
          class:active={range === 14}
          onclick={() => setRange(14)}
          aria-label="Show 14 days"
        >14d</button>
        <button
          class="range-btn"
          class:active={range === 0}
          onclick={() => setRange(0)}
          aria-label="Show all days"
        >All</button>
      </div>
    </div>

    {#if loading}
      <div class="chart-placeholder">
        <p>Loading chart...</p>
      </div>
    {:else if error}
      <div class="chart-placeholder">
        <p style="color: var(--color-danger)">⚠️ {error}</p>
        <button class="btn btn-secondary" onclick={fetchHistory}>Retry</button>
      </div>
    {:else}
      <div class="chart-container">
        <canvas bind:this={canvasEl}></canvas>
      </div>
    {/if}
  </div>
</div>

<style>
  .history {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .history-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 12px;
  }

  .section-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--color-text);
  }

  .chart-container {
    position: relative;
    height: 250px;
    width: 100%;
  }

  @media (min-width: 768px) {
    .chart-container {
      height: 300px;
    }
  }

  .chart-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    height: 200px;
    color: var(--color-secondary-text);
  }
</style>

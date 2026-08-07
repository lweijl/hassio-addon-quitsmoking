<script>
  import { onMount, onDestroy } from 'svelte'
  import { getProgress } from './api.js'
  import { getChartColors } from './chartColors.js'
  import { Chart, LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler } from 'chart.js'

  Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

  let loading = $state(true)
  let error = $state(null)
  let progressData = $state(null)

  let avoidedCanvasEl = $state(null)
  let savingsCanvasEl = $state(null)
  let avoidedChart = null
  let savingsChart = null
  let themeHandler = null
  let mql = null

  onMount(async () => {
    await fetchProgress()

    // Re-render charts on theme changes
    themeHandler = () => renderCharts()
    window.addEventListener('themechange', themeHandler)
    mql = window.matchMedia('(prefers-color-scheme: light)')
    mql.addEventListener('change', themeHandler)
  })

  onDestroy(() => {
    if (avoidedChart) avoidedChart.destroy()
    if (savingsChart) savingsChart.destroy()
    if (themeHandler) {
      window.removeEventListener('themechange', themeHandler)
    }
    if (mql && themeHandler) {
      mql.removeEventListener('change', themeHandler)
    }
  })

  async function fetchProgress() {
    loading = true
    error = null
    try {
      progressData = await getProgress()
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  function renderCharts() {
    if (!progressData) return
    renderAvoidedChart()
    renderSavingsChart()
  }

  function renderAvoidedChart() {
    if (!avoidedCanvasEl || !progressData.cumulative_avoided) return
    if (avoidedChart) avoidedChart.destroy()

    const colors = getChartColors()
    const data = progressData.cumulative_avoided
    const labels = data.map(d => {
      const date = new Date(d.date)
      return date.toLocaleDateString('en', { month: 'short', day: 'numeric' })
    })

    avoidedChart = new Chart(avoidedCanvasEl, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Cigarettes Avoided',
          data: data.map(d => d.avoided_cumulative),
          borderColor: colors.avoided,
          backgroundColor: colors.avoidedBg,
          borderWidth: 2,
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHitRadius: 10
        }]
      },
      options: chartOptions(colors, 'Cumulative Cigarettes Avoided')
    })
  }

  function renderSavingsChart() {
    if (!savingsCanvasEl || !progressData.cumulative_saved) return
    if (savingsChart) savingsChart.destroy()

    const colors = getChartColors()
    const data = progressData.cumulative_saved
    const labels = data.map(d => {
      const date = new Date(d.date)
      return date.toLocaleDateString('en', { month: 'short', day: 'numeric' })
    })

    savingsChart = new Chart(savingsCanvasEl, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Money Saved (€)',
          data: data.map(d => d.saved_cumulative),
          borderColor: colors.saved,
          backgroundColor: colors.savedBg,
          borderWidth: 2,
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHitRadius: 10
        }]
      },
      options: chartOptions(colors, 'Money Saved (€)')
    })
  }

  function chartOptions(colors, title) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        intersect: false,
        mode: 'index'
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: colors.tooltipBg,
          titleColor: colors.tooltipTitle,
          bodyColor: colors.tooltipBody,
          borderColor: colors.tooltipBorder,
          borderWidth: 1,
          cornerRadius: 8,
          padding: 12
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: colors.ticks, font: { size: 11 }, maxTicksLimit: 8 }
        },
        y: {
          beginAtZero: true,
          grid: { color: colors.grid },
          ticks: { color: colors.ticks, font: { size: 11 } }
        }
      }
    }
  }

  // Re-render when canvas elements become available
  $effect(() => {
    if (avoidedCanvasEl && progressData) {
      renderAvoidedChart()
    }
  })

  $effect(() => {
    if (savingsCanvasEl && progressData) {
      renderSavingsChart()
    }
  })
</script>

<div class="progress fade-in">
  {#if loading}
    <div class="card" style="text-align: center; padding: 32px;">
      <p style="color: var(--color-secondary-text)">Loading progress...</p>
    </div>
  {:else if error}
    <div class="card" style="text-align: center; padding: 32px;">
      <p style="color: var(--color-danger)">⚠️ {error}</p>
      <button class="btn btn-secondary" onclick={fetchProgress} style="margin-top: 12px;" aria-label="Retry loading progress">Retry</button>
    </div>
  {:else if progressData}
    <!-- Cigarettes Avoided Chart -->
    <div class="card">
      <h2 class="section-title">🚭 Cigarettes Avoided</h2>
      <div class="chart-container">
        <canvas bind:this={avoidedCanvasEl} aria-label="Cumulative cigarettes avoided chart"></canvas>
      </div>
    </div>

    <!-- Money Saved Chart -->
    <div class="card">
      <h2 class="section-title">💰 Money Saved</h2>
      <div class="chart-container">
        <canvas bind:this={savingsCanvasEl} aria-label="Cumulative money saved chart"></canvas>
      </div>
    </div>

    <!-- Projection -->
    {#if progressData.projections}
      <div class="card projection-card">
        <h2 class="section-title">📈 Projection</h2>
        <p class="projection-text">
          At this rate, you'll have saved <strong class="accent">€{progressData.projections.projected_total_saved?.toFixed(2) ?? '—'}</strong> by your quit date
          and avoided <strong class="accent">{progressData.projections.projected_total_avoided ?? '—'}</strong> cigarettes.
        </p>
      </div>
    {/if}

    <!-- Milestones -->
    {#if progressData.milestones && progressData.milestones.length > 0}
      <div class="card">
        <h2 class="section-title">🏆 Milestones</h2>
        <div class="milestones-list">
          {#each progressData.milestones as milestone}
            <div class="milestone-item" class:reached={milestone.reached}>
              <span class="milestone-icon">{milestone.reached ? '✅' : '⬜'}</span>
              <span class="milestone-text">{milestone.name}</span>
              {#if milestone.reached && milestone.date}
                <span class="milestone-date">{new Date(milestone.date).toLocaleDateString('en', { month: 'short', day: 'numeric' })}</span>
              {/if}
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Fun Equivalents -->
    {#if progressData.fun_equivalents && progressData.fun_equivalents.length > 0}
      <div class="card">
        <h2 class="section-title">🎉 What You've Saved</h2>
        <div class="equivalents-list">
          {#each progressData.fun_equivalents as equiv}
            <div class="equivalent-item">
              <span class="equivalent-text">{equiv.equivalent}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Weekly Comparison -->
    {#if progressData.weekly_comparison && progressData.weekly_comparison.length > 0}
      <div class="card">
        <h2 class="section-title">📊 Weekly Comparison</h2>
        <div class="table-wrapper">
          <table class="schedule-table">
            <thead>
              <tr>
                <th>Week</th>
                <th>Smoked</th>
                <th>Allowance</th>
                <th>Saved</th>
              </tr>
            </thead>
            <tbody>
              {#each progressData.weekly_comparison as week}
                <tr>
                  <td>Week {week.week}</td>
                  <td class:over-limit={week.smoked > week.allowance}>{week.smoked}</td>
                  <td>{week.allowance}</td>
                  <td class="savings-cell">€{week.saved_vs_baseline?.toFixed(2) ?? '0.00'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}
  {/if}
</div>

<style>
  .progress {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .section-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: 16px;
  }

  .chart-container {
    position: relative;
    height: 220px;
    width: 100%;
  }

  @media (min-width: 768px) {
    .chart-container {
      height: 260px;
    }
  }

  .projection-card {
    border-left: 3px solid var(--color-accent);
  }

  .projection-text {
    font-size: 14px;
    color: var(--color-secondary-text);
    line-height: 1.6;
  }

  .accent {
    color: var(--color-accent);
    font-weight: 700;
  }

  .milestones-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .milestone-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--radius-sm);
    background: var(--color-surface-elevated);
    transition: opacity var(--transition);
  }

  .milestone-item:not(.reached) {
    opacity: 0.5;
  }

  .milestone-icon {
    font-size: 16px;
    flex-shrink: 0;
  }

  .milestone-text {
    flex: 1;
    font-size: 14px;
    color: var(--color-text);
  }

  .milestone-date {
    font-size: 12px;
    color: var(--color-secondary-text);
  }

  .equivalents-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .equivalent-item {
    padding: 10px 14px;
    background: var(--color-surface-elevated);
    border-radius: var(--radius-sm);
    font-size: 14px;
    color: var(--color-text);
  }

  .table-wrapper {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .over-limit {
    color: var(--color-danger);
    font-weight: 600;
  }

  .savings-cell {
    color: var(--color-success);
    font-weight: 500;
  }
</style>

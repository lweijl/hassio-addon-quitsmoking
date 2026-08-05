<script>
  import { onMount } from 'svelte'
  import { getWeeklyReport } from './api.js'

  let report = $state(null)
  let loading = $state(true)
  let error = $state(null)

  onMount(async () => {
    try {
      report = await getWeeklyReport()
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  })

  const gradeColors = {
    'A': 'var(--color-success)',
    'B': 'var(--color-accent)',
    'C': 'var(--color-warning)',
    'D': 'var(--color-danger)',
  }
</script>

{#if loading}
  <div class="card" style="text-align: center; padding: 32px;">
    <p style="color: var(--color-secondary-text)">Loading report...</p>
  </div>
{:else if error}
  <div class="card" style="text-align: center; padding: 32px;">
    <p style="color: var(--color-danger)">⚠️ {error}</p>
  </div>
{:else if report}
  <div class="report fade-in">
    <!-- Grade & Summary -->
    <div class="card grade-card">
      <div class="grade-circle" style="border-color: {gradeColors[report.grade] || 'var(--color-secondary-text)'}; color: {gradeColors[report.grade] || 'var(--color-secondary-text)'}">
        {report.grade}
      </div>
      <div class="grade-info">
        <p class="grade-title">Week {report.week_index} Report</p>
        <p class="grade-subtitle">
          {report.totals.smoked} smoked / {report.totals.allowance} allowed
          {#if report.totals.under_budget > 0}
            <span class="under-budget">({report.totals.under_budget} under budget ✨)</span>
          {/if}
        </p>
      </div>
    </div>

    <!-- Achievements -->
    {#if report.achievements.length > 0}
      <div class="card">
        <h3 class="section-title">🏆 Achievements</h3>
        {#each report.achievements as achievement}
          <p class="achievement-item">{achievement}</p>
        {/each}
      </div>
    {/if}

    <!-- Key Stats -->
    <div class="stats-row">
      <div class="card stat-mini">
        <div class="stat-mini-value">{report.avg_per_day}</div>
        <div class="stat-mini-label">Avg/day</div>
      </div>
      <div class="card stat-mini">
        <div class="stat-mini-value">{report.longest_gap_hours}h</div>
        <div class="stat-mini-label">Longest gap</div>
      </div>
      <div class="card stat-mini">
        <div class="stat-mini-value">{report.best_day || '—'}</div>
        <div class="stat-mini-label">Best day</div>
      </div>
    </div>

    <!-- Daily Breakdown -->
    <div class="card">
      <h3 class="section-title">📅 Daily Breakdown</h3>
      <div class="daily-table">
        {#each report.daily_breakdown as day}
          <div class="daily-row">
            <span class="daily-day">{day.day_name}</span>
            <div class="daily-bar-wrapper">
              <div
                class="daily-bar"
                style="width: {day.allowance > 0 ? Math.min(100, (day.smoked / day.allowance) * 100) : 0}%"
                class:over={day.smoked > day.allowance}
                class:under={day.smoked < day.allowance}
                class:exact={day.smoked === day.allowance}
              ></div>
            </div>
            <span class="daily-count">{day.smoked}/{day.allowance}</span>
            {#if day.bonus > 0}
              <span class="daily-bonus">+{day.bonus}🎁</span>
            {/if}
            {#if day.under_budget > 0}
              <span class="daily-saved">-{day.under_budget}</span>
            {/if}
          </div>
        {/each}
      </div>
    </div>

    <!-- Comparison to last week -->
    {#if report.comparison}
      <div class="card">
        <h3 class="section-title">📈 vs Last Week</h3>
        <div class="comparison">
          <div class="comparison-row">
            <span>This week</span>
            <span class="comparison-value">{report.comparison.this_week_avg}/day</span>
          </div>
          <div class="comparison-row">
            <span>Last week</span>
            <span class="comparison-value">{report.comparison.prev_week_avg}/day</span>
          </div>
          <div class="comparison-row trend">
            <span>Trend</span>
            <span class="comparison-value" class:improving={report.comparison.trend === 'improving'} class:higher={report.comparison.trend === 'higher'}>
              {#if report.comparison.trend === 'improving'}
                📉 Improving
              {:else if report.comparison.trend === 'higher'}
                📈 Higher
              {:else}
                ➡️ Same
              {/if}
            </span>
          </div>
        </div>
      </div>
    {/if}
  </div>
{/if}

<style>
  .report {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .grade-card {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px;
  }

  .grade-circle {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    border: 3px solid;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.8rem;
    font-weight: 800;
    flex-shrink: 0;
  }

  .grade-info {
    flex: 1;
  }

  .grade-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--color-text);
  }

  .grade-subtitle {
    font-size: 13px;
    color: var(--color-secondary-text);
    margin-top: 4px;
  }

  .under-budget {
    color: var(--color-success);
    font-weight: 500;
  }

  .section-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: 12px;
  }

  .achievement-item {
    font-size: 14px;
    color: var(--color-text);
    padding: 8px 0;
    border-bottom: 1px solid var(--color-surface-elevated);
    line-height: 1.4;
  }

  .achievement-item:last-child {
    border-bottom: none;
  }

  .stats-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }

  .stat-mini {
    text-align: center;
    padding: 14px 8px;
  }

  .stat-mini-value {
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--color-accent);
  }

  .stat-mini-label {
    font-size: 11px;
    color: var(--color-secondary-text);
    margin-top: 4px;
  }

  .daily-table {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .daily-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .daily-day {
    width: 36px;
    font-size: 13px;
    font-weight: 500;
    color: var(--color-text);
  }

  .daily-bar-wrapper {
    flex: 1;
    height: 8px;
    background: var(--color-surface-elevated);
    border-radius: 4px;
    overflow: hidden;
  }

  .daily-bar {
    height: 100%;
    border-radius: 4px;
    transition: width var(--transition);
  }

  .daily-bar.under {
    background: var(--color-success);
  }

  .daily-bar.exact {
    background: var(--color-accent);
  }

  .daily-bar.over {
    background: var(--color-danger);
  }

  .daily-count {
    font-size: 12px;
    color: var(--color-secondary-text);
    min-width: 32px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .daily-bonus {
    font-size: 11px;
    color: var(--color-warning);
  }

  .daily-saved {
    font-size: 11px;
    color: var(--color-success);
    font-weight: 600;
  }

  .comparison {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .comparison-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 14px;
    color: var(--color-secondary-text);
  }

  .comparison-row.trend {
    padding-top: 8px;
    border-top: 1px solid var(--color-surface-elevated);
  }

  .comparison-value {
    font-weight: 600;
    color: var(--color-text);
  }

  .comparison-value.improving {
    color: var(--color-success);
  }

  .comparison-value.higher {
    color: var(--color-warning);
  }
</style>

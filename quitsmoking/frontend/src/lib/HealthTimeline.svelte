<script>
  import { onMount, onDestroy } from 'svelte'
  import { getHealthTimeline } from './api.js'

  let data = $state(null)
  let loading = $state(true)
  let error = $state(null)
  let refreshInterval = null

  async function fetchData() {
    try {
      data = await getHealthTimeline()
      error = null
    } catch (e) {
      error = e.message
    }
  }

  onMount(async () => {
    await fetchData()
    loading = false
    refreshInterval = setInterval(fetchData, 60000)
  })

  onDestroy(() => {
    if (refreshInterval) {
      clearInterval(refreshInterval)
    }
  })

  function formatDuration(minutes) {
    if (minutes < 60) return `${Math.round(minutes)} min`
    if (minutes < 1440) return `${Math.round(minutes / 60)} hours`
    if (minutes < 10080) return `${Math.round(minutes / 1440)} days`
    if (minutes < 43800) return `${Math.round(minutes / 10080)} weeks`
    if (minutes < 525600) return `${Math.round(minutes / 43800)} months`
    return `${Math.round(minutes / 525600)} years`
  }

  function formatTimeUntil(targetTime) {
    const now = Date.now()
    const target = new Date(targetTime).getTime()
    const diff = target - now
    if (diff <= 0) return 'Now!'
    const hours = Math.floor(diff / 3600000)
    const minutes = Math.floor((diff % 3600000) / 60000)
    if (hours > 24) {
      const days = Math.floor(hours / 24)
      return `${days}d ${hours % 24}h`
    }
    return `${hours}h ${minutes}m`
  }
</script>

{#if loading}
  <div class="card" style="text-align: center; padding: 32px;">
    <p style="color: var(--color-secondary-text)">Loading health timeline...</p>
  </div>
{:else if error}
  <div class="card" style="text-align: center; padding: 32px;">
    <p style="color: var(--color-danger)">⚠️ {error}</p>
  </div>
{:else if data}
  <div class="timeline-page fade-in">
    <!-- Time since last smoke -->
    <div class="card hero-card">
      <p class="hero-label">Time since last cigarette</p>
      <p class="hero-value">{data.hours_since_last < 1 ? `${data.minutes_since_last.toFixed(0)} min` : `${data.hours_since_last.toFixed(1)} hours`}</p>
    </div>

    <!-- Milestones -->
    <div class="milestones">
      {#each data.milestones as milestone, i}
        <div class="milestone-item" class:reached={milestone.reached} class:next={!milestone.reached && (i === 0 || data.milestones[i-1].reached)}>
          <div class="milestone-track">
            <div class="milestone-dot" class:reached={milestone.reached}>
              {#if milestone.reached}
                ✓
              {:else}
                <div class="progress-ring">
                  <svg viewBox="0 0 36 36">
                    <path
                      class="ring-bg"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                    <path
                      class="ring-fill"
                      stroke-dasharray="{milestone.progress * 100}, 100"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                  </svg>
                </div>
              {/if}
            </div>
            {#if i < data.milestones.length - 1}
              <div class="milestone-line" class:reached={milestone.reached}></div>
            {/if}
          </div>
          <div class="milestone-content">
            <div class="milestone-header">
              <span class="milestone-icon">{milestone.icon}</span>
              <span class="milestone-title">{milestone.title}</span>
              <span class="milestone-time">{formatDuration(milestone.minutes_required)}</span>
            </div>
            <p class="milestone-desc">{milestone.description}</p>
            {#if !milestone.reached && milestone.target_time}
              <p class="milestone-eta">⏳ {formatTimeUntil(milestone.target_time)} remaining</p>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </div>
{/if}

<style>
  .timeline-page {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .hero-card {
    text-align: center;
    padding: 24px 16px;
    background: linear-gradient(135deg, rgba(52, 199, 89, 0.1), rgba(100, 210, 255, 0.1));
  }

  .hero-label {
    font-size: 13px;
    color: var(--color-secondary-text);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }

  .hero-value {
    font-size: 2.5rem;
    font-weight: 700;
    color: var(--color-success);
  }

  .milestones {
    display: flex;
    flex-direction: column;
  }

  .milestone-item {
    display: flex;
    gap: 12px;
    opacity: 0.5;
    transition: opacity var(--transition);
  }

  .milestone-item.reached {
    opacity: 1;
  }

  .milestone-item.next {
    opacity: 1;
  }

  .milestone-track {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 36px;
    flex-shrink: 0;
  }

  .milestone-dot {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    background: var(--color-surface-elevated);
    color: var(--color-secondary-text);
    border: 2px solid var(--color-surface-elevated);
    position: relative;
  }

  .milestone-dot.reached {
    background: var(--color-success);
    border-color: var(--color-success);
    color: white;
  }

  .milestone-line {
    flex: 1;
    width: 2px;
    min-height: 20px;
    background: var(--color-surface-elevated);
    margin: 4px 0;
  }

  .milestone-line.reached {
    background: var(--color-success);
  }

  .milestone-content {
    flex: 1;
    padding-bottom: 20px;
  }

  .milestone-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }

  .milestone-icon {
    font-size: 16px;
  }

  .milestone-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text);
    flex: 1;
  }

  .milestone-time {
    font-size: 12px;
    color: var(--color-secondary-text);
    background: var(--color-surface-elevated);
    padding: 2px 8px;
    border-radius: 10px;
  }

  .milestone-desc {
    font-size: 13px;
    color: var(--color-secondary-text);
    line-height: 1.4;
  }

  .milestone-eta {
    font-size: 12px;
    color: var(--color-accent);
    margin-top: 4px;
    font-weight: 500;
  }

  .progress-ring {
    width: 24px;
    height: 24px;
  }

  .progress-ring svg {
    width: 100%;
    height: 100%;
    transform: rotate(-90deg);
  }

  .ring-bg {
    fill: none;
    stroke: var(--color-surface-elevated);
    stroke-width: 3;
  }

  .ring-fill {
    fill: none;
    stroke: var(--color-accent);
    stroke-width: 3;
    stroke-linecap: round;
  }
</style>

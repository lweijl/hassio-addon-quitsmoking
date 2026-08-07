<script>
  import { onMount, onDestroy } from 'svelte'
  import { logCigarette, undoLast } from './api.js'

  let { status = null, onRefresh = () => {} } = $props()

  let countdownText = $state('--:--:--')
  let progressPercent = $state(0)
  let canSmoke = $state(false)
  let shaking = $state(false)
  let showUndo = $state(false)
  let loading = $state(false)
  let tickInterval = null
  let showPastLog = $state(false)
  let pastDate = $state('')
  let pastTime = $state('12:00')
  let pastIsBonus = $state(false)
  let pastLogMessage = $state('')

  $effect(() => {
    if (status) {
      updateCountdown()
      if (tickInterval) clearInterval(tickInterval)
      tickInterval = setInterval(updateCountdown, 1000)
      return () => {
        if (tickInterval) clearInterval(tickInterval)
      }
    }
  })

  onDestroy(() => {
    if (tickInterval) clearInterval(tickInterval)
  })

  function updateCountdown() {
    if (!status || !status.next_allowed_time) {
      canSmoke = status?.can_smoke ?? true
      countdownText = 'Available now'
      progressPercent = 100
      return
    }

    const now = Date.now()
    const nextAllowed = new Date(status.next_allowed_time).getTime()
    const diff = nextAllowed - now

    if (diff <= 0) {
      canSmoke = true
      countdownText = 'Available now'
      progressPercent = 100
      return
    }

    canSmoke = false
    const hours = Math.floor(diff / 3600000)
    const minutes = Math.floor((diff % 3600000) / 60000)
    const seconds = Math.floor((diff % 60000) / 1000)

    countdownText = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`

    // Progress: how far through the wait we are
    if (status.interval_hours) {
      const totalMs = status.interval_hours * 3600000
      const elapsed = totalMs - diff
      progressPercent = Math.min(100, Math.max(0, (elapsed / totalMs) * 100))
    } else if (status.time_until_next_seconds) {
      // Daily mode: use the original time_until_next_seconds as total duration
      const totalMs = status.time_until_next_seconds * 1000
      const elapsed = totalMs - diff
      progressPercent = Math.min(100, Math.max(0, (elapsed / totalMs) * 100))
    } else {
      progressPercent = 0
    }
  }

  async function handleLog(isBonus = false) {
    if (loading) return
    loading = true
    try {
      const newStatus = await logCigarette(isBonus)
      // Use the response directly — avoids stale cache from GET /status
      status = newStatus
      showUndo = true
      setTimeout(() => { showUndo = false }, 10000)
      // Also trigger a background refresh for good measure
      onRefresh()
    } catch (e) {
      console.error('Failed to log:', e)
    } finally {
      loading = false
    }
  }

  async function handleUndo() {
    if (loading) return
    loading = true
    try {
      await undoLast()
      showUndo = false
      await onRefresh()
    } catch (e) {
      console.error('Failed to undo:', e)
    } finally {
      loading = false
    }
  }

  const motivationalTexts = [
    "Every cigarette you don't smoke is a victory 💪",
    "Your lungs are thanking you right now 🫁",
    "You're stronger than the craving 🔥",
    "One day at a time, one step at a time 🚶",
    "Freedom is closer than you think 🌅",
    "Your future self will thank you 🌟",
    "Breaking free, one breath at a time 🌬️"
  ]

  function initPastDate() {
    const yesterday = new Date()
    yesterday.setDate(yesterday.getDate() - 1)
    pastDate = yesterday.toISOString().split('T')[0]
    showPastLog = true
  }

  async function handlePastLog() {
    if (!pastDate || !pastTime || loading) return
    loading = true
    pastLogMessage = ''
    try {
      const timestamp = `${pastDate}T${pastTime}:00`
      await logCigarette(pastIsBonus, timestamp)
      pastLogMessage = `✓ Logged for ${pastDate} at ${pastTime}${pastIsBonus ? ' (bonus)' : ''}`
      pastIsBonus = false
      await onRefresh()
    } catch (e) {
      pastLogMessage = `⚠️ ${e.message}`
    } finally {
      loading = false
    }
  }

  function getMotivation() {
    const day = Math.floor(Date.now() / 86400000)
    return motivationalTexts[day % motivationalTexts.length]
  }
</script>

{#if !status}
  <div class="card" style="text-align: center; padding: 32px;">
    <p style="color: var(--color-secondary-text)">Loading...</p>
  </div>
{:else}
  <div class="dashboard fade-in">
    <!-- Mode Badge -->
    <div class="mode-badge">
      {#if status.mode === 'interval'}
        <span class="badge badge-interval">⏱️ Interval Mode</span>
      {:else if status.mode === 'daily'}
        <span class="badge badge-daily">📅 Daily Mode</span>
      {:else if status.mode === 'quit'}
        <span class="badge badge-quit">🎉 Quit!</span>
      {:else}
        <span class="badge">{status.mode}</span>
      {/if}
    </div>

    <!-- Countdown / Status Card -->
    <div class="card countdown-card">
      {#if status.mode === 'interval'}
        <p class="countdown-label">Next cigarette in</p>
        <p class="countdown" class:available={canSmoke}>{countdownText}</p>
        <div class="progress-bar">
          <div
            class="progress-bar-fill"
            style="width: {progressPercent}%; background: {canSmoke ? 'var(--color-success)' : 'var(--color-accent)'};"
          ></div>
        </div>
      {:else if status.mode === 'daily'}
        <p class="countdown-label">Today's allowance</p>
        <p class="daily-count">
          <span class="count-current">{status.smoked_today ?? 0}</span>
          <span class="count-sep">/</span>
          <span class="count-total">{status.daily_allowance ?? 0}</span>
        </p>
        {#if !canSmoke && (status.remaining_today ?? 0) > 0}
          <p class="next-scheduled-label">Next scheduled in</p>
          <p class="countdown">{countdownText}</p>
          <div class="progress-bar">
            <div
              class="progress-bar-fill"
              style="width: {progressPercent}%; background: var(--color-accent);"
            ></div>
          </div>
        {:else if (status.remaining_today ?? 0) === 0}
          <p class="next-scheduled-label">Done for today</p>
          <p class="countdown available">✓</p>
        {/if}
        {#if status.schedule_times && status.schedule_times.length > 0}
          <div class="dots" aria-label="Schedule times">
            {#each status.schedule_times as time, i}
              {@const timeStr = String(time[0]).padStart(2, '0') + ':' + String(time[1]).padStart(2, '0')}
              <div
                class="dot"
                class:filled={i < (status.smoked_today ?? 0)}
                title={timeStr}
              ></div>
            {/each}
          </div>
          <!-- Smoking Times Timeline -->
          <div class="timeline" aria-label="Smoking schedule timeline">
            <div class="timeline-track"></div>
            <div class="timeline-dots">
              {#each status.schedule_times as time, i}
                {@const h = time[0]}
                {@const m = time[1]}
                {@const timeStr = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0')}
                {@const now = new Date()}
                {@const timeDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m)}
                {@const isPast = timeDate < now}
                {@const isNearest = (() => {
                  const times = status.schedule_times.map(t => {
                    return new Date(now.getFullYear(), now.getMonth(), now.getDate(), t[0], t[1])
                  })
                  const futureTimes = times.filter(t => t >= now)
                  if (futureTimes.length === 0) return false
                  const nearest = futureTimes.reduce((a, b) => a < b ? a : b)
                  return timeDate.getTime() === nearest.getTime()
                })()}
                {@const isLogged = i < (status.smoked_today ?? 0)}
                <div class="timeline-point" class:past={isPast} class:nearest={isNearest} class:future={!isPast && !isNearest} class:logged={isLogged}>
                  <div class="timeline-dot" title="{timeStr}{isLogged ? ' (logged)' : ''}" aria-label="{timeStr}, {isPast ? 'past' : isNearest ? 'next' : 'upcoming'}{isLogged ? ', logged' : ''}"></div>
                  <span class="timeline-label">{timeStr}</span>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      {:else if status.mode === 'quit'}
        <p class="countdown-label">You're free!</p>
        <p class="countdown available">🎉</p>
        <p style="text-align:center; color: var(--color-success); font-weight: 600;">
          {status.days_since_start ?? 0} days smoke-free
        </p>
      {/if}
    </div>

    <!-- Action Buttons -->
    <div class="actions">
      <button
        class="btn btn-primary log-btn"
        class:shake={shaking}
        onclick={() => handleLog(false)}
        disabled={loading || status.mode === 'quit'}
        aria-label="Log a cigarette"
      >
        {#if (status.remaining_today ?? 1) === 0}
          🚬 Log (over limit)
        {:else if !canSmoke}
          🚬 Log (early)
        {:else}
          🚬 Log Cigarette
        {/if}
      </button>

      {#if (status.remaining_bonus ?? 0) > 0}
        <button
          class="btn btn-bonus"
          onclick={() => handleLog(true)}
          disabled={loading}
          aria-label="Use bonus cigarette, {status.remaining_bonus} remaining"
        >
          🎁 Use Bonus ({status.remaining_bonus})
        </button>
      {/if}

      {#if showUndo}
        <button
          class="btn btn-danger undo-btn fade-in"
          onclick={handleUndo}
          disabled={loading}
          aria-label="Undo last log"
        >
          ↩️ Undo
        </button>
      {/if}
    </div>

    <!-- Stats -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{status.cigarettes_avoided ?? 0}</div>
        <div class="stat-label">Avoided</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">€{(status.money_saved ?? 0).toFixed(2)}</div>
        <div class="stat-label">Saved</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{status.days_since_start ?? 0}</div>
        <div class="stat-label">Days</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{status.days_until_quit ?? '—'}</div>
        <div class="stat-label">Until Free</div>
      </div>
    </div>

    <!-- Log for past date -->
    {#if !showPastLog}
      <button
        class="btn btn-secondary past-log-toggle"
        onclick={initPastDate}
        aria-label="Log a cigarette for a past date"
      >
        📅 Log for a past date
      </button>
    {:else}
      <div class="card past-log-card fade-in">
        <p class="past-log-title">📅 Log for past date</p>
        <div class="past-log-form">
          <div class="past-log-row">
            <input
              type="date"
              bind:value={pastDate}
              max={new Date().toISOString().split('T')[0]}
              aria-label="Date"
            />
            <input
              type="time"
              bind:value={pastTime}
              aria-label="Time"
            />
          </div>
          <div class="past-log-row">
            <label class="past-log-bonus">
              <input type="checkbox" bind:checked={pastIsBonus} />
              🎁 Bonus
            </label>
            <button
              class="btn btn-primary past-log-submit"
              onclick={handlePastLog}
              disabled={loading || !pastDate}
              aria-label="Log cigarette for selected date"
            >
              🚬 Log
            </button>
            <button
              class="btn btn-secondary"
              onclick={() => { showPastLog = false; pastLogMessage = '' }}
              aria-label="Cancel past logging"
            >
              ✕
            </button>
          </div>
          {#if pastLogMessage}
            <p class="past-log-message">{pastLogMessage}</p>
          {/if}
        </div>
      </div>
    {/if}

    <!-- Bonus remaining -->
    {#if status.remaining_bonus != null}
      <div class="card bonus-card">
        <span class="bonus-icon">🎁</span>
        <span class="bonus-text">
          {status.remaining_bonus} bonus cigarette{status.remaining_bonus !== 1 ? 's' : ''} remaining this week
        </span>
      </div>
    {/if}

    <!-- Motivation -->
    <p class="motivation">{getMotivation()}</p>
  </div>
{/if}

<style>
  .dashboard {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .mode-badge {
    display: flex;
    justify-content: center;
  }

  .badge {
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 600;
    background: var(--color-surface-elevated);
    color: var(--color-secondary-text);
  }

  .badge-interval {
    background: rgba(100, 210, 255, 0.15);
    color: var(--color-accent);
  }

  .badge-daily {
    background: rgba(255, 149, 0, 0.15);
    color: var(--color-warning);
  }

  .badge-quit {
    background: rgba(52, 199, 89, 0.15);
    color: var(--color-success);
  }

  .countdown-card {
    text-align: center;
    padding: 24px 16px;
  }

  .countdown-label {
    font-size: 14px;
    color: var(--color-secondary-text);
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .next-scheduled-label {
    font-size: 12px;
    color: var(--color-secondary-text);
    margin-top: 12px;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .available {
    color: var(--color-success) !important;
  }

  .daily-count {
    text-align: center;
    margin-bottom: 16px;
  }

  .count-current {
    font-size: 3rem;
    font-weight: 700;
    color: var(--color-accent);
  }

  .count-sep {
    font-size: 2rem;
    color: var(--color-secondary-text);
    margin: 0 4px;
  }

  .count-total {
    font-size: 2rem;
    color: var(--color-secondary-text);
  }

  .actions {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .log-btn {
    font-size: 18px;
    padding: 16px;
  }

  .undo-btn {
    font-size: 14px;
  }

  .bonus-card {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
  }

  .bonus-icon {
    font-size: 1.2rem;
  }

  .bonus-text {
    font-size: 14px;
    color: var(--color-secondary-text);
  }

  .motivation {
    text-align: center;
    font-size: 14px;
    color: var(--color-secondary-text);
    font-style: italic;
    padding: 8px 0;
  }

  /* Smoking Times Timeline */
  .timeline {
    position: relative;
    margin-top: 20px;
    padding: 0 8px;
  }

  .timeline-track {
    position: absolute;
    top: 10px;
    left: 16px;
    right: 16px;
    height: 2px;
    background: var(--color-surface-elevated);
    border-radius: 1px;
  }

  .timeline-dots {
    display: flex;
    justify-content: space-between;
    position: relative;
  }

  .timeline-point {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
  }

  .timeline-dot {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 2px solid var(--color-surface-elevated);
    background: var(--color-surface);
    transition: all var(--transition);
    position: relative;
    z-index: 1;
  }

  .timeline-point.past .timeline-dot {
    background: var(--color-success);
    border-color: var(--color-success);
  }

  .timeline-point.logged .timeline-dot {
    background: var(--color-success);
    border-color: var(--color-success);
    box-shadow: 0 0 6px rgba(52, 199, 89, 0.4);
  }

  .timeline-point.nearest .timeline-dot {
    background: var(--color-accent);
    border-color: var(--color-accent);
    animation: pulse 2s ease-in-out infinite;
  }

  .timeline-point.future .timeline-dot {
    background: transparent;
    border-color: var(--color-secondary-text);
  }

  .timeline-label {
    font-size: 10px;
    color: var(--color-secondary-text);
    font-variant-numeric: tabular-nums;
  }

  .timeline-point.nearest .timeline-label {
    color: var(--color-accent);
    font-weight: 600;
  }

  @keyframes pulse {
    0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(100, 210, 255, 0.4); }
    50% { transform: scale(1.15); box-shadow: 0 0 10px 4px rgba(100, 210, 255, 0.2); }
  }

  /* Past log section */
  .past-log-toggle {
    font-size: 13px;
    padding: 10px;
    opacity: 0.7;
  }

  .past-log-card {
    padding: 16px;
  }

  .past-log-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: 12px;
  }

  .past-log-form {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .past-log-row {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .past-log-row input[type="date"],
  .past-log-row input[type="time"] {
    flex: 1;
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--color-surface-elevated);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: 14px;
  }

  .past-log-bonus {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--color-secondary-text);
    cursor: pointer;
  }

  .past-log-bonus input[type="checkbox"] {
    width: 16px;
    height: 16px;
  }

  .past-log-submit {
    font-size: 13px;
    padding: 8px 14px;
  }

  .past-log-message {
    font-size: 13px;
    color: var(--color-success);
    margin-top: 4px;
  }
</style>

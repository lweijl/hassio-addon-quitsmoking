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

  $effect(() => {
    if (status) {
      updateCountdown()
      if (tickInterval) clearInterval(tickInterval)
      tickInterval = setInterval(updateCountdown, 1000)
    }
  })

  onDestroy(() => {
    if (tickInterval) clearInterval(tickInterval)
  })

  function updateCountdown() {
    if (!status || !status.next_allowed_at) {
      canSmoke = true
      countdownText = 'Available now'
      progressPercent = 100
      return
    }

    const now = Date.now()
    const nextAllowed = new Date(status.next_allowed_at).getTime()
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

    // Progress: how far through the interval we are
    if (status.interval_seconds) {
      const totalMs = status.interval_seconds * 1000
      const elapsed = totalMs - diff
      progressPercent = Math.min(100, Math.max(0, (elapsed / totalMs) * 100))
    } else {
      progressPercent = 0
    }
  }

  async function handleLog(isBonus = false) {
    if (loading) return
    if (!isBonus && !canSmoke) {
      shaking = true
      setTimeout(() => { shaking = false }, 500)
      return
    }
    loading = true
    try {
      await logCigarette(isBonus)
      showUndo = true
      setTimeout(() => { showUndo = false }, 10000)
      await onRefresh()
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
          <span class="count-current">{status.today_count ?? 0}</span>
          <span class="count-sep">/</span>
          <span class="count-total">{status.daily_allowance ?? 0}</span>
        </p>
        {#if status.schedule_times && status.schedule_times.length > 0}
          <div class="dots" aria-label="Schedule times">
            {#each status.schedule_times as time, i}
              <div
                class="dot"
                class:filled={i < (status.today_count ?? 0)}
                title={time}
              ></div>
            {/each}
          </div>
        {/if}
      {:else if status.mode === 'quit'}
        <p class="countdown-label">You're free!</p>
        <p class="countdown available">🎉</p>
        <p style="text-align:center; color: var(--color-success); font-weight: 600;">
          {status.days_smoke_free ?? 0} days smoke-free
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
        🚬 Log Cigarette
      </button>

      {#if (status.bonus_remaining ?? 0) > 0}
        <button
          class="btn btn-bonus"
          onclick={() => handleLog(true)}
          disabled={loading}
          aria-label="Use bonus cigarette, {status.bonus_remaining} remaining"
        >
          🎁 Use Bonus ({status.bonus_remaining})
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
        <div class="stat-value">{status.days_on_plan ?? 0}</div>
        <div class="stat-label">Days</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{status.days_until_free ?? '—'}</div>
        <div class="stat-label">Until Free</div>
      </div>
    </div>

    <!-- Bonus remaining -->
    {#if status.bonus_remaining != null}
      <div class="card bonus-card">
        <span class="bonus-icon">🎁</span>
        <span class="bonus-text">
          {status.bonus_remaining} bonus cigarette{status.bonus_remaining !== 1 ? 's' : ''} remaining this week
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
</style>

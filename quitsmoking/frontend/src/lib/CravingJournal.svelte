<script>
  import { onMount } from 'svelte'
  import { logCraving, getCravingPatterns, getCravingTriggers } from './api.js'

  let view = $state('log') // 'log' | 'patterns'
  let triggers = $state([])
  let patterns = $state(null)
  let loading = $state(false)
  let error = $state(null)
  let successMessage = $state(null)

  // Log form state
  let selectedTrigger = $state('')
  let intensity = $state(3)
  let notes = $state('')
  let resisted = $state(true)

  const triggerLabels = {
    stress: '😤 Stress',
    boredom: '😐 Boredom',
    social: '🍻 Social',
    after_meal: '🍽️ After meal',
    coffee: '☕ Coffee',
    alcohol: '🍷 Alcohol',
    habit: '🔄 Habit',
    anxiety: '😰 Anxiety',
    celebration: '🎉 Celebration',
    other: '❓ Other',
  }

  onMount(async () => {
    try {
      const data = await getCravingTriggers()
      triggers = data.triggers
    } catch (e) {
      error = e.message
    }
  })

  async function handleSubmit() {
    if (!selectedTrigger) return
    loading = true
    error = null
    successMessage = null
    try {
      await logCraving({
        trigger: selectedTrigger,
        intensity,
        notes: notes.trim() || null,
        resisted,
      })
      successMessage = resisted ? '💪 Craving resisted! Logged.' : '🚬 Craving logged.'
      // Reset form
      selectedTrigger = ''
      intensity = 3
      notes = ''
      resisted = true
      setTimeout(() => { successMessage = null }, 3000)
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  async function loadPatterns() {
    view = 'patterns'
    loading = true
    error = null
    try {
      patterns = await getCravingPatterns()
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }
</script>

<div class="cravings fade-in">
  <!-- Toggle -->
  <div class="view-toggle">
    <button class="toggle-btn" class:active={view === 'log'} onclick={() => view = 'log'} aria-label="Log a craving">
      ✏️ Log
    </button>
    <button class="toggle-btn" class:active={view === 'patterns'} onclick={loadPatterns} aria-label="View patterns">
      📊 Patterns
    </button>
  </div>

  {#if view === 'log'}
    <!-- Log Craving Form -->
    <div class="card">
      <h2 class="section-title">What triggered the craving?</h2>

      <div class="trigger-grid">
        {#each triggers as trigger}
          <button
            class="trigger-btn"
            class:selected={selectedTrigger === trigger}
            onclick={() => selectedTrigger = trigger}
            aria-label={triggerLabels[trigger] || trigger}
            aria-pressed={selectedTrigger === trigger}
          >
            {triggerLabels[trigger] || trigger}
          </button>
        {/each}
      </div>

      <div class="intensity-section">
        <label class="field-label" for="intensity-slider">Intensity: {intensity}/5</label>
        <input
          id="intensity-slider"
          type="range"
          min="1"
          max="5"
          step="1"
          bind:value={intensity}
          class="intensity-slider"
          aria-label="Craving intensity, {intensity} out of 5"
        />
        <div class="intensity-labels">
          <span>Mild</span>
          <span>Strong</span>
        </div>
      </div>

      <div class="resist-section">
        <p class="field-label" id="resist-label">Did you resist?</p>
        <div class="resist-toggle" role="group" aria-labelledby="resist-label">
          <button
            class="resist-btn"
            class:active={resisted}
            onclick={() => resisted = true}
            aria-pressed={resisted}
          >
            💪 Yes
          </button>
          <button
            class="resist-btn gave-in"
            class:active={!resisted}
            onclick={() => resisted = false}
            aria-pressed={!resisted}
          >
            🚬 No
          </button>
        </div>
      </div>

      <div class="notes-section">
        <label class="field-label" for="craving-notes">Notes (optional)</label>
        <input
          id="craving-notes"
          type="text"
          bind:value={notes}
          placeholder="What were you doing?"
          aria-label="Optional notes about the craving"
        />
      </div>

      <button
        class="btn btn-primary submit-btn"
        onclick={handleSubmit}
        disabled={loading || !selectedTrigger}
        aria-label="Log craving"
      >
        {loading ? 'Saving...' : '📝 Log Craving'}
      </button>

      {#if successMessage}
        <p class="success-text fade-in">{successMessage}</p>
      {/if}
      {#if error}
        <p class="error-text">⚠️ {error}</p>
      {/if}
    </div>

  {:else if view === 'patterns'}
    <!-- Patterns View -->
    {#if loading}
      <div class="card" style="text-align: center; padding: 32px;">
        <p style="color: var(--color-secondary-text)">Analyzing patterns...</p>
      </div>
    {:else if patterns}
      {#if patterns.total_cravings === 0}
        <div class="card" style="text-align: center; padding: 32px;">
          <p style="color: var(--color-secondary-text)">No cravings logged yet. Start logging to see patterns!</p>
        </div>
      {:else}
        <!-- Summary -->
        <div class="card">
          <div class="pattern-stats">
            <div class="pattern-stat">
              <div class="pattern-stat-value">{patterns.total_cravings}</div>
              <div class="pattern-stat-label">Total</div>
            </div>
            <div class="pattern-stat">
              <div class="pattern-stat-value">{patterns.resist_rate}%</div>
              <div class="pattern-stat-label">Resisted</div>
            </div>
            <div class="pattern-stat">
              <div class="pattern-stat-value">{patterns.avg_intensity}/5</div>
              <div class="pattern-stat-label">Avg Intensity</div>
            </div>
          </div>
        </div>

        <!-- Insights -->
        {#if patterns.insights.length > 0}
          <div class="card">
            <h3 class="section-title">💡 Insights</h3>
            {#each patterns.insights as insight}
              <p class="insight-text">{insight}</p>
            {/each}
          </div>
        {/if}

        <!-- By Trigger -->
        {#if patterns.by_trigger.length > 0}
          <div class="card">
            <h3 class="section-title">By Trigger</h3>
            <div class="trigger-list">
              {#each patterns.by_trigger as t}
                <div class="trigger-row">
                  <span class="trigger-name">{triggerLabels[t.trigger] || t.trigger}</span>
                  <span class="trigger-count">{t.count}×</span>
                  <span class="trigger-resist">{t.resist_rate}% resisted</span>
                </div>
              {/each}
            </div>
          </div>
        {/if}

        <!-- By Hour -->
        {#if patterns.by_hour.some(h => h.count > 0)}
          <div class="card">
            <h3 class="section-title">By Time of Day</h3>
            <div class="hour-chart">
              {#each patterns.by_hour as h}
                {#if h.hour >= 6 && h.hour <= 23}
                  <div class="hour-bar-wrapper">
                    <div
                      class="hour-bar"
                      style="height: {h.count > 0 ? Math.max(8, (h.count / Math.max(...patterns.by_hour.map(x => x.count))) * 60) : 0}px"
                      title="{h.hour}:00 — {h.count} cravings"
                    ></div>
                    <span class="hour-label">{h.hour}</span>
                  </div>
                {/if}
              {/each}
            </div>
          </div>
        {/if}
      {/if}
    {/if}
  {/if}
</div>

<style>
  .cravings {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .view-toggle {
    display: flex;
    gap: 4px;
    background: var(--color-surface-elevated);
    border-radius: var(--radius-sm);
    padding: 4px;
  }

  .toggle-btn {
    flex: 1;
    padding: 10px;
    border-radius: var(--radius-sm);
    font-size: 14px;
    font-weight: 500;
    color: var(--color-secondary-text);
    transition: all var(--transition);
  }

  .toggle-btn.active {
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
  }

  .section-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: 14px;
  }

  .trigger-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    margin-bottom: 20px;
  }

  .trigger-btn {
    padding: 12px 10px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    background: var(--color-surface-elevated);
    color: var(--color-text);
    border: 2px solid transparent;
    transition: all var(--transition);
  }

  .trigger-btn.selected {
    border-color: var(--color-accent);
    background: var(--color-accent-subtle);
  }

  .field-label {
    display: block;
    font-size: 13px;
    color: var(--color-secondary-text);
    font-weight: 500;
    margin-bottom: 8px;
  }

  .intensity-section {
    margin-bottom: 20px;
  }

  .intensity-slider {
    width: 100%;
    margin: 8px 0;
    -webkit-appearance: none;
    appearance: none;
    height: 6px;
    border-radius: 3px;
    background: var(--color-surface-elevated);
    outline: none;
  }

  .intensity-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--color-accent);
    cursor: pointer;
  }

  .intensity-slider::-moz-range-thumb {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--color-accent);
    border: none;
    cursor: pointer;
  }

  .intensity-slider::-moz-range-track {
    height: 6px;
    border-radius: 3px;
    background: var(--color-surface-elevated);
  }

  .intensity-labels {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--color-secondary-text);
  }

  .resist-section {
    margin-bottom: 20px;
  }

  .resist-toggle {
    display: flex;
    gap: 8px;
  }

  .resist-btn {
    flex: 1;
    padding: 12px;
    border-radius: var(--radius-sm);
    font-size: 14px;
    background: var(--color-surface-elevated);
    color: var(--color-text);
    border: 2px solid transparent;
    transition: all var(--transition);
  }

  .resist-btn.active {
    border-color: var(--color-success);
    background: var(--color-success-subtle);
  }

  .resist-btn.gave-in.active {
    border-color: var(--color-warning);
    background: var(--color-warning-subtle);
  }

  .notes-section {
    margin-bottom: 20px;
  }

  .notes-section input {
    width: 100%;
    padding: 10px 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--color-surface-elevated);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: 14px;
  }

  .submit-btn {
    width: 100%;
  }

  .success-text {
    color: var(--color-success);
    font-size: 14px;
    text-align: center;
    margin-top: 12px;
  }

  .error-text {
    color: var(--color-danger);
    font-size: 14px;
    margin-top: 12px;
  }

  /* Patterns */
  .pattern-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    text-align: center;
  }

  .pattern-stat-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--color-accent);
  }

  .pattern-stat-label {
    font-size: 12px;
    color: var(--color-secondary-text);
    margin-top: 4px;
  }

  .insight-text {
    font-size: 14px;
    color: var(--color-text);
    padding: 8px 0;
    border-bottom: 1px solid var(--color-surface-elevated);
    line-height: 1.4;
  }

  .insight-text:last-child {
    border-bottom: none;
  }

  .trigger-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .trigger-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 0;
    border-bottom: 1px solid var(--color-surface-elevated);
  }

  .trigger-row:last-child {
    border-bottom: none;
  }

  .trigger-name {
    flex: 1;
    font-size: 14px;
    color: var(--color-text);
  }

  .trigger-count {
    font-size: 13px;
    font-weight: 600;
    color: var(--color-accent);
  }

  .trigger-resist {
    font-size: 12px;
    color: var(--color-success);
    min-width: 80px;
    text-align: right;
  }

  .hour-chart {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 80px;
    padding-top: 8px;
  }

  .hour-bar-wrapper {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }

  .hour-bar {
    width: 100%;
    background: var(--color-accent);
    border-radius: 2px 2px 0 0;
    min-width: 4px;
    transition: height var(--transition);
  }

  .hour-label {
    font-size: 9px;
    color: var(--color-secondary-text);
  }
</style>

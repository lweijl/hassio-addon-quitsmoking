<script>
  import { onMount } from 'svelte'
  import { getCatchUp, backfillDays } from './api.js'

  let { onComplete = () => {} } = $props()

  let catchUpData = $state(null)
  let visible = $state(false)
  let mode = $state('prompt') // 'prompt' | 'adjust' | 'partial'
  let adjustCounts = $state([])
  let submitting = $state(false)
  let error = $state(null)

  onMount(async () => {
    try {
      catchUpData = await getCatchUp()
      if (catchUpData.partial_yesterday) {
        mode = 'partial'
        visible = true
      } else if (catchUpData.missed_days && catchUpData.missed_days.length > 0) {
        mode = 'prompt'
        adjustCounts = catchUpData.missed_days.map(d => ({ date: d.date, count: d.allowance }))
        visible = true
      }
    } catch (e) {
      // Silently ignore catch-up errors on mount
      console.error('Catch-up check failed:', e)
    }
  })

  async function fillFullAllowance() {
    submitting = true
    error = null
    try {
      const days = catchUpData.missed_days.map(d => ({ date: d.date, count: d.allowance }))
      await backfillDays(days)
      visible = false
      onComplete()
    } catch (e) {
      error = e.message
    } finally {
      submitting = false
    }
  }

  function startAdjust() {
    mode = 'adjust'
  }

  function skip() {
    visible = false
    onComplete()
  }

  async function submitAdjusted() {
    submitting = true
    error = null
    try {
      await backfillDays(adjustCounts)
      visible = false
      onComplete()
    } catch (e) {
      error = e.message
    } finally {
      submitting = false
    }
  }

  async function confirmPartial(loggedEverything) {
    if (loggedEverything) {
      visible = false
      onComplete()
      return
    }
    // If they didn't log everything, treat yesterday as a missed day
    submitting = true
    error = null
    try {
      if (catchUpData.partial_yesterday) {
        adjustCounts = [{ date: catchUpData.partial_yesterday.date, count: catchUpData.partial_yesterday.allowance }]
        mode = 'adjust'
      } else {
        visible = false
        onComplete()
      }
    } catch (e) {
      error = e.message
    } finally {
      submitting = false
    }
  }
</script>

{#if visible}
  <div class="overlay" role="dialog" aria-modal="true" aria-labelledby="catchup-title">
    <div class="modal card fade-in">
      {#if mode === 'partial'}
        <h2 id="catchup-title" class="modal-title">📋 Quick Check</h2>
        <p class="modal-text">Did you log everything yesterday?</p>
        <div class="modal-actions">
          <button
            class="btn btn-success"
            onclick={() => confirmPartial(true)}
            disabled={submitting}
            aria-label="Yes, I logged everything yesterday"
          >
            ✅ Yes, all logged
          </button>
          <button
            class="btn btn-secondary"
            onclick={() => confirmPartial(false)}
            disabled={submitting}
            aria-label="No, I missed some entries"
          >
            ✏️ Let me fix it
          </button>
        </div>

      {:else if mode === 'prompt'}
        <h2 id="catchup-title" class="modal-title">📅 Missed Days</h2>
        <p class="modal-text">You have {catchUpData.missed_days.length} day{catchUpData.missed_days.length > 1 ? 's' : ''} without entries:</p>
        <div class="missed-list">
          {#each catchUpData.missed_days as day}
            <div class="missed-item">
              <span class="missed-date">{new Date(day.date).toLocaleDateString('en', { weekday: 'short', month: 'short', day: 'numeric' })}</span>
              <span class="missed-allowance">{day.allowance}/day</span>
            </div>
          {/each}
        </div>
        <div class="modal-actions">
          <button
            class="btn btn-primary"
            onclick={fillFullAllowance}
            disabled={submitting}
            aria-label="Fill all days with full allowance"
          >
            ✅ Fill full allowance
          </button>
          <button
            class="btn btn-secondary"
            onclick={startAdjust}
            disabled={submitting}
            aria-label="Adjust counts manually"
          >
            ✏️ Let me adjust
          </button>
          <button
            class="btn btn-secondary"
            onclick={skip}
            disabled={submitting}
            aria-label="Skip catch-up"
          >
            ⏭️ Skip
          </button>
        </div>

      {:else if mode === 'adjust'}
        <h2 id="catchup-title" class="modal-title">✏️ Adjust Counts</h2>
        <p class="modal-text">Enter how many you actually smoked each day:</p>
        <div class="adjust-list">
          {#each adjustCounts as entry, i}
            <div class="adjust-item">
              <label for="adjust-{i}" class="adjust-date">
                {new Date(entry.date).toLocaleDateString('en', { weekday: 'short', month: 'short', day: 'numeric' })}
              </label>
              <input
                id="adjust-{i}"
                type="number"
                min="0"
                max="50"
                bind:value={adjustCounts[i].count}
                aria-label="Cigarette count for {entry.date}"
              />
            </div>
          {/each}
        </div>
        <div class="modal-actions">
          <button
            class="btn btn-primary"
            onclick={submitAdjusted}
            disabled={submitting}
            aria-label="Confirm adjusted counts"
          >
            {submitting ? 'Saving...' : '💾 Confirm'}
          </button>
          <button
            class="btn btn-secondary"
            onclick={skip}
            disabled={submitting}
            aria-label="Cancel and skip"
          >
            Cancel
          </button>
        </div>
      {/if}

      {#if error}
        <p class="error-text" role="alert">⚠️ {error}</p>
      {/if}
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: var(--color-overlay);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 16px;
  }

  .modal {
    max-width: 420px;
    width: 100%;
    max-height: 80vh;
    overflow-y: auto;
    padding: 24px;
  }

  .modal-title {
    font-size: 18px;
    font-weight: 700;
    color: var(--color-text);
    margin-bottom: 12px;
  }

  .modal-text {
    font-size: 14px;
    color: var(--color-secondary-text);
    margin-bottom: 16px;
    line-height: 1.5;
  }

  .missed-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 20px;
  }

  .missed-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 12px;
    background: var(--color-surface-elevated);
    border-radius: var(--radius-sm);
  }

  .missed-date {
    font-size: 14px;
    color: var(--color-text);
  }

  .missed-allowance {
    font-size: 13px;
    color: var(--color-accent);
    font-weight: 600;
  }

  .adjust-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 20px;
  }

  .adjust-item {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .adjust-date {
    flex: 1;
    font-size: 14px;
    color: var(--color-text);
  }

  .adjust-item input {
    width: 80px;
    text-align: center;
  }

  .modal-actions {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .error-text {
    color: var(--color-danger);
    font-size: 14px;
    margin-top: 12px;
  }
</style>

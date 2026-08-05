<script>
  import { onMount } from 'svelte'
  import { getConfig, updateConfig, importEntries, importConfig } from './api.js'

  let config = $state(null)
  let loading = $state(true)
  let saving = $state(false)
  let error = $state(null)
  let successMessage = $state(null)

  let bonusPerWeek = $state(1)
  let costPerCigarette = $state(0.565)
  let baseline = $state(20)

  // Import state
  let importError = $state(null)
  let importSuccess = $state(null)
  let importing = $state(false)

  onMount(async () => {
    await fetchConfig()
  })

  async function fetchConfig() {
    loading = true
    error = null
    try {
      config = await getConfig()
      bonusPerWeek = config.bonus_per_week ?? 1
      costPerCigarette = config.cost_per_cigarette ?? 0.565
      baseline = config.baseline_daily_count ?? 20
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  async function handleSave() {
    saving = true
    error = null
    successMessage = null
    try {
      await updateConfig({
        bonus_per_week: bonusPerWeek,
        cost_per_cigarette: costPerCigarette,
        baseline_daily_count: baseline
      })
      successMessage = 'Settings saved!'
      setTimeout(() => { successMessage = null }, 3000)
    } catch (e) {
      error = e.message
    } finally {
      saving = false
    }
  }

  async function handleFileImport(event, type) {
    const file = event.target.files?.[0]
    if (!file) return

    importing = true
    importError = null
    importSuccess = null

    try {
      const text = await file.text()
      const data = JSON.parse(text)

      let result
      if (type === 'entries') {
        result = await importEntries(data)
        importSuccess = `✅ Imported ${result.imported} entries (${result.skipped_duplicates} duplicates skipped). Total: ${result.total}`
      } else {
        result = await importConfig(data)
        importSuccess = `✅ Config imported (start: ${result.start_date}, ${result.weeks} weeks)`
        await fetchConfig()
      }
    } catch (e) {
      if (e instanceof SyntaxError) {
        importError = 'Invalid JSON file'
      } else {
        importError = e.message
      }
    } finally {
      importing = false
      // Reset file input
      event.target.value = ''
    }
  }
</script>

<div class="settings fade-in">
  {#if loading}
    <div class="card" style="text-align: center; padding: 32px;">
      <p style="color: var(--color-secondary-text)">Loading settings...</p>
    </div>
  {:else if error && !config}
    <div class="card" style="text-align: center; padding: 32px;">
      <p style="color: var(--color-danger)">⚠️ {error}</p>
      <button class="btn btn-secondary" onclick={fetchConfig} style="margin-top: 12px;">Retry</button>
    </div>
  {:else}
    <!-- Schedule Table -->
    {#if config?.weekly_schedules}
      <div class="card">
        <h2 class="section-title">Tapering Schedule</h2>
        <div class="table-wrapper">
          <table class="schedule-table">
            <thead>
              <tr>
                <th>Week</th>
                <th>Mode</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {#each config.weekly_schedules as week, i}
                <tr>
                  <td>Week {i + 1}</td>
                  <td>
                    <span class="mode-pill" class:interval={week.mode === 'interval'} class:daily={week.mode === 'daily'} class:quit={week.mode === 'quit'}>
                      {week.mode}
                    </span>
                  </td>
                  <td>{week.mode === 'daily' ? `${week.allowance}/day` : week.mode === 'interval' ? `${week.interval_hours}h` : '—'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}

    <!-- Edit Config -->
    <div class="card">
      <h2 class="section-title">Configuration</h2>

      <div class="form-grid">
        <div class="form-group">
          <label for="bonus-per-week">Bonus per week</label>
          <input
            id="bonus-per-week"
            type="number"
            min="0"
            max="10"
            bind:value={bonusPerWeek}
            aria-label="Bonus cigarettes per week"
          />
        </div>

        <div class="form-group">
          <label for="cost-per-cigarette">Cost per cigarette (€)</label>
          <input
            id="cost-per-cigarette"
            type="number"
            min="0"
            step="0.01"
            bind:value={costPerCigarette}
            aria-label="Cost per cigarette in euros"
          />
        </div>

        <div class="form-group">
          <label for="baseline">Baseline (per day)</label>
          <input
            id="baseline"
            type="number"
            min="1"
            max="100"
            bind:value={baseline}
            aria-label="Baseline cigarettes per day"
          />
        </div>
      </div>

      {#if error}
        <p class="error-text">⚠️ {error}</p>
      {/if}

      {#if successMessage}
        <p class="success-text fade-in">✅ {successMessage}</p>
      {/if}

      <button
        class="btn btn-primary save-btn"
        onclick={handleSave}
        disabled={saving}
        aria-label="Save settings"
      >
        {saving ? 'Saving...' : '💾 Save Settings'}
      </button>
    </div>

    <!-- Import Data -->
    <div class="card">
      <h2 class="section-title">Import Data</h2>
      <p class="import-description">
        Import your smoking history and config from the macOS app or a previous backup.
        Accepts both the Swift app format and the addon's native format.
      </p>

      <div class="import-grid">
        <div class="import-group">
          <label for="import-entries" class="import-label">📋 Import Entries</label>
          <p class="import-hint">entries.json from macOS app or backup</p>
          <input
            id="import-entries"
            type="file"
            accept=".json"
            onchange={(e) => handleFileImport(e, 'entries')}
            disabled={importing}
            aria-label="Import cigarette entries from JSON file"
          />
        </div>

        <div class="import-group">
          <label for="import-config" class="import-label">⚙️ Import Config</label>
          <p class="import-hint">config.json from macOS app or backup</p>
          <input
            id="import-config"
            type="file"
            accept=".json"
            onchange={(e) => handleFileImport(e, 'config')}
            disabled={importing}
            aria-label="Import schedule configuration from JSON file"
          />
        </div>
      </div>

      {#if importing}
        <p class="import-status">Importing...</p>
      {/if}

      {#if importError}
        <p class="error-text">⚠️ {importError}</p>
      {/if}

      {#if importSuccess}
        <p class="success-text fade-in">{importSuccess}</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .settings {
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

  .table-wrapper {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .mode-pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
    background: var(--color-surface-elevated);
    color: var(--color-secondary-text);
  }

  .mode-pill.interval {
    background: rgba(100, 210, 255, 0.15);
    color: var(--color-accent);
  }

  .mode-pill.daily {
    background: rgba(255, 149, 0, 0.15);
    color: var(--color-warning);
  }

  .mode-pill.quit {
    background: rgba(52, 199, 89, 0.15);
    color: var(--color-success);
  }

  .form-grid {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-bottom: 16px;
  }

  @media (min-width: 480px) {
    .form-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
    }
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .form-group label {
    font-size: 13px;
    color: var(--color-secondary-text);
    font-weight: 500;
  }

  .save-btn {
    width: 100%;
    margin-top: 8px;
  }

  .error-text {
    color: var(--color-danger);
    font-size: 14px;
    margin-bottom: 8px;
  }

  .success-text {
    color: var(--color-success);
    font-size: 14px;
    margin-bottom: 8px;
  }

  .import-description {
    font-size: 13px;
    color: var(--color-secondary-text);
    margin-bottom: 16px;
    line-height: 1.5;
  }

  .import-grid {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-bottom: 16px;
  }

  @media (min-width: 480px) {
    .import-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
    }
  }

  .import-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .import-label {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text);
  }

  .import-hint {
    font-size: 12px;
    color: var(--color-secondary-text);
    margin-bottom: 6px;
  }

  .import-group input[type="file"] {
    font-size: 13px;
    color: var(--color-text);
  }

  .import-status {
    font-size: 14px;
    color: var(--color-accent);
    margin-bottom: 8px;
  }
</style>

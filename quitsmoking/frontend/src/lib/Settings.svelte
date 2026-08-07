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

  // Schedule editor state
  let editableSchedule = $state([])
  let scheduleChanged = $state(false)
  let scheduleSaving = $state(false)
  let scheduleError = $state(null)
  let scheduleSuccess = $state(null)

  // Import state
  let importError = $state(null)
  let importSuccess = $state(null)
  let importing = $state(false)

  // Notification test state
  let testingNotification = $state(false)
  let notificationResult = $state(null)

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
      editableSchedule = (config.weekly_schedules ?? []).map(w => ({ ...w }))
      scheduleChanged = false
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  function getCurrentWeekIndex() {
    if (!config?.start_date) return -1
    const start = new Date(config.start_date)
    const now = new Date()
    const diffDays = Math.floor((now - start) / (1000 * 60 * 60 * 24))
    const idx = Math.floor(diffDays / 7)
    return Math.max(0, Math.min(idx, (config.weekly_schedules?.length ?? 1) - 1))
  }

  function isFutureWeek(index) {
    return index > getCurrentWeekIndex()
  }

  function isCurrentWeek(index) {
    return index === getCurrentWeekIndex()
  }

  function updateScheduleField(index, field, value) {
    editableSchedule[index] = { ...editableSchedule[index], [field]: value }
    scheduleChanged = true
  }

  function updateScheduleMode(index, newMode) {
    const week = { ...editableSchedule[index], mode: newMode }
    if (newMode === 'daily') {
      week.allowance = week.allowance ?? 5
      delete week.interval_hours
    } else if (newMode === 'interval') {
      week.interval_hours = week.interval_hours ?? 2
      delete week.allowance
    } else if (newMode === 'quit') {
      delete week.allowance
      delete week.interval_hours
    }
    editableSchedule[index] = week
    scheduleChanged = true
  }

  function addWeek() {
    const lastWeek = editableSchedule[editableSchedule.length - 1]
    let newWeek = { mode: 'daily', allowance: 1 }
    if (lastWeek?.mode === 'quit') {
      newWeek = { mode: 'quit' }
    }
    editableSchedule = [...editableSchedule, newWeek]
    scheduleChanged = true
  }

  function deleteWeek(index) {
    editableSchedule = editableSchedule.filter((_, i) => i !== index)
    scheduleChanged = true
  }

  async function saveSchedule() {
    scheduleSaving = true
    scheduleError = null
    scheduleSuccess = null
    try {
      await updateConfig({
        bonus_per_week: bonusPerWeek,
        cost_per_cigarette: costPerCigarette,
        baseline_daily_count: baseline,
        weekly_schedules: editableSchedule
      })
      scheduleSuccess = 'Schedule saved!'
      scheduleChanged = false
      config = { ...config, weekly_schedules: editableSchedule.map(w => ({ ...w })) }
      setTimeout(() => { scheduleSuccess = null }, 3000)
    } catch (e) {
      scheduleError = e.message
    } finally {
      scheduleSaving = false
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

  async function testNotification() {
    testingNotification = true
    notificationResult = null
    try {
      const baseUrl = document.baseURI || window.location.href
      const url = new URL(baseUrl)
      let pathname = url.pathname.replace(/\/[^/]*\.[^/]*$/, '').replace(/\/$/, '')
      const resp = await fetch(`${url.origin}${pathname}/api/notifications/test`, { method: 'POST' })
      const data = await resp.json()
      if (data.status === 'ok') {
        notificationResult = `✅ Test sent to: ${data.services.join(', ')}`
      } else {
        notificationResult = `⚠️ Failed — check addon logs for details`
      }
    } catch (e) {
      notificationResult = `⚠️ Error: ${e.message}`
    } finally {
      testingNotification = false
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
    <!-- Schedule Table (Editable) -->
    {#if editableSchedule.length > 0}
      <div class="card">
        <h2 class="section-title">Tapering Schedule</h2>
        <div class="table-wrapper">
          <table class="schedule-table">
            <thead>
              <tr>
                <th></th>
                <th>Week</th>
                <th>Mode</th>
                <th>Value</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {#each editableSchedule as week, i}
                {@const past = !isFutureWeek(i) && !isCurrentWeek(i)}
                {@const current = isCurrentWeek(i)}
                {@const future = isFutureWeek(i)}
                <tr class:past-row={past} class:current-row={current}>
                  <td class="indicator-cell">
                    {#if past}
                      <span title="Locked (past week)" aria-label="Past week, locked">🔒</span>
                    {:else if current}
                      <span title="Current week" aria-label="Current week">▶️</span>
                    {/if}
                  </td>
                  <td>Week {i + 1}</td>
                  <td>
                    {#if future}
                      <select
                        value={week.mode}
                        onchange={(e) => updateScheduleMode(i, e.target.value)}
                        aria-label="Mode for week {i + 1}"
                        class="mode-select"
                      >
                        <option value="daily">daily</option>
                        <option value="interval">interval</option>
                        <option value="quit">quit</option>
                      </select>
                    {:else}
                      <span class="mode-pill" class:interval={week.mode === 'interval'} class:daily={week.mode === 'daily'} class:quit={week.mode === 'quit'}>
                        {week.mode}
                      </span>
                    {/if}
                  </td>
                  <td>
                    {#if future && week.mode === 'daily'}
                      <input
                        type="number"
                        min="0"
                        max="50"
                        value={week.allowance ?? 0}
                        onchange={(e) => updateScheduleField(i, 'allowance', parseInt(e.target.value) || 0)}
                        class="schedule-input"
                        aria-label="Daily allowance for week {i + 1}"
                      />
                      <span class="input-suffix">/day</span>
                    {:else if future && week.mode === 'interval'}
                      <input
                        type="number"
                        min="0.5"
                        max="24"
                        step="0.5"
                        value={week.interval_hours ?? 2}
                        onchange={(e) => updateScheduleField(i, 'interval_hours', parseFloat(e.target.value) || 2)}
                        class="schedule-input"
                        aria-label="Interval hours for week {i + 1}"
                      />
                      <span class="input-suffix">hours</span>
                    {:else if !future && week.mode === 'daily'}
                      {week.allowance}/day
                    {:else if !future && week.mode === 'interval'}
                      {week.interval_hours}h
                    {:else}
                      —
                    {/if}
                  </td>
                  <td class="action-cell">
                    {#if future}
                      <button
                        class="delete-btn"
                        onclick={() => deleteWeek(i)}
                        aria-label="Delete week {i + 1}"
                        title="Delete week"
                      >
                        ✕
                      </button>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>

        <div class="schedule-actions">
          <button
            class="btn btn-secondary add-week-btn"
            onclick={addWeek}
            aria-label="Add a new week to the schedule"
          >
            ➕ Add Week
          </button>

          {#if scheduleChanged}
            <button
              class="btn btn-primary"
              onclick={saveSchedule}
              disabled={scheduleSaving}
              aria-label="Save schedule changes"
            >
              {scheduleSaving ? 'Saving...' : '💾 Save Schedule'}
            </button>
          {/if}
        </div>

        {#if scheduleError}
          <p class="error-text">⚠️ {scheduleError}</p>
        {/if}

        {#if scheduleSuccess}
          <p class="success-text fade-in">✅ {scheduleSuccess}</p>
        {/if}
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
          <span class="import-label">📋 Import Entries</span>
          <p class="import-hint">entries.json from macOS app or backup</p>
          <label class="btn btn-secondary upload-btn" for="import-entries" aria-label="Choose entries file to import">
            📋 Choose File
          </label>
          <input
            id="import-entries"
            type="file"
            accept=".json"
            class="sr-only"
            onchange={(e) => handleFileImport(e, 'entries')}
            disabled={importing}
          />
        </div>

        <div class="import-group">
          <span class="import-label">⚙️ Import Config</span>
          <p class="import-hint">config.json from macOS app or backup</p>
          <label class="btn btn-secondary upload-btn" for="import-config" aria-label="Choose config file to import">
            ⚙️ Choose File
          </label>
          <input
            id="import-config"
            type="file"
            accept=".json"
            class="sr-only"
            onchange={(e) => handleFileImport(e, 'config')}
            disabled={importing}
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

    <!-- Notifications -->
    <div class="card">
      <h2 class="section-title">Notifications</h2>
      <p class="import-description">
        Send a test notification to verify your configured devices receive it.
        Configure which devices get notifications in the addon's Configuration tab.
      </p>
      <button
        class="btn btn-primary"
        onclick={testNotification}
        disabled={testingNotification}
        aria-label="Send test notification"
      >
        {testingNotification ? '📡 Sending...' : '🔔 Send Test Notification'}
      </button>
      {#if notificationResult}
        <p class="notification-result fade-in" class:success-text={notificationResult.startsWith('✅')} class:error-text={notificationResult.startsWith('⚠️')}>
          {notificationResult}
        </p>
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
    background: var(--color-accent-subtle);
    color: var(--color-accent);
  }

  .mode-pill.daily {
    background: var(--color-warning-subtle);
    color: var(--color-warning);
  }

  .mode-pill.quit {
    background: var(--color-success-subtle);
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

  .upload-btn {
    align-self: flex-start;
    font-size: 14px;
    padding: 10px 16px;
    min-height: 40px;
    cursor: pointer;
  }

  .import-status {
    font-size: 14px;
    color: var(--color-accent);
    margin-bottom: 8px;
  }

  /* Schedule editor styles */
  .past-row {
    opacity: 0.5;
  }

  .current-row {
    background: var(--color-accent-subtle);
  }

  .indicator-cell {
    width: 30px;
    text-align: center;
    font-size: 14px;
  }

  .action-cell {
    width: 40px;
    text-align: center;
  }

  .mode-select {
    padding: 6px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--color-surface-elevated);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: 13px;
    font-family: inherit;
    cursor: pointer;
  }

  .mode-select:focus {
    border-color: var(--color-accent);
    outline: none;
  }

  .schedule-input {
    width: 60px;
    padding: 6px 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--color-surface-elevated);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: 13px;
    font-family: inherit;
    text-align: center;
  }

  .schedule-input:focus {
    border-color: var(--color-accent);
    outline: none;
  }

  .input-suffix {
    font-size: 12px;
    color: var(--color-secondary-text);
    margin-left: 4px;
  }

  .delete-btn {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--color-danger-subtle);
    color: var(--color-danger);
    font-size: 12px;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: all var(--transition);
  }

  .delete-btn:hover {
    background: var(--color-danger);
    color: #FFF;
  }

  .schedule-actions {
    display: flex;
    gap: 10px;
    margin-top: 16px;
    flex-wrap: wrap;
  }

  .add-week-btn {
    font-size: 14px;
    padding: 10px 16px;
    min-height: 40px;
  }

  .notification-result {
    margin-top: 12px;
    font-size: 14px;
  }
</style>

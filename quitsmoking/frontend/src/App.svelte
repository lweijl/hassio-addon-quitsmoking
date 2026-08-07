<script>
  import { onMount, onDestroy } from 'svelte'
  import Dashboard from './lib/Dashboard.svelte'
  import History from './lib/History.svelte'
  import Progress from './lib/Progress.svelte'
  import Settings from './lib/Settings.svelte'
  import CatchUp from './lib/CatchUp.svelte'
  import HealthTimeline from './lib/HealthTimeline.svelte'
  import CravingJournal from './lib/CravingJournal.svelte'
  import WeeklyReport from './lib/WeeklyReport.svelte'
  import { getStatus, logCigarette } from './lib/api.js'

  let activeTab = $state('dashboard')
  let status = $state(null)
  let error = $state(null)
  let refreshInterval = null
  let actionMessage = $state(null)

  async function fetchStatus() {
    try {
      status = await getStatus()
      error = null
    } catch (e) {
      error = e.message
      console.error('Failed to fetch status:', e)
    }
  }

  onMount(() => {
    fetchStatus()
    refreshInterval = setInterval(fetchStatus, 30000)
    handleActionParam()
  })

  onDestroy(() => {
    if (refreshInterval) clearInterval(refreshInterval)
  })

  async function handleActionParam() {
    // Check both query param and hash fragment for action
    const params = new URLSearchParams(window.location.search)
    let action = params.get('action')

    // Also check hash fragment (e.g., #action=log)
    if (!action && window.location.hash) {
      const hashParams = new URLSearchParams(window.location.hash.substring(1))
      action = hashParams.get('action')
    }

    if (!action) return

    // Clear the action from URL (so refresh doesn't re-trigger)
    const url = new URL(window.location)
    url.searchParams.delete('action')
    url.hash = ''
    window.history.replaceState({}, '', url)

    try {
      if (action === 'log') {
        await logCigarette(false)
        actionMessage = '🚬 Logged from notification!'
        await fetchStatus()
      } else if (action === 'log_bonus') {
        await logCigarette(true)
        actionMessage = '🎁 Bonus logged from notification!'
        await fetchStatus()
      } else if (action === 'skip') {
        // Call skip endpoint
        const baseUrl = document.baseURI || window.location.href
        const urlObj = new URL(baseUrl)
        let pathname = urlObj.pathname.replace(/\/[^/]*\.[^/]*$/, '').replace(/\/$/, '')
        await fetch(`${urlObj.origin}${pathname}/api/actions/skip`, { method: 'POST' })
        actionMessage = '💪 Craving resisted!'
      } else if (action === 'test') {
        actionMessage = '✅ Action navigation works! Nothing was logged.'
      }
      setTimeout(() => { actionMessage = null }, 5000)
    } catch (e) {
      console.error('Action failed:', e)
    }
  }

  function setTab(tab) {
    activeTab = tab
  }

  function handleCatchUpComplete() {
    fetchStatus()
  }
</script>

<div class="container">
  <header class="app-header">
    <h1 class="app-title">🚭 QuitSmoking <span class="app-version">2.0.2</span></h1>
  </header>

  <nav class="tab-nav" role="tablist" aria-label="Main navigation">
    <button
      class="tab-btn"
      class:active={activeTab === 'dashboard'}
      onclick={() => setTab('dashboard')}
      role="tab"
      aria-selected={activeTab === 'dashboard'}
      aria-label="Dashboard"
    >
      <span class="tab-icon">🏠</span>
      <span class="tab-label">Home</span>
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'health'}
      onclick={() => setTab('health')}
      role="tab"
      aria-selected={activeTab === 'health'}
      aria-label="Health Timeline"
    >
      <span class="tab-icon">🫁</span>
      <span class="tab-label">Health</span>
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'cravings'}
      onclick={() => setTab('cravings')}
      role="tab"
      aria-selected={activeTab === 'cravings'}
      aria-label="Craving Journal"
    >
      <span class="tab-icon">📓</span>
      <span class="tab-label">Log</span>
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'report'}
      onclick={() => setTab('report')}
      role="tab"
      aria-selected={activeTab === 'report'}
      aria-label="Weekly Report"
    >
      <span class="tab-icon">📊</span>
      <span class="tab-label">Report</span>
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'history'}
      onclick={() => setTab('history')}
      role="tab"
      aria-selected={activeTab === 'history'}
      aria-label="History"
    >
      <span class="tab-icon">📈</span>
      <span class="tab-label">History</span>
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'progress'}
      onclick={() => setTab('progress')}
      role="tab"
      aria-selected={activeTab === 'progress'}
      aria-label="Progress"
    >
      <span class="tab-icon">🏆</span>
      <span class="tab-label">Goals</span>
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'settings'}
      onclick={() => setTab('settings')}
      role="tab"
      aria-selected={activeTab === 'settings'}
      aria-label="Settings"
    >
      <span class="tab-icon">⚙️</span>
      <span class="tab-label">Config</span>
    </button>
  </nav>

  {#if error}
    <div class="error-banner fade-in" role="alert">
      <span>⚠️ {error}</span>
      <button class="btn btn-secondary" onclick={fetchStatus} aria-label="Retry">Retry</button>
    </div>
  {/if}

  {#if actionMessage}
    <div class="action-banner fade-in" role="status">
      <span>{actionMessage}</span>
    </div>
  {/if}

  <main class="tab-content fade-in">
    {#if activeTab === 'dashboard'}
      <Dashboard {status} onRefresh={fetchStatus} onNavigate={setTab} />
    {:else if activeTab === 'health'}
      <HealthTimeline />
    {:else if activeTab === 'cravings'}
      <CravingJournal />
    {:else if activeTab === 'report'}
      <WeeklyReport />
    {:else if activeTab === 'history'}
      <History />
    {:else if activeTab === 'progress'}
      <Progress />
    {:else if activeTab === 'settings'}
      <Settings />
    {/if}
  </main>

  <CatchUp onComplete={handleCatchUpComplete} />
</div>

<style>
  .app-header {
    text-align: center;
    margin-bottom: 16px;
  }

  .app-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--color-text);
  }

  .app-version {
    font-size: 0.6rem;
    font-weight: 400;
    color: var(--color-secondary-text);
    vertical-align: super;
  }

  .tab-content {
    margin-top: 16px;
  }

  .error-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    background: var(--color-danger-subtle);
    border: 1px solid var(--color-danger);
    border-radius: var(--radius-sm);
    padding: 12px 16px;
    margin-top: 12px;
    font-size: 14px;
    color: var(--color-danger);
  }

  .action-banner {
    background: var(--color-success-subtle);
    border: 1px solid var(--color-success);
    border-radius: var(--radius-sm);
    padding: 12px 16px;
    margin-top: 12px;
    font-size: 14px;
    color: var(--color-success);
    text-align: center;
  }
</style>

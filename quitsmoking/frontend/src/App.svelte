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
    const params = new URLSearchParams(window.location.search)
    const action = params.get('action')
    if (!action) return

    // Clear the query param from URL (so refresh doesn't re-trigger)
    const url = new URL(window.location)
    url.searchParams.delete('action')
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
    <h1 class="app-title">🚭 QuitSmoking</h1>
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
      🏠
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'health'}
      onclick={() => setTab('health')}
      role="tab"
      aria-selected={activeTab === 'health'}
      aria-label="Health Timeline"
    >
      🫁
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'cravings'}
      onclick={() => setTab('cravings')}
      role="tab"
      aria-selected={activeTab === 'cravings'}
      aria-label="Craving Journal"
    >
      📓
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'report'}
      onclick={() => setTab('report')}
      role="tab"
      aria-selected={activeTab === 'report'}
      aria-label="Weekly Report"
    >
      📊
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'history'}
      onclick={() => setTab('history')}
      role="tab"
      aria-selected={activeTab === 'history'}
      aria-label="History"
    >
      📈
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'progress'}
      onclick={() => setTab('progress')}
      role="tab"
      aria-selected={activeTab === 'progress'}
      aria-label="Progress"
    >
      🏆
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'settings'}
      onclick={() => setTab('settings')}
      role="tab"
      aria-selected={activeTab === 'settings'}
      aria-label="Settings"
    >
      ⚙️
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
      <Dashboard {status} onRefresh={fetchStatus} />
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

  .tab-content {
    margin-top: 16px;
  }

  .error-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    background: rgba(255, 59, 48, 0.15);
    border: 1px solid var(--color-danger);
    border-radius: var(--radius-sm);
    padding: 12px 16px;
    margin-top: 12px;
    font-size: 14px;
    color: var(--color-danger);
  }

  .action-banner {
    background: rgba(52, 199, 89, 0.15);
    border: 1px solid var(--color-success);
    border-radius: var(--radius-sm);
    padding: 12px 16px;
    margin-top: 12px;
    font-size: 14px;
    color: var(--color-success);
    text-align: center;
  }
</style>

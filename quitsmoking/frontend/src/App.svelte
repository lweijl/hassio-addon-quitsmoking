<script>
  import { onMount, onDestroy } from 'svelte'
  import Dashboard from './lib/Dashboard.svelte'
  import History from './lib/History.svelte'
  import Progress from './lib/Progress.svelte'
  import Settings from './lib/Settings.svelte'
  import CatchUp from './lib/CatchUp.svelte'
  import { getStatus } from './lib/api.js'

  let activeTab = $state('dashboard')
  let status = $state(null)
  let error = $state(null)
  let refreshInterval = null

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
  })

  onDestroy(() => {
    if (refreshInterval) clearInterval(refreshInterval)
  })

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
      Dashboard
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'history'}
      onclick={() => setTab('history')}
      role="tab"
      aria-selected={activeTab === 'history'}
      aria-label="History"
    >
      History
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'progress'}
      onclick={() => setTab('progress')}
      role="tab"
      aria-selected={activeTab === 'progress'}
      aria-label="Progress"
    >
      Progress
    </button>
    <button
      class="tab-btn"
      class:active={activeTab === 'settings'}
      onclick={() => setTab('settings')}
      role="tab"
      aria-selected={activeTab === 'settings'}
      aria-label="Settings"
    >
      Settings
    </button>
  </nav>

  {#if error}
    <div class="error-banner fade-in" role="alert">
      <span>⚠️ {error}</span>
      <button class="btn btn-secondary" onclick={fetchStatus} aria-label="Retry">Retry</button>
    </div>
  {/if}

  <main class="tab-content fade-in">
    {#if activeTab === 'dashboard'}
      <Dashboard {status} onRefresh={fetchStatus} />
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
</style>

/**
 * API helper for QuitSmoking Home Assistant add-on.
 * Detects the ingress base URL automatically.
 */

function getBaseUrl() {
  // HA ingress sets the base URI to the ingress path
  const base = document.baseURI || window.location.href
  const url = new URL(base)
  // Remove trailing slash and any file references
  let pathname = url.pathname.replace(/\/[^/]*\.[^/]*$/, '')
  // Remove trailing slash
  pathname = pathname.replace(/\/$/, '')
  return `${url.origin}${pathname}/api`
}

const BASE_URL = getBaseUrl()

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    },
    ...options
  }

  const response = await fetch(url, config)

  if (!response.ok) {
    const error = await response.text().catch(() => 'Unknown error')
    throw new Error(`API Error ${response.status}: ${error}`)
  }

  return response.json()
}

/**
 * Get current smoking status (mode, next allowed, counts, etc.)
 */
export function getStatus() {
  // Cache-bust to avoid stale responses through HA ingress proxy
  return request(`/status?_=${Date.now()}`)
}

/**
 * Log a cigarette
 * @param {boolean} isBonus - Whether this uses a bonus allowance
 * @param {string|null} timestamp - Optional ISO timestamp to log for a past date
 */
export function logCigarette(isBonus = false, timestamp = null) {
  const body = { is_bonus: isBonus }
  if (timestamp) body.timestamp = timestamp
  return request('/log', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

/**
 * Undo the last logged cigarette
 */
export function undoLast() {
  return request('/undo', {
    method: 'POST'
  })
}

/**
 * Get smoking history (daily counts)
 */
export function getHistory() {
  return request('/history')
}

/**
 * Get current configuration
 */
export function getConfig() {
  return request('/config')
}

/**
 * Update configuration
 * @param {object} config - Configuration object to save
 */
export function updateConfig(config) {
  return request('/config', {
    method: 'PUT',
    body: JSON.stringify(config)
  })
}

/**
 * Import entries from Swift app or backup
 * @param {object|array} data - Entries in Swift format ({version, entries}) or addon format (array)
 */
export function importEntries(data) {
  return request('/import/entries', {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

/**
 * Import config from Swift app or backup
 * @param {object} data - Config in Swift format (camelCase) or addon format (snake_case)
 */
export function importConfig(data) {
  return request('/import/config', {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

/**
 * Get catch-up info for missed days and partial yesterday
 */
export function getCatchUp() {
  return request('/catchup')
}

/**
 * Backfill missed days with cigarette counts
 * @param {Array<{date: string, count: number}>} days - Array of day entries to backfill
 */
export function backfillDays(days) {
  return request('/catchup/backfill', {
    method: 'POST',
    body: JSON.stringify({ days })
  })
}

/**
 * Get progress data (charts, milestones, projections)
 */
export function getProgress() {
  return request('/progress')
}

/**
 * Get health timeline (milestones based on time since last smoke)
 */
export function getHealthTimeline() {
  return request('/health-timeline')
}

/**
 * Log a craving event
 * @param {object} entry - {trigger, intensity, notes, resisted}
 */
export function logCraving(entry) {
  return request('/cravings', {
    method: 'POST',
    body: JSON.stringify(entry)
  })
}

/**
 * Get craving patterns analysis
 */
export function getCravingPatterns() {
  return request('/cravings/patterns')
}

/**
 * Get list of valid craving triggers
 */
export function getCravingTriggers() {
  return request('/cravings/triggers')
}

/**
 * Get detailed weekly report card
 */
export function getWeeklyReport() {
  return request('/report/weekly')
}

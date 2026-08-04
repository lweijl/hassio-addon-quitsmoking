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
  return request('/status')
}

/**
 * Log a cigarette
 * @param {boolean} isBonus - Whether this uses a bonus allowance
 */
export function logCigarette(isBonus = false) {
  return request('/log', {
    method: 'POST',
    body: JSON.stringify({ is_bonus: isBonus })
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

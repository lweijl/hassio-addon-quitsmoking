import './app.css'
import App from './App.svelte'
import { mount } from 'svelte'

// Theme detection — HA ingress iframe aware
;(function initTheme() {
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme
    // Update color-scheme for native form controls (inputs, scrollbars, etc.)
    const meta = document.querySelector('meta[name="color-scheme"]')
    if (meta) meta.content = theme === 'light' ? 'light dark' : 'dark light'
    // Update theme-color for mobile browser chrome
    const themeMeta = document.querySelector('meta[name="theme-color"]')
    if (themeMeta) themeMeta.content = theme === 'light' ? '#F2F2F7' : '#1C1C1E'
    window.dispatchEvent(new CustomEvent('themechange'))
  }

  function detectTheme() {
    // 1. Explicit URL param override (?theme=light or ?theme=dark)
    const params = new URLSearchParams(window.location.search)
    const haTheme = params.get('theme')
    if (haTheme) return haTheme

    // 2. Try reading HA theme from parent document (same-origin ingress iframe)
    try {
      const parentHA = window.parent.document.querySelector('home-assistant')
      if (parentHA && parentHA.hass && parentHA.hass.themes) {
        return parentHA.hass.themes.darkMode ? 'dark' : 'light'
      }
    } catch (e) { /* cross-origin or no parent — ignore */ }

    // 3. Check if HA injected background styles on our body
    const bodyBg = getComputedStyle(document.body).backgroundColor
    if (bodyBg && bodyBg !== 'rgba(0, 0, 0, 0)' && bodyBg !== 'transparent') {
      const match = bodyBg.match(/(\d+),\s*(\d+),\s*(\d+)/)
      if (match) {
        const avg = (parseInt(match[1]) + parseInt(match[2]) + parseInt(match[3])) / 3
        if (avg > 128) return 'light'
        if (avg < 50) return 'dark'
      }
    }

    // 4. System preference fallback
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  }

  // Initial detection
  applyTheme(detectTheme())

  // Re-check after HA has time to inject styles
  setTimeout(() => {
    const newTheme = detectTheme()
    if (newTheme !== document.documentElement.dataset.theme) {
      applyTheme(newTheme)
    }
  }, 300)

  // Second re-check for slow connections
  setTimeout(() => {
    const newTheme = detectTheme()
    if (newTheme !== document.documentElement.dataset.theme) {
      applyTheme(newTheme)
    }
  }, 1000)

  // Listen for system preference changes
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
    applyTheme(e.matches ? 'light' : 'dark')
  })

  // Watch for HA theme changes via parent document (live switching)
  try {
    const parentDoc = window.parent.document
    const observer = new MutationObserver(() => {
      const ha = parentDoc.querySelector('home-assistant')
      if (ha && ha.hass && ha.hass.themes) {
        const newTheme = ha.hass.themes.darkMode ? 'dark' : 'light'
        if (newTheme !== document.documentElement.dataset.theme) {
          applyTheme(newTheme)
        }
      }
    })
    observer.observe(parentDoc.documentElement, { attributes: true, attributeFilter: ['style'] })
  } catch (e) { /* not in HA iframe — ignore */ }
})()

const app = mount(App, {
  target: document.getElementById('app')
})

export default app

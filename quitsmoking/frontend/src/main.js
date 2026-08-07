import './app.css'
import App from './App.svelte'
import { mount } from 'svelte'

// Theme detection — respects system preference and HA theme override
;(function initTheme() {
  const params = new URLSearchParams(window.location.search)
  const haTheme = params.get('theme')
  if (haTheme) {
    document.documentElement.dataset.theme = haTheme
  }
  // Listen for system preference changes (when no explicit override)
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
    if (document.documentElement.dataset.theme) return
    // CSS @media handles it automatically, but dispatch event for chart re-render
    window.dispatchEvent(new CustomEvent('themechange'))
  })
})()

const app = mount(App, {
  target: document.getElementById('app')
})

export default app

import './app.css'
import App from './App.svelte'
import { mount } from 'svelte'

// Theme detection — respects system preference and HA theme override
;(function initTheme() {
  const params = new URLSearchParams(window.location.search)
  const haTheme = params.get('theme')
  if (haTheme) {
    document.documentElement.dataset.theme = haTheme
  } else if (window.matchMedia('(prefers-color-scheme: light)').matches) {
    // Explicitly set data-theme so CSS vars update even if media query
    // doesn't propagate into HA ingress iframe
    document.documentElement.dataset.theme = 'light'
  }
  // Listen for system preference changes
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
    document.documentElement.dataset.theme = e.matches ? 'light' : 'dark'
    window.dispatchEvent(new CustomEvent('themechange'))
  })
})()

const app = mount(App, {
  target: document.getElementById('app')
})

export default app

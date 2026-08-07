/**
 * Chart.js color helper — adapts chart colors to current theme.
 * Canvas can't read CSS vars at render time, so we compute them.
 */
export function getChartColors() {
  const theme = document.documentElement.dataset.theme
  const isDark = theme !== 'light'

  return {
    regular: isDark ? 'rgba(100, 210, 255, 0.7)' : 'rgba(0, 122, 255, 0.6)',
    regularBorder: isDark ? 'rgba(100, 210, 255, 1)' : 'rgba(0, 122, 255, 1)',
    bonus: 'rgba(175, 82, 222, 0.7)',
    bonusBorder: 'rgba(175, 82, 222, 1)',
    allowanceLine: 'rgba(255, 149, 0, 0.8)',
    avoided: isDark ? 'rgba(52, 199, 89, 1)' : 'rgba(40, 167, 69, 1)',
    avoidedBg: isDark ? 'rgba(52, 199, 89, 0.1)' : 'rgba(40, 167, 69, 0.06)',
    saved: isDark ? 'rgba(100, 210, 255, 1)' : 'rgba(0, 122, 255, 1)',
    savedBg: isDark ? 'rgba(100, 210, 255, 0.1)' : 'rgba(0, 122, 255, 0.06)',
    grid: isDark ? 'rgba(142, 142, 147, 0.1)' : 'rgba(142, 142, 147, 0.15)',
    ticks: isDark ? '#8E8E93' : '#6C6C70',
    tooltipBg: isDark ? '#2C2C2E' : '#FFFFFF',
    tooltipTitle: isDark ? '#FFFFFF' : '#1C1C1E',
    tooltipBody: isDark ? '#8E8E93' : '#6C6C70',
    tooltipBorder: isDark ? '#3A3A3C' : '#E5E5EA',
    legendColor: isDark ? '#8E8E93' : '#6C6C70',
  }
}

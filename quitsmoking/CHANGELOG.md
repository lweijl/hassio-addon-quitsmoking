# Changelog

## 1.1.0

### New Features
- **Catch-Up Manager**: Detects missed days on app load, shows dialog to backfill entries or skip. Also detects partially-logged yesterday.
- **Progress tab**: Cumulative line charts (avoided + saved), milestones with checkmarks, fun equivalents (coffees, pizzas, concerts), weekly comparison table, projections to quit date.
- **Schedule editor**: Edit future weeks directly in Settings. Add/remove weeks, change mode (daily/interval/quit), lock past weeks.
- **Smoking times timeline**: Visual dot timeline in daily mode showing past (green), current (pulsing blue), and future (gray) scheduled times.
- **Scheduled notifications**: Background task sends daily reminders (9AM), weekly Monday summaries, per-cigarette time alerts, and interval-elapsed notifications via HA notify.

### Improvements
- Dashboard: countdown progress bar now ticks correctly using interval_hours
- Dashboard: schedule_times rendered from [hour, minute] tuples correctly
- 4 tabs: Dashboard, History, Progress, Settings

## 1.0.8

- Fix history chart: endpoint now returns daily aggregated data (`{days: [...]}`)
- Fix Settings: schedule table and baseline field names aligned with API
- Fix Dashboard: all stat fields now use correct API response names

## 1.0.7

- Fix Dashboard field name mismatches (next_allowed_time, remaining_bonus, days_since_start, days_until_quit, smoked_today)

## 1.0.6

- Add `cd /app` in run.sh for correct Python module resolution
- Add `/api/health` debug endpoint
- Add `addon_config:rw` mapping

## 1.0.5

- Add web UI import for entries and config (Settings → Import Data)
- Accepts both Swift macOS app format and addon native format
- Auto-deduplicates entries on import

## 1.0.4

- Fix s6-overlay v3 shebang: `#!/command/with-contenv bashio`
- Add `init: false` to config.yaml (required for s6v3)
- Add `homeassistant_api: true` for notification access
- Add Docker labels (required by Supervisor 2026.04.0+)
- Fix notification service name parsing (strip `notify.` prefix)
- Replace echo with `bashio::log` for proper HA logging
- Remove unnecessary CORS middleware
- Add migration script (`migrate_from_swift.py`)

## 1.0.1

- Fix architecture-specific base image selection via `build.yaml`
- Default `BUILD_FROM` to amd64 for local builds

## 1.0.0

- Initial release
- Smoking cessation tracker with interval and daily scheduling
- Progress statistics (cigarettes avoided, money saved)
- HA notifications on cigarette logging and limit reached
- Ingress-based web UI with sidebar panel

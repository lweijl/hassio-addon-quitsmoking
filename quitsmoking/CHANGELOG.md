# Changelog

## 1.3.1

### Fixes
- **Notification dedup survives restarts**: The "already sent" tracking was in-memory only, so every addon restart (including updates) would re-fire the morning notification. Now persisted to `sent_notifications.json` on disk.

## 1.3.0

### New Features
- **Health Timeline**: New tab (🫁) showing real health recovery milestones tied to your time since last cigarette. Progress rings show how close you are to each milestone.
- **Craving Journal**: New tab (📓) to log cravings with trigger, intensity (1-5), and whether you resisted. Patterns view shows analysis by trigger, time of day, and trends.
- **Weekly Report Card**: New tab (📊) with detailed weekly breakdown — grade (A-D), daily smoked vs allowance bars, best day, longest gap, achievements, and comparison to last week.

### Improvements
- **Navigation**: Tabs now use icons to fit all 7 sections (🏠 🫁 📓 📊 📈 🏆 ⚙️).

### Fixes
- **Docker version label**: Fixed `io.hass.version` label in Dockerfile — was hardcoded to 1.1.0, causing HA to not detect updates. Now uses `BUILD_VERSION` arg synced with config.yaml.

## 1.2.4

### New Features
- **Configurable notification targets**: Choose which devices receive notifications instead of broadcasting to all. Configure a list of specific services (e.g., `notify.mobile_app_iphone_van_papa`) in the addon settings.
- **Test notification button**: In Settings, tap "🔔 Send Test Notification" to verify your devices receive it.
- **Log for past date**: New "📅 Log for a past date" button on the dashboard lets you retroactively log cigarettes (including bonus) for yesterday or earlier.
- **Debug endpoint**: `GET /api/debug` shows raw computed values for troubleshooting.

### Bug Fixes
- **Countdown after logging (interval mode)**: Timestamp was not timezone-normalized, causing "Available now" to persist after logging.
- **Countdown after logging (daily mode)**: Now scans forward to find the next *future* scheduled slot instead of only checking one.
- **Backfill blocked on partial days**: Backfill now allows adding entries to days that already have some (was incorrectly skipping them).

### Improvements
- **Robust notification scheduler**: Notifications no longer require hitting the exact minute. Uses `>=` checks with dedup tracking — if the addon restarts or lags, it catches up on the next 60s tick.
- **Interval notification resets per log**: The "interval elapsed" notification is tied to the specific last entry, so it resets automatically after each new cigarette.
- **Daily slot dedup**: Each scheduled slot is tracked individually to avoid duplicate reminders.

### Configuration
- New `notify_services` option: list of HA notify services to target.
- Legacy `notify_service` (single) still works as fallback.
- If neither is set, falls back to `notify.notify` (broadcast to all).

### Bug Fixes
- **Countdown after logging (interval mode)**: Timestamp was not timezone-normalized, causing "Available now" to persist after logging.
- **Countdown after logging (daily mode)**: Now scans forward to find the next *future* scheduled slot instead of only checking one.

### Configuration
- New `notify_services` option: list of HA notify services to target.
- Legacy `notify_service` (single) still works as fallback.
- If neither is set, falls back to `notify.notify` (broadcast to all).

## 1.2.0

### Bug Fixes
- **Timer fix**: "Next cigarette in" no longer always shows "Available now" after logging. Fixed HTTP caching issue (added no-cache headers + cache-busting) and made frontend use POST /api/log response directly.
- **Daily mode countdown**: Daily mode now shows countdown to next scheduled smoke time instead of always "available now". After logging at slot 1, you'll see a countdown to slot 2.

### New Features
- **Actionable notifications**: All notifications now include tappable buttons:
  - "⏰ Scheduled smoke time" → [🚬 Log it] [💪 Skip it] [📱 Open]
  - "✅ Interval elapsed" → [🚬 Log it] [💪 Skip it] [📱 Open]
  - "⚠️ Daily limit reached" → [🎁 Use Bonus] [📊 Progress]
  - "☀️ Good morning" → [📱 Open] [📊 Progress]
- **Quick-log from notification**: Tap "Log it" to log a cigarette without opening the app.
- **Skip/resist craving**: Tap "Skip it" to get an encouragement message with your stats.
- **Evening check-in (21:00)**: Daily summary notification — congratulates if under budget, acknowledges if on track.
- **Notification tags**: Notifications use tags so newer ones replace older ones (no spam).

### Improvements
- **Better notification content**: Log notifications now show next allowed time, remaining count, and cumulative avoided count.
- **Log button disabled when at limit**: In daily mode, the log button is disabled when remaining = 0.

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

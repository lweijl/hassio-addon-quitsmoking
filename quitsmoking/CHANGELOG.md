# Changelog

## 1.0.3

- Fix s6-overlay v3 compatibility (`init: false`, correct shebang)
- Fix architecture-specific base image selection via `build.yaml`
- Add required `homeassistant_api: true` for notifications
- Fix notification service name parsing (strip `notify.` prefix)
- Replace echo with bashio::log for proper HA logging
- Remove unnecessary CORS middleware
- Add Docker labels required by Supervisor 2026.04.0+

## 1.0.0

- Initial release
- Smoking cessation tracker with interval and daily scheduling
- Progress statistics (cigarettes avoided, money saved)
- HA notifications on cigarette logging and limit reached
- Ingress-based web UI with sidebar panel

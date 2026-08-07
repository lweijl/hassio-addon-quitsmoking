#!/command/with-contenv bashio
set -e

# Read ingress entry from Supervisor
INGRESS_ENTRY=$(bashio::addon.ingress_entry)
export INGRESS_PATH="${INGRESS_ENTRY}"

# Addon slug for companion app navigation
# Try bashio first, fall back to HOSTNAME (set by HA to addon slug)
ADDON_SLUG=$(bashio::addon.slug 2>/dev/null || echo "")
if [ -z "$ADDON_SLUG" ]; then
    ADDON_SLUG="${HOSTNAME:-472f365d_quitsmoking}"
fi
export ADDON_SLUG

# Data directory for persistence
export DATA_DIR="/config/quitsmoking"
mkdir -p "$DATA_DIR"

# Read notify_services for migration (configured in-app after first startup)
NOTIFY_SERVICES_JSON=$(bashio::config 'notify_services' 2>/dev/null || echo "")
if [ "$NOTIFY_SERVICES_JSON" != "null" ] && [ -n "$NOTIFY_SERVICES_JSON" ]; then
    export NOTIFY_SERVICES=$(bashio::config 'notify_services | join(",")' 2>/dev/null || echo "")
fi

bashio::log.info "Starting Quit Smoking add-on..."
bashio::log.info "Ingress path: ${INGRESS_PATH}"
bashio::log.info "Addon slug: ${ADDON_SLUG}"
bashio::log.info "Data directory: ${DATA_DIR}"

cd /app
exec python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8099

#!/command/with-contenv bashio
set -e

# Read ingress entry from Supervisor
INGRESS_ENTRY=$(bashio::addon.ingress_entry)
export INGRESS_PATH="${INGRESS_ENTRY}"

# Read options
export NOTIFY_SERVICE=$(bashio::config 'notify_service')

# Data directory for persistence
export DATA_DIR="/config/quitsmoking"
mkdir -p "$DATA_DIR"

bashio::log.info "Starting Quit Smoking add-on..."
bashio::log.info "Ingress path: ${INGRESS_PATH}"
bashio::log.info "Notify service: ${NOTIFY_SERVICE}"
bashio::log.info "Data directory: ${DATA_DIR}"

cd /app
exec python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8099

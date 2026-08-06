ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.20

## Build frontend with native Node image
FROM node:20-alpine AS frontend-builder

WORKDIR /build
COPY frontend/package.json frontend/
RUN cd frontend && npm install
COPY frontend/ frontend/
RUN cd frontend && npm run build

## Runtime image
FROM ${BUILD_FROM}

ARG BUILD_VERSION=1.3.9

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64|armv7"

SHELL ["/bin/ash", "-o", "pipefail", "-c"]

# Install Python
RUN apk add --no-cache python3 py3-pip

# Install Python packages
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Copy application
WORKDIR /app
COPY backend/ /app/backend/
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist

# Copy run script
COPY run.sh /
RUN chmod +x /run.sh

CMD ["/run.sh"]

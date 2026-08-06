# Version Bump Checklist

When releasing a new version, update **all four** of these files:

| File | Field | Example |
|------|-------|---------|
| `quitsmoking/config.yaml` | `version:` | `version: 1.3.8` |
| `quitsmoking/build.yaml` | `args.BUILD_VERSION:` | `BUILD_VERSION: 1.3.8` |
| `quitsmoking/Dockerfile` | `ARG BUILD_VERSION=` | `ARG BUILD_VERSION=1.3.8` |
| `quitsmoking/frontend/src/App.svelte` | `<span class="app-version">` | `1.3.8` |

Also update:
- `quitsmoking/CHANGELOG.md` — add a new `## x.y.z` section at the top

## Why all four?

- `config.yaml` → HA Supervisor reads this to detect available updates in the repo
- `build.yaml` → HA builder passes this as a build arg when building the Docker image
- `Dockerfile` → The `io.hass.version` label (set from `BUILD_VERSION`) tells the Supervisor what version is *installed*. If this doesn't match config.yaml, HA shows "update available" but thinks it's already up to date after building.
- `App.svelte` → The version shown in the web UI header

If `config.yaml` is bumped but `Dockerfile`/`build.yaml` are not, HA will detect the update but fail to apply it (grays out, says "up to date").

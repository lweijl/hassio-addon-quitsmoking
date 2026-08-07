# Quit Smoking Add-on for Home Assistant

## Installation

1. **Add the repository to Home Assistant:**
   - Navigate to **Settings → Add-ons → Add-on Store**
   - Click the three-dot menu (top right) → **Repositories**
   - Add the repository URL: `https://github.com/lweijl/hassio-addon-quitsmoking`
   - Click **Add** and close the dialog

2. **Install the add-on:**
   - Find "Quit Smoking" in the add-on store
   - Click **Install** and wait for the build to complete

3. **Start the add-on:**
   - Go to the add-on's **Info** tab and click **Start**
   - Enable **Show in sidebar** for quick access

## Configuration

This add-on requires no configuration in the HA addon panel. All settings — including notification targets — are managed within the app's **Settings (⚙️)** tab.

### Notification Targets

To receive notifications on your phone or other devices:

1. Open the add-on via the sidebar panel
2. Navigate to the **⚙️ Settings** tab
3. Under **Notifications**, add your Home Assistant notify service names (e.g., `notify.mobile_app_yourphone`)
4. Use the **🔔 Send Test Notification** button to verify delivery

If no services are configured, notifications broadcast to all devices via the default `notify.notify` service.

## Usage

Once installed and started, access the add-on via the **Quit Smoking** panel in your Home Assistant sidebar (the lungs icon).

### Features

- **Schedule Tracking** — Configure your tapering schedule (interval-based or daily limits) and track each cigarette logged against your plan.
- **Progress Dashboard** — View daily, weekly, and overall statistics including cigarettes avoided, money saved, and health milestones.
- **Notifications** — Receive alerts when your interval elapses, daily reminders, milestone celebrations, and weekly progress summaries.
- **Data Persistence** — All data is stored in a SQLite database at `/config/quitsmoking/` and persists across add-on restarts and updates.

### Ingress

This add-on uses Home Assistant Ingress, meaning it is accessible directly through your HA interface without exposing additional ports. No external port configuration is needed.

## Data Storage

Data is stored at `/config/quitsmoking/` inside the Home Assistant config directory. This ensures your progress data:

- Survives add-on updates and reinstalls
- Can be included in Home Assistant backups
- Is accessible for manual export if needed

## Troubleshooting

- **Add-on won't start:** Check the add-on logs for error messages.
- **Notifications not working:** Open the ⚙️ Settings tab and verify your notify services are listed. Use the test button to confirm. Check that the service names match those in **Developer Tools → Services** (e.g., `notify.mobile_app_yourphone`).
- **Data loss after update:** Data is stored in the config directory and should persist. If you experience issues, check that the `/config/quitsmoking/` directory exists and has proper permissions.

## Support

For issues and feature requests, visit: https://github.com/lweijl/hassio-addon-quitsmoking/issues

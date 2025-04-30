# Official Dreo Smart Device Integration for Home Assistant

This is the official integration component developed and maintained by the Dreo engineering team for Home Assistant. It enables direct control and monitoring of Dreo smart fans through your Home Assistant installation.

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)

If you like Dreo products and want to support this integration, you can purchase our devices through this link: [Dreo Fans on Amazon](https://www.amazon.com/gp/search?ie=UTF8&tag=jeffsteinbok-20&linkCode=ur2&linkId=264bf9285db76a172f81bad93760d162&camp=1789&creative=9325&index=hpc&keywords=Dreo%20Smart%20Fan)

## Version Information

This integration offers two release channels:

1. **Beta Testing**: Pre-release versions available for early access to new features. These builds may contain bugs but provide the latest functionality.
2. **Stable Release**: Thoroughly tested versions recommended for regular users.

We recommend most users to use the stable releases for reliability, while beta versions are available for those interested in testing new features and providing early feedback.

We welcome you to subscribe to our GitHub repository to stay updated with our latest releases and announcements.

**Important Notice**: Dreo is currently working on becoming an official Home Assistant integration. In the near future, this integration will be available directly through the official Home Assistant channels. The current HACS plugin version is not considered stable. Once Dreo is integrated into the official Home Assistant repository, we recommend transitioning to the official integration.

## Interested in Contributing?

We welcome enthusiasts and hobbyists who are interested in contributing to the Dreo integration for Home Assistant. Your valuable contributions help improve this project for everyone. For more information on how to contribute, please check [Contributing](contributing.md).

## Table of Contents

- [Compatibility](#compatibility)
- [Installation](#installation)
- [Initial Configuration](#initial-configuration)
- [Debugging](#debugging)
- [Troubleshooting](#troubleshooting)
  - [If HomeAssistant Doesn't Show Your Device](#if-homeassistant-doesnt-show-your-device)
- [Adding New Products](#adding-new-products)

## Compatibility

Currently supported fan models are listed below.

### Fans

The following fans types are supported. Not all variants have been tested.

| Fan Type | Model Prefix(es) | Notes |
| -------- | ------------ | ------ |
| Tower Fans | DR-HTF | |

Models that have been specifically tested can be found below.

#### Tower Fans

- DR-HTF001S (Cruiser Pro T1 S)
- DR-HTF002S (Cruiser Pro T2 S)
- DR-HTF004S (Pilot Max S)
- DR-HTF005S (Pilot Pro S)
- DR-HTF005S-2 (Pilot Pro S v2)
- DR-HTF007S (Nomad One S)
- DR-HTF008S (Cruiser Pro T3 S)
- DR-HTF009S (Cruiser Pro T2S 2nd Gen)
- DR-HTF010S (MC710S)

Features for Tower Fans include:
- Power (true, false)
- Preset modes (Normal, Natural, Sleep, Auto)
- Set Speed (varies by model: 1-4, 1-6, 1-9, or 1-12)
- Oscillate (true, false)
- Attributes: `poweron`, `windtype`, `windlevel`, `shakehorizon`


## Installation

**Note**: Dreo integration is currently in the process of being added to HACS. At present, only manual installation is available.

### Manual Installation

1. Copy the `dreo` directory into your `/config/custom_components` directory in your Home Assistant installation.

2. Restart your Home Assistant instance to load the integration.

**Note about dependencies**: This integration has `hscloud` library as a dependency (version 1.0.6), which is specified in the manifest.json file. When you restart Home Assistant after adding the integration (including in Docker environments), the system will automatically install the required dependencies. You do not need to manually install dependencies in most cases.

If for some reason the automatic installation fails, you can manually install the dependency:

```bash
pip install hscloud==1.0.6
```

## Initial Configuration

> [!IMPORTANT]
> If you used the very early version of this that required editing `configuration.yaml`, you will need to do a one-time reconfiguration. Delete the configuration entries you added and then go through the configuration flow within HomeAssistant.

### Adding the Dreo Integration to Home Assistant

Follow these detailed steps to configure the Dreo integration after installation:

1. **Access Home Assistant Settings**:
   - Open your Home Assistant web interface
   - Click on the gear icon (⚙️) in the lower left sidebar to access **Settings**

2. **Navigate to Integrations**:
   - In the Settings menu, find and click on **Devices & Services**
   - You'll see a list of your currently configured integrations

3. **Add Dreo Integration**:
   - Look for the blue **+ ADD INTEGRATION** button in the bottom right corner of the screen
   - Click this button to open the integration selection dialog

4. **Find and Select Dreo**:
   - In the search box that appears, type `Dreo`
   - The Dreo integration should appear in the search results
   - Click on the Dreo integration to select it

5. **Enter Your Credentials**:
   - You will be prompted to enter your Dreo account credentials
   - Enter the same username (email) and password you use to log in to the Dreo mobile app
   - Click **Submit** to continue

6. **Complete the Setup**:
   - If your credentials are correct, Home Assistant will connect to the Dreo cloud service
   - Your Dreo devices will be automatically discovered and added to Home Assistant
   - You can now control your Dreo devices from the Home Assistant interface

After completion, your Dreo devices will appear in the Home Assistant dashboard where you can control them.

## Debugging

Use the **Diagnostics** feature in HomeAssistant to get diagnostics from the integration. Sensitive info should be redacted automatically.

In your `configuration.yaml` file, add this:

```
logger:
    logs:
        dreo: debug
```

Now restart HomeAssistant. Perform the actions needed to generate some debugging info.

### Collecting Debug Information

When troubleshooting issues with the Dreo integration, you may need to collect debug logs or diagnostic files. These files help developers understand what's happening with your system.

#### Option 1: Download Full Home Assistant Logs

These logs contain detailed information about all Home Assistant operations, including the Dreo integration.

**Steps to download full logs:**
1. Open Home Assistant web interface
2. Click on **Settings** in the left sidebar
3. Select **System** from the menu
4. Click on the **Logs** tab
5. Look for the **Download full log** button at the bottom right
6. Save the log file to your computer

> **Important:** Full logs may contain sensitive information about your Home Assistant setup and connected devices. Always review logs before sharing them with others.

#### Option 2: Download Dreo-specific Diagnostics

For issues specifically related to the Dreo integration, downloading diagnostics provides focused information.

**Steps to download diagnostics:**
1. Open Home Assistant web interface
2. Click on **Settings** in the left sidebar
3. Select **Devices & services**
4. Find and click on **Dreo** integration
5. Click the three-dot menu (⋮) in the top-right corner of the Dreo card
6. Select **Download diagnostics**
7. Save the JSON file to your computer

These diagnostics files are specifically designed to help troubleshoot the Dreo integration while automatically redacting sensitive information.

## Adding New products

Don't see your model listed above? Create an [issue](https://github.com/dreo-team/hacs-dreo/issues) and I'll add it.

**Please make sure to include:**

- Model - in the format above
- Number of speeds the fan supports (not including "off")
- Does the fan support oscillating?
- What preset modes are supported?
- Is temperature supported?

Depending on answers, I may reach out and need you to pull some debug logs.

## Troubleshooting

### If HomeAssistant Doesn't Show Your Device

If you've installed the Dreo integration but your devices don't appear in HomeAssistant, follow these troubleshooting steps:

#### Step 1: Verify Basic Setup
- **Check Wi-Fi Connection**: Ensure your Dreo device is properly connected to your home Wi-Fi network
- **Test Mobile App**: Confirm the device works correctly in the Dreo mobile app
- **Verify Account**: Make sure you're using the exact same account credentials in HomeAssistant as in your Dreo mobile app
- **Restart Services**: Try restarting both your Dreo device and HomeAssistant instance

#### Step 2: Check Integration Installation
- Confirm the integration was installed properly:
  1. Go to **Settings** → **Devices & services**
  2. Look for "Dreo" in the list of integrations
  3. If not found, try adding it again following the [Initial Configuration](#initial-configuration) steps

#### Step 3: Enable Debugging
1. Add debug logging as described in the [Debugging](#debugging) section
2. Restart HomeAssistant
3. Try using your Dreo device through the mobile app to generate activity
4. Check logs for any information about your device

#### Step 4: Determine Support Status
Look for specific messages in your logs that indicate whether your device model is supported:

- If you see log entries related to your device but it still doesn't appear in the interface, there might be a connection or authentication issue
- If you see this message, your device model is detected but not yet supported:
  ```
  2023-06-29 01:02:25,312 - dreo - DEBUG - Received products for current unsupported device. SN: XXX341964289-77f2977b24191a4a:001:0000000000b
  ```

#### Reporting Unsupported Devices
If your device is not yet supported:

1. Collect the following information:
   - Your exact device model number (found on the device or packaging)
   - The device's firmware version (if available in the Dreo app)
   - Diagnostic information using [Option 2](#option-2-download-dreo-specific-diagnostics) above
   - Screenshots of the device in your Dreo mobile app (if possible)

2. [Create an issue](https://github.com/dreo-team/hacs-dreo/issues/new) on GitHub with all the collected information

> **Note:** Our team is actively expanding device support. When reporting unsupported devices, please provide as much detail as possible to help us prioritize and implement support for your model in future updates.

# Official Dreo Smart Device Integration for Home Assistant

This is the official integration component developed and maintained by the Dreo engineering team for Home Assistant. It enables direct control and monitoring of Dreo smart fans through your Home Assistant installation.

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)

If you like Dreo products and want to support this integration, you can purchase our devices through this link: [Dreo Fans on Amazon](https://www.amazon.com/gp/search?ie=UTF8&tag=jeffsteinbok-20&linkCode=ur2&linkId=264bf9285db76a172f81bad93760d162&camp=1789&creative=9325&index=hpc&keywords=Dreo%20Smart%20Fan)

## Version Information

This integration offers two release channels:

1. **Beta Testing**: Pre-release versions available for early access to new features. These builds may contain bugs but provide the latest functionality.
2. **Stable Release**: Thoroughly tested versions recommended for regular users.

We recommend most users to use the stable releases for reliability, while beta versions are available for those interested in testing new features and providing early feedback.

**Important Notice**: Dreo is currently working on becoming an official Home Assistant integration. In the near future, this integration will be available directly through the official Home Assistant channels. The current HACS plugin version is not considered stable. Once Dreo is integrated into the official Home Assistant repository, we recommend transitioning to the official integration.

## Interested in Contributing?

We welcome enthusiasts and hobbyists who are interested in contributing to the Dreo integration for Home Assistant. Your valuable contributions help improve this project for everyone. For more information on how to contribute, please check [Contributing](contributing.md).

## Table of Contents

- [Compatibility](#compatibility)
- [Installation](#installation)
- [Debugging](#debugging)
- [Adding new Fans](#adding-new-fans)
- [To Do](#to-do)

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

Copy the `dreo` directory into your `/config/custom_components` directory, then restart your HomeAssistant Core.

## Initial Configuration

> [!IMPORTANT]
> If you used the very early version of this that required editing `configuration.yaml`, you will need to do a one-time reconfiguration. Delete the configuration entries you added and then go through the configuration flow within HomeAssistant.

1. In HA, open `Settings`
2. Click `Devices & services`
3. Click `Add integration` (blue button at the bottom right of the screen)
4. Search `Dreo` and select it
5. Enter your `Dreo` username & password (same login you use on the Dreo app)

## Debugging

Use the **Diagnostics** feature in HomeAssistant to get diagnostics from the integration. Sensitive info should be redacted automatically.

In your `configuration.yaml` file, add this:

```
logger:
    logs:
        dreo: debug
```

Now restart HomeAssistant. Perform the actions needed to generate some debugging info.

##### Download the full logs

Note that these may contain sensitive information, so do always check before sending them to someone.

1. In HA, open `Settings`
2. Click `System`
3. Click `Logs`
4. Click `Download full log`

##### Download diagnostics (`.json` file)

1. In HA, open `Settings`
2. Click `Device & services`
3. Click `Dreo`
4. Click on the three-dot hamburger menu (next to `Configure`) and click `Download diagnostics`.


## Adding New Fans

Don't see your model listed above? Create an [issue](https://github.com/JeffSteinbok/hass-dreo/issues) and I'll add it.

**Please make sure to include:**

- Model - in the format above
- Number of speeds the fan supports (not including "off")
- Does the fan support oscillating?
- What preset modes are supported?
- Is temperature supported?

Depending on answers, I may reach out and need you to pull some debug logs.

### Debug Logs for New Fans

1. Enable [debugging](#debugging)
2. Go to the Dreo app on your mobile device and perform the various commands you want to be able to use in HA. Dreo servers will send updates to the WebSocket that the integration is listening on.
3. Go look at the logs, you should see something like the below. Create an [issue](https://github.com/JeffSteinbok/hass-dreo/issues) and include the lines related to `pydreo`, the diagnostics `json` file, and if possible, what actions you performed in the app.

```
2023-06-29 01:02:25,312 - pydreo - DEBUG - Received message for unknown or unsupported device. SN: XXX341964289-77f2977b24191a4a:001:0000000000b
2023-06-29 01:02:25,312 - pydreo - DEBUG - Message: {'method': 'control-report', 'devicesn': 'XXX0393341964289-77f2977b24191a4a:001:0000000000b', 'messageid': 'bdf23a1f-c8e1-4e22-8ad3-dc0cd5dfdc7c', 'timestamp': 1688025746, 'reported': {'windtype': 1}}
```
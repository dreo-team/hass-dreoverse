# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Lint
```bash
scripts/lint        # runs ruff format + ruff check --fix
```

### Dev environment
```bash
scripts/setup       # pip install -r requirements.txt (installs ruff)
scripts/develop     # launches a local Home Assistant instance with the integration loaded
```
The `scripts/develop` script sets `PYTHONPATH` to include `custom_components/` and runs `hass --config ./config --debug`. The `config/configuration.yaml` in this repo is pre-configured for local development.

There is no automated test suite. Manual testing is done by running the integration inside Home Assistant and observing logs/behavior.

## Architecture

### Integration entry point (`__init__.py`)
On `async_setup_entry`, the integration:
1. Logs in via `DreoClient` (from the `pydreo-cloud` library) using stored credentials.
2. Calls `client.get_devices()` which returns a list of device dicts, each containing device metadata **and** a `"config"` key holding per-model capability configuration.
3. Creates one `DreoDataUpdateCoordinator` per device, seeds it with the initial state from the device list, then forwards setup to all platform modules.

### Config-driven entity creation
Device capability is entirely server-driven: each device dict contains a `"config"` section (accessed via `DreoEntityConfigSpec.TOP_CONFIG`) that declares what Home Assistant entities and features the device supports. Platform modules check `entitySupports` (a list of `Platform` values inside the config) before creating any entity. This avoids hardcoding per-model logic in the integration.

### Coordinator & data classes (`coordinator.py`)
`DreoDataUpdateCoordinator` wraps HA's `DataUpdateCoordinator` with a 15-second poll interval. It selects a `data_processor` static method based on `device_type` (a `DreoDeviceType` string enum). Each typed `DeviceData` class (e.g. `DreoFanDeviceData`, `DreoHacDeviceData`) holds parsed state fields and exposes a `process_*` static method that translates the raw API `state` dict into typed attributes using `DreoDirective` string enum keys.

### Base entity (`entity.py`)
`DreoEntity` extends `CoordinatorEntity`. All platform entities inherit from it. `async_send_command_and_update` is the canonical way to send a directive to the device: it calls `client.update_status(device_id, **kwargs)`, then triggers a coordinator refresh. Error translation keys come from `DreoErrorCode`.

### Platform modules
Each HA platform (`fan.py`, `climate.py`, `humidifier.py`, `light.py`, `number.py`, `select.py`, `sensor.py`, `switch.py`) has an `async_setup_entry` that iterates `config_entry.runtime_data.devices`, checks device type and `entitySupports`, looks up the coordinator by `deviceSn`, and instantiates typed entity subclasses.

### Status dependency (`status_dependency.py`)
`DreotStatusDependency` is a callable that evaluates whether a select/number entity should be available based on the current device state. It reads `status_available_dependencies` from the model config — a list of `{directive_name, dependency_values, condition}` rules evaluated with AND/OR logic against the current `DeviceData` object.

### Key enums in `const.py`
- `DreoDeviceType` — device type strings from the API (`"fan"`, `"circulation_fan"`, `"hac"`, etc.)
- `DreoDirective` — API state field names (`"power_switch"`, `"mode"`, `"speed"`, etc.)
- `DreoEntityConfigSpec` — keys inside the per-model config dict
- `DreoFeatureSpec` — keys inside config sub-sections (e.g. `"speed_range"`, `"preset_modes"`)
- `DreoErrorCode` — translation keys for HA error messages (defined in `translations/en.json`)

### Adding support for a new device type
1. Add a new value to `DreoDeviceType` in `const.py`.
2. Create a `Dreo<Type>DeviceData` class in `coordinator.py` with a `process_<type>_data` static method.
3. Register the processor in `DreoDataUpdateCoordinator.__init__` under the new device type.
4. Add entity classes to the relevant platform files and gate them behind the correct `device_type` check or `entitySupports` flag.

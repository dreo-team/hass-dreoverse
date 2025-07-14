# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-07-13

### 🚀 Major Updates

#### Architecture Improvements
- **Core Architecture Refactoring**: Comprehensive optimization of the underlying `pydreo` package, enhancing overall performance and stability
- **Dependency Management Optimization**: Updated `pydreo-cloud` dependency package to ensure better compatibility and feature support
- **Communication Protocol Enhancement**: Optimized communication mechanism with Dreo cloud services, improving response speed and reliability

#### Code Optimization
- **Code Refactoring**: Comprehensive code optimization to improve code quality and maintainability
- **Performance Enhancement**: Optimized device state update mechanism to reduce unnecessary API calls
- **Error Handling**: Enhanced exception handling logic to improve system stability and user experience

### 🆕 New Device Support

#### Circulation Fan Devices
- **511S/611S (DR-HAF001S)**: 4-speed control, preset modes, oscillation
- **PolyFan S (DR-HAF003S)**: 8-speed control, multi-direction oscillation
- **714S/814S (DR-HAF004S)**: 9-speed control, pan-tilt oscillation
- **Falcon S (DR-HPF001S)**: 8-speed control, basic oscillation
- **Falcon X (DR-HPF002S)**: 8-speed control, directional oscillation
- **CF714S (DR-HPF004S)**: 9-speed control, directional oscillation
- **PolyFan Pro S (DR-HPF005S)**: 10-speed control, directional oscillation
- **PF707S (DR-HPF007S)**: 10-speed control, smart follow mode
- **PolyFan 508S (DR-HPF008S)**: 9-speed control, ambient lighting
- **Falcon X (DR-HPF010S)**: 8-speed control, directional oscillation

#### Air Conditioning Devices
- **AC516S (DR-HAC006S)**: Complete climate control with temperature (64-86°F), humidity (40-70%), multiple HVAC modes (Cool/Dry/Fan Only)

#### Ceiling Fan Devices
- **CLF513S (DR-HCF003S)**: 12-speed fan control, integrated lighting with brightness and color temperature adjustment

#### Humidifier Devices
- **ec02 (DR-HEC002S)**: Humidity control (40-90%), oscillation, multiple operating modes (Normal/Auto/Sleep/Natural)

### 🔧 Technical Improvements

#### Enhanced Features
- **Device Discovery**: Improved automatic device discovery mechanism to support automatic recognition of more device types
- **State Synchronization**: Optimized device state synchronization logic to ensure consistency between Home Assistant and actual devices
- **Configuration Process**: Simplified device configuration process to improve user experience

#### Bug Fixes
- Fixed connection issues for certain devices during network instability
- Resolved device state update delays
- Fixed device model identification errors for some models

### 🛠️ Breaking Changes
- This version includes major architectural adjustments - users are advised to backup configurations before upgrading
- Some legacy configurations may need to be reconfigured

### 📋 Compatibility
- Supports Home Assistant 2024.12.0 and above
- Requires Python 3.11 or higher
- Compatible with HACS installation

### 🙏 Acknowledgments
Special thanks to community users for their feedback and testing, particularly those who provided device testing and debugging support.

---

## [1.0.0] - 2024-XX-XX

### 🚀 Initial Release
- Initial release of Dreo smart device Home Assistant integration
- Support for basic tower fan device control functions
- Provides device discovery and configuration functionality 
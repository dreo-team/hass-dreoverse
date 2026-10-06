# New DR-HCF002S RGBIC support

This fork preserves the official `dreo` domain, existing config-entry data,
device identifiers and entity unique IDs. Fan and main-light control continue
through the official Open API. The existing RGB light uses the mobile API only
when the exact DR-HCF002S device reports RGBIC capability and its effect catalog
contains Constant. Exact-model mobile initialization or capability failure leaves
only RGB unavailable; it never enables legacy RGB commands or prevents fan/main
setup. Reload the integration to requalify a failed mobile initialization.
Other models retain their existing behavior.

The existing config flow stores the API's MD5 password credential; mobile
authentication uses those bytes without hashing again. Home Assistant's maintained
aiohttp session owns transport; no requirement or background controller is added.
Credentials and tokens remain private in memory and managed config-entry custody.
Communication errors contain fixed messages rather than raw server payloads.

Effect IDs, names, reference IDs and layouts come from the current device's
catalog. Constant color modifies only layouts with wholeColorList, preserving
all segmented colorList values. RGBIC brightness uses 1–100. RGB power/brightness
commands contain only atmon and atmbri; neither fan/main-light nor the
whole-device power gate is written. A previously closed whole-device gate can
therefore prevent successful RGB activation rather than starting another load.

Commands are serialized, sent once and checked through fresh catalog and mobile
state reads. Server acknowledgement is acceptance only. A changed native effect
ID must match an independently read catalog record before publishing effect or
color. Mismatched or unavailable readback raises an error; caller intent never
becomes reported state. A failed RGB read marks the RGB light unavailable while
retaining the separately observed fan/main-light data.

The RGBIC effect protocol follows
[community PR927](https://github.com/JeffSteinbok/hass-dreo/pull/927), immutable
commit a6461fe6045f8f2f84a0561fb550af6aaebfb6ff. That proposed change documents
DR-HCF002S/CF712S hardware with module firmware 1.0.49 and MCU firmware 2.1.39.
This fork adds independent readback instead of optimistic requested-color state.
The original MIT license remains included.

Run native tests with `python3 -m unittest discover -s tests -v`. Tests use
synthetic credentials and protocol-shaped HTTP/WebSocket sessions; they never
access a household account. These tests do not establish live device support.
Activation of changed integration code requires a qualified Core restart and
protected source/config-entry recovery material. Preserve existing entries and
registries during deployment and rollback; do not reenroll or recreate entities.

# ESP32-C6 Firmware Client (Arduino)

This firmware connects an ESP32-C6 to the Python command server and polls commands for one specific device.

## Libraries
Install these in Arduino IDE Library Manager:
- `ArduinoJson` by Benoit Blanchon

`WiFi` and `HTTPClient` come from ESP32 board package.

## Arduino IDE Setup
1. Install ESP32 board package by Espressif.
2. Select board: an ESP32-C6 board variant matching your hardware.
3. Open `firmware/esp32_c6_client/esp32_c6_client.ino`.
4. Edit WiFi and server values.
5. Set `DEVICE_ID` and `DEVICE_TOKEN` unique per board.
6. Upload.

## Two Device Example
For board A:
- `DEVICE_ID = "esp32-a"`
- `DEVICE_TOKEN = "token-device-a"`

For board B:
- `DEVICE_ID = "esp32-b"`
- `DEVICE_TOKEN = "token-device-b"`

Both can point to the same `SERVER_BASE_URL`.

## Command Format
Current sketch handles:
- `relay:on` or `led:on`
- `relay:off` or `led:off`

Unknown commands are logged on Serial.

## Notes
- Your server URL should be reachable from ESP32 over WiFi (same LAN or routed network).
- If `ACTUATOR_PIN` is `-1`, command handling is log-only.
- Serial monitor speed: `115200`.

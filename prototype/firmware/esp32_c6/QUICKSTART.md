# Kywo Firmware - Quick Start Guide

## 1. Prerequisites

- **PlatformIO**: Install via VSCode or CLI
- **ESP32-C6 board**: Connected via USB
- **Server running**: Kywo server on local network

## 2. Configuration (5 minutes)

### WiFi Setup
Open `esp32_c6.ino` and update lines 28-29:
```cpp
const char* WIFI_SSID     = "YourWiFiName";
const char* WIFI_PASSWORD = "YourPassword";
```

### Server Setup
Update lines 32-33 with your server IP:
```cpp
const char* SERVER_URL = "http://192.168.1.100:8000";
const char* API_KEY    = "super-secret-admin";
```

**Important**: API key must match the `ADMIN_API_KEY` environment variable on your server.

## 3. Hardware Connections

Connect your ESP32-C6 outputs:

| GPIO | Purpose | Connection |
|------|---------|------------|
| 15 | Digital Output 1 | Your load/relay/LED |
| 16 | Digital Output 2 | Your load/relay/LED |
| 17 | Digital Output 3 | Your load/relay/LED |
| 18 | PWM Output | Motor/LED/analog device |

**Note**: Add appropriate drivers (MOSFETs, relays) for loads >20mA.

## 4. Flash Firmware

### Using PlatformIO CLI
```bash
cd prototype/firmware/esp32_c6
pio run --target upload
pio device monitor
```

### Using VSCode
1. Open folder in PlatformIO
2. Click "Upload" button in bottom toolbar
3. Click "Serial Monitor" to view output

## 5. Verify Connection

### Serial Monitor Output
You should see:
```
[wifi] Connected! IP: 192.168.1.42, Channel: 1
[server] Registration successful
[boot] System ready. Waiting for configuration...
```

### Web Dashboard
1. Open server URL in browser (e.g., `http://192.168.1.100:8000`)
2. Click "Refresh" button
3. Your device (e.g., `ESP32-C6-A3B4`) should appear in list with green dot

## 6. Deploy Configuration

### Create Sequence
1. Select your device from dropdown
2. Build state sequence (Digital 1/2/3 + PWM + Duration)
3. Click "→ Deploy to Device"

### Set Grandmaster (First Device Only)
1. Select device from dropdown
2. Click "★ Set as Grandmaster"
3. Device will begin broadcasting ESP-NOW sync

Wait ~2 seconds for other devices to synchronize.

## 7. Add More Devices

Repeat steps 2-6 for each additional ESP32-C6:
- Each device gets unique ID from MAC address
- Only ONE device should be Grandmaster
- All devices must be on same WiFi channel

## 8. Troubleshooting

### Device offline (gray dot)
- Check WiFi credentials
- Verify device powered on
- Check serial monitor for errors

### Device online but not synced
- Ensure one device is Grandmaster (★ badge)
- Check all devices on same WiFi channel
- Serial should show: `[ESP-NOW] Clock synchronized...`

### Outputs not working
- Verify GPIO connections
- Check sequence has non-zero durations
- Test with simple 2-state sequence first

## Pin Diagram (ESP32-C6-DevKitC-1)

```
                  ESP32-C6
              ┌──────────────┐
     USB-C ───┤              ├─── GND
              │              │
     3.3V ────┤              ├─── GPIO 15 (Digital 1)
              │              │
     GND  ────┤              ├─── GPIO 16 (Digital 2)
              │              │
              │              ├─── GPIO 17 (Digital 3)
              │              │
              │              ├─── GPIO 18 (PWM)
              │              │
              └──────────────┘
```

## Architecture Summary

```
┌─────────────┐    HTTP/TCP (1s poll)    ┌──────────────┐
│  Kywo       │ ◄───────────────────────► │  ESP32-C6    │
│  Server     │                           │  Device 1    │
└─────────────┘                           │ (Grandmaster)│
                                          └──────────────┘
                                                 │
                                          ESP-NOW Broadcast
                                           (2s interval)
                                                 │
                                                 ▼
                                          ┌──────────────┐
                                          │  ESP32-C6    │
                                          │  Device 2    │
                                          │  (Follower)  │
                                          └──────────────┘
                                                 │
                                                 │
                                                 ▼
                                          ┌──────────────┐
                                          │  ESP32-C6    │
                                          │  Device 3    │
                                          │  (Follower)  │
                                          └──────────────┘
```

- **Server**: Configuration management, device registry
- **Grandmaster**: Broadcasts time via ESP-NOW
- **Followers**: Sync to Grandmaster, execute sequences

## Next Steps

- Test synchronization with 2+ devices
- Measure drift with hardware observer (see `poc/tests/`)
- Adjust PWM frequency if needed (line 44 in .ino file)
- Deploy to production hardware

## Support

For issues, check:
1. Serial monitor output (`pio device monitor`)
2. Server event log (bottom of web dashboard)
3. POC test results (`poc/test_results/RESULTS_ANALYSIS.md`)

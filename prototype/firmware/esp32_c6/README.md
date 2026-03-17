# Kywo Production Firmware - ESP32-C6

Production firmware for distributed ESP32 control system with ESP-NOW clock synchronization.

## Hardware Configuration

### Target Board
- **ESP32-C6-DevKitC-1**
- **Framework**: Arduino
- **Firmware Version**: 3.0.0-Production

### Pin Assignment (Fixed)

| Output | GPIO Pin | Type | Description |
|--------|----------|------|-------------|
| Digital Output 1 | GPIO 15 | Digital | Binary output (HIGH/LOW) |
| Digital Output 2 | GPIO 16 | Digital | Binary output (HIGH/LOW) |
| Digital Output 3 | GPIO 17 | Digital | Binary output (HIGH/LOW) |
| PWM Output | GPIO 18 | PWM | Variable duty cycle (0-255) |

**PWM Specifications:**
- LEDC Channel: 0
- Frequency: 5 kHz
- Resolution: 8-bit (0-255)

## System Architecture

### Communication Layers

1. **HTTP/TCP Configuration Layer**
   - **Purpose**: Configuration polling from server
   - **Interval**: 1000ms
   - **Endpoint**: `GET /devices/{device_id}/config`
   - **Payload**: Sequence configuration + master role assignment

2. **ESP-NOW Synchronization Layer**
   - **Purpose**: Microsecond-precision clock synchronization
   - **Interval**: 2000ms broadcast (master only)
   - **Latency Compensation**: 1054µs (measured median)
   - **Target Drift**: <50µs mean

### Execution Model

- **FreeRTOS Architecture**: Dual-core task distribution
  - **Core 0**: ESP-NOW sync broadcast task (Priority 3)
  - **Core 1**: State machine execution engine (Highest priority)

- **Thread-Safe Double Buffering**: Configuration updates don't interrupt execution
- **Intelligent Delay Strategy**:
  - Yields to scheduler for waits >2ms
  - Busy-waits for <2ms transitions (minimal jitter)

### State Machine

Each device independently executes a state sequence synchronized via ESP-NOW:

```c
struct StateNode {
  bool digital_out1;     // GPIO 15 state
  bool digital_out2;     // GPIO 16 state
  bool digital_out3;     // GPIO 17 state
  uint8_t pwm_out;       // GPIO 18 duty cycle (0-255)
  uint32_t duration_ms;  // State duration
};
```

## Configuration

### Step 1: Update WiFi Credentials

Edit `esp32_c6.ino` lines 28-29:

```cpp
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
```

### Step 2: Update Server Configuration

Edit `esp32_c6.ino` lines 32-33:

```cpp
const char* SERVER_URL = "http://192.168.1.100:8000";  // Your server IP
const char* API_KEY    = "super-secret-admin";          // Match server key
```

### Step 3: Verify Pin Assignment

If your hardware uses different GPIO pins, update lines 38-41:

```cpp
static const int PIN_DIGITAL_OUT1 = 15;
static const int PIN_DIGITAL_OUT2 = 16;
static const int PIN_DIGITAL_OUT3 = 17;
static const int PIN_PWM_OUT      = 18;
```

## Building and Flashing

### Requirements
- **PlatformIO**: Install via VSCode extension or CLI
- **USB Cable**: For flashing firmware to ESP32

### Build Commands

```bash
# Build firmware
pio run

# Flash to device
pio run --target upload

# Open serial monitor
pio device monitor

# Build + Flash + Monitor (one command)
pio run --target upload && pio device monitor
```

### First Boot Sequence

1. Device connects to WiFi
2. Generates unique ID from MAC: `ESP32-C6-XXXX`
3. Registers with server via HTTP POST
4. Initializes ESP-NOW (default: follower mode)
5. Creates FreeRTOS tasks
6. Begins polling for configuration

## Expected Serial Output

```
========================================
Kywo - Production Firmware v3.0.0
Distributed ESP32 Control System
========================================

[hw] Hardware initialized:
  Digital outputs: GPIO 15, 16, 17
  PWM output: GPIO 18 (Channel 0, 5000 Hz)
[wifi] Connecting to MyWiFi
[wifi] Connected! IP: 192.168.1.42, Channel: 1
[boot] Device ID: ESP32-C6-A3B4
[server] Registering as ESP32-C6-A3B4...
[server] Registration successful
[ESP-NOW] Initialized successfully
[ESP-NOW] Role: FOLLOWER (listening on channel 1)
[boot] FreeRTOS tasks created:
  - ESP-NOW sync task (Core 0, Priority 3)
  - State machine engine (Core 1, Highest Priority)

[boot] System ready. Waiting for configuration...

[config] New configuration detected. Parsing...
[config] SUCCESS! 2 states, 2000 ms total, PWM enabled
[ESP-NOW] Clock synchronized to Grandmaster! Offset: -1234 µs
[status] Running: 2 states, Master: NO
```

## Network Protocol Details

### Device Registration
```http
POST /devices/register
Content-Type: application/json

{
  "device_id": "ESP32-C6-A3B4",
  "device_token": "kywo-device-token",
  "firmware_version": "3.0.0-Production",
  "wifi_channel": 1
}
```

### Configuration Polling
```http
GET /devices/ESP32-C6-A3B4/config
x-api-key: super-secret-admin

Response:
{
  "sequence": [
    {
      "digital_out1": true,
      "digital_out2": false,
      "digital_out3": false,
      "pwm_out": 128,
      "duration_ms": 1000
    },
    {
      "digital_out1": false,
      "digital_out2": true,
      "digital_out3": true,
      "pwm_out": 255,
      "duration_ms": 1000
    }
  ],
  "is_master": false,
  "master_channel": 1
}
```

### ESP-NOW Sync Message
```c
struct sync_message_t {
  uint32_t magic;           // 0xA2C22026
  int64_t master_time_us;   // Grandmaster timestamp (µs)
};
```

## Troubleshooting

### Issue: Device not connecting to WiFi
- Verify SSID and password in firmware
- Check WiFi is 2.4GHz (ESP32-C6 doesn't support 5GHz)
- Serial output shows connection attempts

### Issue: Device not appearing in web dashboard
- Verify server URL and API key match
- Check device successfully registered (serial: `[server] Registration successful`)
- Refresh device list in web UI

### Issue: "Waiting for ESP-NOW clock sync..."
- Ensure at least one device is configured as Grandmaster via web UI
- Check all devices are on the same WiFi channel
- Serial should show: `[ESP-NOW] Clock synchronized to Grandmaster!`

### Issue: State transitions not synchronized
- Verify all devices show clock sync in serial output
- Check network latency (should be <5ms for WiFi)
- Ensure no WiFi interference on the channel

### Issue: PWM output not working
- Verify GPIO 18 is connected correctly
- Check PWM duty cycle is not 0 in sequence
- Test with simple sequence (pwm_out: 128 for 50% duty cycle)

## Performance Targets

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Clock sync drift | <50µs mean | Hardware observer (arch2_sync_test) |
| State transition jitter | <10µs | Oscilloscope on GPIO outputs |
| Config update latency | <1.5s | HTTP polling interval + parsing |
| ESP-NOW broadcast latency | ~1ms | Median transmission time |

## Firmware Architecture Improvements over POC

1. **Fixed Hardware Configuration**: Eliminates dynamic pin mapping overhead
2. **PWM Support**: LEDC peripheral for smooth analog output
3. **Dual-Core Optimization**: Network I/O isolated from timing-critical execution
4. **Enhanced Comments**: Production-ready documentation
5. **Updated Endpoints**: Uses simplified `/devices/` API (not `/arch2/devices/`)
6. **Version Tracking**: Semantic versioning for compatibility management

## License

Part of the Kywo Distributed Control System.  
See repository root for license information.

## Version History

- **3.0.0-Production** (March 17, 2026)
  - Production release based on POC testing
  - Fixed configuration: 3 digital + 1 PWM output
  - Improved state machine execution engine
  - Updated API endpoints for simplified server architecture

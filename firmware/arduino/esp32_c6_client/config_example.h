#pragma once

// Copy these values into esp32_c6_client.ino or adapt the sketch to include this file.

#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// Use your PC local network IP where FastAPI server runs.
#define SERVER_BASE_URL "http://192.168.1.100:8000"

// Unique values per board.
#define DEVICE_ID "esp32-a"
#define DEVICE_TOKEN "token-device-a"
#define FIRMWARE_VERSION "1.0.0"

// Set to your relay/LED pin. Use -1 to disable GPIO control.
#define ACTUATOR_PIN -1

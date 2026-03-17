/*
 * Kywo Firmware - Configuration Template
 * 
 * Instructions:
 * 1. Copy this file to 'config.h'
 * 2. Update with your WiFi and server details
 * 3. Add 'config.h' to .gitignore to keep credentials private
 * 
 * Note: Do NOT commit config.h to version control
 */

#ifndef CONFIG_H
#define CONFIG_H

// ==========================================
// WIFI CONFIGURATION
// ==========================================
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// ==========================================
// SERVER CONFIGURATION
// ==========================================
const char* SERVER_URL = "http://192.168.1.100:8000";  // Update with your server IP
const char* API_KEY    = "super-secret-admin";          // Must match server ADMIN_API_KEY

// ==========================================
// HARDWARE PIN CONFIGURATION (Optional)
// ==========================================
// Uncomment and modify if using different GPIO pins

// #define PIN_DIGITAL_OUT1 15
// #define PIN_DIGITAL_OUT2 16
// #define PIN_DIGITAL_OUT3 17
// #define PIN_PWM_OUT      18

// ==========================================
// PWM CONFIGURATION (Optional)
// ==========================================
// Uncomment and modify if using different PWM settings

// #define PWM_CHANNEL      0
// #define PWM_FREQUENCY    5000
// #define PWM_RESOLUTION   8

#endif // CONFIG_H

#include <Arduino.h>
#include "driver/gpio.h"

// Pin connected to the Edge ESP32's Actuator Pin (e.g., GPIO 15)
static const gpio_num_t MEASURE_PIN = GPIO_NUM_4; // Change if needed

// Trigger bytes from the server
static const uint8_t TRIG_EXPECT_HIGH = 'H';
static const uint8_t TRIG_EXPECT_LOW  = 'L';

void setup() {
  Serial.begin(2000000); 
  
  // Use native ESP-IDF driver for initialization instead of Arduino wrappers
  gpio_set_direction(MEASURE_PIN, GPIO_MODE_INPUT);
  gpio_set_pull_mode(MEASURE_PIN, GPIO_PULLDOWN_ONLY);

  while (!Serial) { delay(10); }
  
  Serial.println("\n[observer] Hardware Latency Observer Ready");
  Serial.println("[observer] Mode: Ultra-Low Latency Native Register Polling");
  Serial.println("[observer] Waiting for trigger commands ('H' or 'L')...");
}

void loop() {
  if (Serial.available() > 0) {
    uint8_t cmd = Serial.read();

    if (cmd == TRIG_EXPECT_HIGH || cmd == TRIG_EXPECT_LOW) {
      // 1. Mark start time the nanosecond the serial command arrives
      uint32_t t0 = micros();
      
      uint32_t targetState = (cmd == TRIG_EXPECT_HIGH) ? 1 : 0;
      uint32_t t1 = 0;
      bool timeout = false;

      // ┌──────────────────────────────────────────────────────────────────┐
      // │  ULTRA LOW LATENCY POLLING LOOP                                  │
      // │  - Bypasses heavy Arduino digitalRead()                          │
      // │  - Bypasses 1.5µs Interrupt Context Switch overhead              │
      // │  - Reads straight from the silicon register in ~1 clock cycle    │
      // └──────────────────────────────────────────────────────────────────┘
      while (gpio_get_level(MEASURE_PIN) != targetState) {
        // Timeout check limits to 2 seconds so we don't lock forever
        if (micros() - t0 > 2000000) { 
          timeout = true;
          break;
        }
      }

      // 3. Mark end time the instant the while-loop breaks
      t1 = micros();

      // 4. Report back to server
      if (timeout) {
        Serial.println("TIMEOUT");
      } else {
        uint32_t latency_us = t1 - t0;
        Serial.printf("%lu\n", latency_us);
      }
    }
  }
}

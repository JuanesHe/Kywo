#include <Arduino.h>

// ==========================================
// CONFIGURATION
// ==========================================
// Pin connected to Device A (Edge Node 1) Output Pin
static const int PIN_DEVICE_A = 4;

// Pin connected to Device B (Edge Node 2) Output Pin
static const int PIN_DEVICE_B = 5;

// ==========================================
// VOLATILE TIMESTAMP REGISTERS
// ==========================================
// Using internal ESP timer which runs natively in microsecond precision
volatile int64_t lastRisingTempA = 0;
volatile int64_t lastRisingTempB = 0;

volatile int64_t capturedRisingA = 0;
volatile int64_t capturedRisingB = 0;

volatile bool newEventToReport = false;

// ==========================================
// HARDWARE INTERRUPT SERVICE ROUTINES (ISRs)
// ==========================================
// A simple software debounce to prevent hardware bouncing
// from triggering multiple captures in the same microsecond.
static const int64_t DEBOUNCE_TIME_US = 5000; // 5 milliseconds

// IRAM_ATTR ensures these functions are loaded into ultra-fast 
// internal RAM, not flash memory.
void IRAM_ATTR isrDeviceA() {
  int64_t now = esp_timer_get_time();
  if (now - lastRisingTempA > DEBOUNCE_TIME_US) {
    lastRisingTempA = now;
  }
}

void IRAM_ATTR isrDeviceB() {
  int64_t now = esp_timer_get_time();
  if (now - lastRisingTempB > DEBOUNCE_TIME_US) {
    lastRisingTempB = now;
  }
}

// ==========================================
// SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  delay(100);

  Serial.println("\n\n================================================");
  Serial.println("  ESP32 Arch 2 Synchronization Observer");
  Serial.println("================================================\n");
  
  Serial.printf("Waiting for signals on GPIO %d and GPIO %d...\n", PIN_DEVICE_A, PIN_DEVICE_B);
  
  pinMode(PIN_DEVICE_A, INPUT_PULLDOWN);
  pinMode(PIN_DEVICE_B, INPUT_PULLDOWN);

  // Attach hardware interrupts triggering exactly when the voltage goes from LOW to HIGH.
  attachInterrupt(digitalPinToInterrupt(PIN_DEVICE_A), isrDeviceA, RISING);
  attachInterrupt(digitalPinToInterrupt(PIN_DEVICE_B), isrDeviceB, RISING);
}

// ==========================================
// MAIN LOOP
// ==========================================
int64_t previousA = 0;
int64_t previousB = 0;

void loop() {
  noInterrupts();
  int64_t a = lastRisingTempA;
  int64_t b = lastRisingTempB;
  interrupts();

  // Check if we have unseen pulses on our pins
  bool a_is_new = (a != previousA) && (a > 0);
  bool b_is_new = (b != previousB) && (b > 0);

  if (a_is_new && b_is_new) {
    int64_t drift_us = a - b;
    
    // Valid pairs must be within 500ms of each other. 
    // Anything larger means a device completely skipped a beat or rebooted.
    if (abs(drift_us) < 500000) {
      Serial.printf("DATA:%lld,%lld,%lld\n", a, b, drift_us);
      previousA = a;
      previousB = b;
    } else {
      // Discard the incredibly old pulse so it can catch up to the new one
      if (a < b) {
        previousA = a; // A is way too old, drop it
      } else {
        previousB = b; // B is way too old, drop it
      }
    }
  }
  
  // Prevent WDT reset
  delay(1);
}

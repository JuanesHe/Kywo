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
volatile int64_t timeTriggered = 0;
volatile int64_t capturedRisingA = 0;
volatile int64_t capturedRisingB = 0;

// ==========================================
// HARDWARE INTERRUPT SERVICE ROUTINES (ISRs)
// ==========================================
void IRAM_ATTR isrDeviceA() {
  if (capturedRisingA == 0 && timeTriggered > 0) {
    capturedRisingA = esp_timer_get_time();
  }
}

void IRAM_ATTR isrDeviceB() {
  if (capturedRisingB == 0 && timeTriggered > 0) {
    capturedRisingB = esp_timer_get_time();
  }
}

// ==========================================
// SETUP
// ==========================================
void setup() {
  // Use a fast baud rate to minimize USB communication latency
  Serial.begin(2000000);
  delay(100);

  pinMode(PIN_DEVICE_A, INPUT_PULLDOWN);
  pinMode(PIN_DEVICE_B, INPUT_PULLDOWN);

  attachInterrupt(digitalPinToInterrupt(PIN_DEVICE_A), isrDeviceA, RISING);
  attachInterrupt(digitalPinToInterrupt(PIN_DEVICE_B), isrDeviceB, RISING);
}

// ==========================================
// MAIN LOOP
// ==========================================
void loop() {
  if (Serial.available() > 0) {
    char c = Serial.read();
    
    // As soon as we receive 'H', start the stopwatch
    if (c == 'H') {
      timeTriggered = esp_timer_get_time();
      capturedRisingA = 0;
      capturedRisingB = 0;
      
      // Wait for both hardware interrupts to fire, with a 500ms timeout
      int64_t startWait = esp_timer_get_time();
      while ((capturedRisingA == 0 || capturedRisingB == 0) && (esp_timer_get_time() - startWait < 500000)) {
        // yield slightly to avoid WDT, though tightly polling is okay for <500ms
        esp_rom_delay_us(10);
      }
      
      if (capturedRisingA > 0 && capturedRisingB > 0) {
        int64_t latencyA = capturedRisingA - timeTriggered;
        int64_t latencyB = capturedRisingB - timeTriggered;
        // Output format: DATA: latency_A, latency_B
        Serial.printf("DATA:%lld,%lld\n", latencyA, latencyB);
      } else {
        Serial.println("TIMEOUT: One or both devices failed to respond within 500ms.");
      }
    }
  }
}

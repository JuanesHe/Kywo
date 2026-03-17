/*
 * Kywo - Distributed ESP32 Control System (Production Firmware)
 * 
 * Architecture: Distributed autonomous execution with ESP-NOW clock synchronization
 * Target: <50µs mean drift between nodes
 * 
 * Hardware Configuration (Fixed):
 *   - 3 Digital Outputs (GPIO 15, 16, 17)
 *   - 1 PWM Output (GPIO 18, LEDC Channel 0)
 * 
 * Communication:
 *   - HTTP/TCP: Configuration polling (1000ms interval)
 *   - ESP-NOW: Clock synchronization broadcast (2000ms interval)
 * 
 * Firmware Version: 3.0.0-Production
 * Date: March 17, 2026
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <esp_now.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// ==========================================
// USER CONFIGURATION
// ==========================================
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Server configuration
const char* SERVER_URL = "http://192.168.1.100:8000";  // Update with your server IP
const char* API_KEY    = "super-secret-admin";          // Must match server ADMIN_API_KEY

// ==========================================
// HARDWARE PIN CONFIGURATION (Fixed)
// ==========================================
static const int PIN_DIGITAL_OUT1 = 15;  // GPIO 15
static const int PIN_DIGITAL_OUT2 = 16;  // GPIO 16
static const int PIN_DIGITAL_OUT3 = 17;  // GPIO 17
static const int PIN_PWM_OUT      = 18;  // GPIO 18

// PWM Configuration (LEDC)
static const int PWM_CHANNEL      = 0;   // LEDC channel 0
static const int PWM_FREQUENCY    = 5000; // 5 kHz
static const int PWM_RESOLUTION   = 8;   // 8-bit (0-255)

// ==========================================
// STATE MACHINE MEMORY (Thread-Safe)
// ==========================================
#define MAX_STATES 20

struct StateNode {
  bool digital_out1;
  bool digital_out2;
  bool digital_out3;
  uint8_t pwm_out;       // 0-255 duty cycle
  uint32_t duration_ms;
};

// Double-buffering to avoid race conditions during network updates
struct SequenceConfig {
  StateNode states[MAX_STATES];
  int stateCount;
  uint32_t totalSequenceTimeMs;
  bool isValid;
};

SequenceConfig seqConfigs[2];
volatile int activeConfigIdx = 0;
volatile bool sequenceRunning = false;

TaskHandle_t engineTaskHandle = NULL;
TaskHandle_t syncBroadcastTaskHandle = NULL;

String deviceId;

// ==========================================
// ESP-NOW CLOCK SYNCHRONIZATION
// ==========================================
volatile bool is_master_clock = false;
volatile int  master_channel = 0;
bool esp_now_initialized = false;

volatile int64_t clockOffsetUs = 0;
volatile bool    clockSynced = false;

typedef struct sync_message_t {
  uint32_t magic;
  int64_t master_time_us;
} sync_message_t;

const uint32_t SYNC_MAGIC = 0xA2C22026;  // Updated magic number for v3.0
uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// Sync improvement: Dynamic latency compensation
const int64_t LATENCY_COMPENSATION_US = 1054;  // Measured ESP-NOW median latency

// ==========================================
// WIFI CONNECTION
// ==========================================
void connectWiFi() {
  Serial.printf("\n[wifi] Connecting to %s\n", WIFI_SSID);
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  WiFi.setSleep(false);
  delay(500);

  const int maxRetries = 5;
  for (int attempt = 1; attempt <= maxRetries; attempt++) {
    Serial.printf("[wifi] Attempt %d/%d\n", attempt, maxRetries);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    uint32_t startMs = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - startMs) < 10000) {
      delay(500);
      Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("[wifi] Connected! IP: %s, Channel: %d\n", 
                    WiFi.localIP().toString().c_str(), WiFi.channel());
      return;
    }

    WiFi.disconnect(true);
    delay(1000);
  }

  Serial.println("[wifi] All connection attempts failed. Rebooting...");
  delay(3000);
  ESP.restart();
}

// ==========================================
// ESP-NOW CALLBACKS & SETUP
// ==========================================
#if ESP_ARDUINO_VERSION_MAJOR >= 3
void OnDataRecv(const esp_now_recv_info_t *info, const uint8_t *incomingData, int len) {
#else
void OnDataRecv(const uint8_t * mac, const uint8_t *incomingData, int len) {
#endif
  if (is_master_clock) return; // Grandmaster ignores incoming sync messages
  
  if (len == sizeof(sync_message_t)) {
    sync_message_t msg;
    memcpy(&msg, incomingData, sizeof(msg));
    
    if (msg.magic == SYNC_MAGIC) {
      // Apply latency compensation based on ESP-NOW transmission time
      int64_t masterTimeUs = msg.master_time_us + LATENCY_COMPENSATION_US;
      int64_t localUptimeUs = esp_timer_get_time();
      int64_t instantOffsetUs = masterTimeUs - localUptimeUs;
      
      if (!clockSynced) {
        // Initial synchronization
        clockOffsetUs = instantOffsetUs;
        clockSynced = true;
        Serial.printf("[ESP-NOW] Clock synchronized to Grandmaster! Offset: %lld µs\n", instantOffsetUs);
      } else {
        // Continuous synchronization updates
        clockOffsetUs = instantOffsetUs;
        Serial.print(".");  // Sync pulse indicator
      }
    }
  }
}

void configureEspNow() {
  if (!esp_now_initialized) {
    if (esp_now_init() != ESP_OK) {
      Serial.println("[ESP-NOW] Error: Initialization failed");
      return;
    }
    esp_now_register_recv_cb(OnDataRecv);
    esp_now_initialized = true;
    Serial.println("[ESP-NOW] Initialized successfully");
  }
  
  if (is_master_clock) {
    // Configure as Grandmaster Clock
    Serial.println("[ESP-NOW] Role: GRANDMASTER");
    
    esp_now_peer_info_t peerInfo;
    memset(&peerInfo, 0, sizeof(peerInfo));
    for (int i = 0; i < 6; i++) peerInfo.peer_addr[i] = 0xFF;
    peerInfo.channel = WiFi.channel();
    peerInfo.encrypt = false;
    peerInfo.ifidx = WIFI_IF_STA;
    
    esp_now_del_peer(broadcastAddress);
    if (esp_now_add_peer(&peerInfo) != ESP_OK) {
      Serial.println("[ESP-NOW] Error: Failed to add broadcast peer");
    } else {
      Serial.printf("[ESP-NOW] Broadcasting on channel %d\n", peerInfo.channel);
    }
    
    clockSynced = true;
    clockOffsetUs = 0;
  } else {
    // Configure as Follower
    Serial.printf("[ESP-NOW] Role: FOLLOWER (listening on channel %d)\n", master_channel);
    clockSynced = false;  // Wait for first sync message
  }
}

// ==========================================
// SERVER REGISTRATION (HTTP)
// ==========================================
void registerWithServer() {
  if (WiFi.status() != WL_CONNECTED) return;
  
  HTTPClient http;
  String url = String(SERVER_URL) + "/devices/register";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<256> doc;
  doc["device_id"] = deviceId;
  doc["device_token"] = "kywo-device-token";
  doc["firmware_version"] = "3.0.0-Production";
  doc["wifi_channel"] = WiFi.channel();
  
  String payload;
  serializeJson(doc, payload);

  Serial.printf("[server] Registering as %s...\n", deviceId.c_str());
  int httpCode = http.POST(payload);
  
  if (httpCode == 200) {
    Serial.println("[server] Registration successful");
  } else {
    Serial.printf("[server] Registration failed: HTTP %d\n", httpCode);
  }
  
  http.end();
}

// ==========================================
// CONFIGURATION POLLING (HTTP/TCP)
// ==========================================
uint32_t lastPollMs = 0;
String lastPayload = "";

void pollForConfig() {
  if (WiFi.status() != WL_CONNECTED) return;
  
  HTTPClient http;
  String url = String(SERVER_URL) + "/devices/" + deviceId + "/config";
  http.begin(url);
  http.addHeader("x-api-key", API_KEY);
  
  int httpCode = http.GET();
  
  if (httpCode == 200) {
    String payload = http.getString();
    
    // Only process if configuration changed
    if (payload != lastPayload) {
      Serial.println("[config] New configuration detected. Parsing...");
      
      DynamicJsonDocument doc(4096);
      DeserializationError err = deserializeJson(doc, payload);
      
      if (!err) {
        // Update ESP-NOW role configuration
        bool new_is_master = doc["is_master"].as<bool>();
        int new_master_channel = doc["master_channel"].as<int>();
        
        if (new_is_master != is_master_clock || 
            new_master_channel != master_channel || 
            !esp_now_initialized) {
          is_master_clock = new_is_master;
          master_channel = new_master_channel;
          configureEspNow();
        }

        // Parse sequence configuration
        JsonArray arr = doc["sequence"].as<JsonArray>();
        
        // Build into inactive buffer (thread-safe double-buffering)
        int nextIdx = (activeConfigIdx + 1) % 2;
        SequenceConfig* nxCfg = &seqConfigs[nextIdx];
        
        nxCfg->stateCount = 0;
        uint32_t sumDuration = 0;
        
        for (JsonObject st : arr) {
          if (nxCfg->stateCount >= MAX_STATES) break;
          
          nxCfg->states[nxCfg->stateCount].digital_out1 = st["digital_out1"].as<bool>();
          nxCfg->states[nxCfg->stateCount].digital_out2 = st["digital_out2"].as<bool>();
          nxCfg->states[nxCfg->stateCount].digital_out3 = st["digital_out3"].as<bool>();
          nxCfg->states[nxCfg->stateCount].pwm_out = st["pwm_out"].as<uint8_t>();
          nxCfg->states[nxCfg->stateCount].duration_ms = st["duration_ms"].as<uint32_t>();
          
          sumDuration += st["duration_ms"].as<uint32_t>();
          nxCfg->stateCount++;
        }
        
        nxCfg->totalSequenceTimeMs = sumDuration;
        nxCfg->isValid = (nxCfg->stateCount > 0 && sumDuration > 0);
        
        // Atomic buffer swap - makes new config live to execution engine
        activeConfigIdx = nextIdx;
        sequenceRunning = nxCfg->isValid;
        lastPayload = payload;
        
        Serial.printf("[config] SUCCESS! %d states, %u ms total, PWM enabled\n", 
                     nxCfg->stateCount, nxCfg->totalSequenceTimeMs);
      } else {
        Serial.printf("[config] ERROR: JSON parse failed: %s\n", err.c_str());
      }
    }
  } else if (httpCode > 0) {
    Serial.printf("[config] HTTP error: %d\n", httpCode);
  }
  
  http.end();
}

// ==========================================
// TIME SYNCHRONIZATION HELPER
// ==========================================
int64_t getSyncedTimeUs() {
  if (!clockSynced) return 0;
  return esp_timer_get_time() + clockOffsetUs;
}

// ==========================================
// FREERTOS TASK: SYNC BROADCAST
// ==========================================
void syncBroadcastTask(void * pvParameters) {
  while (true) {
    if (is_master_clock && clockSynced) {
      sync_message_t msg;
      msg.magic = SYNC_MAGIC;
      msg.master_time_us = esp_timer_get_time();
      
      esp_err_t result = esp_now_send(broadcastAddress, (uint8_t *)&msg, sizeof(msg));
      
      if (result == ESP_OK) {
        Serial.print("M");  // Master broadcast indicator
      } else {
        Serial.print("!");  // Broadcast error
      }
    }
    
    vTaskDelay(pdMS_TO_TICKS(2000));  // 2 second sync interval
  }
}

// ==========================================
// FREERTOS TASK: STATE MACHINE EXECUTION
// ==========================================
void stateMachineEngineTask(void * pvParameters) {
  while (true) {
    SequenceConfig* cfg = &seqConfigs[activeConfigIdx];
    
    if (sequenceRunning && cfg->isValid && clockSynced) {
      // Calculate current position in sequence based on synchronized time
      int64_t nowUs = getSyncedTimeUs();
      int64_t totalSequenceTimeUs = (int64_t)cfg->totalSequenceTimeMs * 1000LL;
      
      // Phase within current sequence loop
      int64_t phaseUs = nowUs % totalSequenceTimeUs;
      int64_t accumulatorUs = 0;
      
      // Determine current state
      bool d1 = false, d2 = false, d3 = false;
      uint8_t pwm = 0;
      int64_t timeToNextStateUs = 1000;
      
      for (int i = 0; i < cfg->stateCount; i++) {
        accumulatorUs += ((int64_t)cfg->states[i].duration_ms * 1000LL);
        
        if (phaseUs < accumulatorUs) {
          d1 = cfg->states[i].digital_out1;
          d2 = cfg->states[i].digital_out2;
          d3 = cfg->states[i].digital_out3;
          pwm = cfg->states[i].pwm_out;
          timeToNextStateUs = accumulatorUs - phaseUs;
          break;
        }
      }
      
      // Execute state (fast GPIO writes)
      digitalWrite(PIN_DIGITAL_OUT1, d1 ? HIGH : LOW);
      digitalWrite(PIN_DIGITAL_OUT2, d2 ? HIGH : LOW);
      digitalWrite(PIN_DIGITAL_OUT3, d3 ? HIGH : LOW);
      ledcWrite(PWM_CHANNEL, pwm);
      
      // Intelligent delay strategy for minimal jitter
      uint32_t waitUs = timeToNextStateUs;
      if (waitUs > 10000) waitUs = 10000;  // Max 10ms sleep for config responsiveness
      
      if (waitUs > 2000) {
        // Yield to scheduler for longer waits
        vTaskDelay(pdMS_TO_TICKS(waitUs / 1000));
      } else {
        // Busy-wait for precise timing on short intervals
        int64_t targetTime = esp_timer_get_time() + waitUs;
        while (esp_timer_get_time() < targetTime) {
          taskYIELD();
        }
      }
      
    } else {
      // No valid sequence or not synced - idle state
      digitalWrite(PIN_DIGITAL_OUT1, LOW);
      digitalWrite(PIN_DIGITAL_OUT2, LOW);
      digitalWrite(PIN_DIGITAL_OUT3, LOW);
      ledcWrite(PWM_CHANNEL, 0);
      vTaskDelay(pdMS_TO_TICKS(10));
    }
  }
}

// ==========================================
// SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n========================================");
  Serial.println("Kywo - Production Firmware v3.0.0");
  Serial.println("Distributed ESP32 Control System");
  Serial.println("========================================\n");

  // Configure digital output pins
  pinMode(PIN_DIGITAL_OUT1, OUTPUT);
  pinMode(PIN_DIGITAL_OUT2, OUTPUT);
  pinMode(PIN_DIGITAL_OUT3, OUTPUT);
  digitalWrite(PIN_DIGITAL_OUT1, LOW);
  digitalWrite(PIN_DIGITAL_OUT2, LOW);
  digitalWrite(PIN_DIGITAL_OUT3, LOW);
  
  // Configure PWM output (LEDC)
  ledcSetup(PWM_CHANNEL, PWM_FREQUENCY, PWM_RESOLUTION);
  ledcAttachPin(PIN_PWM_OUT, PWM_CHANNEL);
  ledcWrite(PWM_CHANNEL, 0);
  
  Serial.println("[hw] Hardware initialized:");
  Serial.printf("  Digital outputs: GPIO %d, %d, %d\n", 
                PIN_DIGITAL_OUT1, PIN_DIGITAL_OUT2, PIN_DIGITAL_OUT3);
  Serial.printf("  PWM output: GPIO %d (Channel %d, %d Hz)\n", 
                PIN_PWM_OUT, PWM_CHANNEL, PWM_FREQUENCY);

  // Initialize sequence configs
  seqConfigs[0].isValid = false;
  seqConfigs[1].isValid = false;

  // Connect to WiFi
  connectWiFi();

  // Generate unique device ID from MAC address
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char idBuf[32];
  snprintf(idBuf, sizeof(idBuf), "ESP32-C6-%02X%02X", mac[4], mac[5]);
  deviceId = String(idBuf);
  
  Serial.printf("[boot] Device ID: %s\n", deviceId.c_str());

  // Register with server
  registerWithServer();

  // Initialize ESP-NOW (will be configured as master/follower via config poll)
  configureEspNow();

  // Create ESP-NOW sync broadcast task (runs on core 0)
  xTaskCreatePinnedToCore(
    syncBroadcastTask,
    "espnow_sync",
    3072,
    NULL,
    3,
    &syncBroadcastTaskHandle,
    0  // Core 0
  );

  // Create state machine execution task (runs on core 1 for timing precision)
  xTaskCreatePinnedToCore(
    stateMachineEngineTask,
    "sm_engine",
    4096,
    NULL,
    configMAX_PRIORITIES - 1,  // Highest priority for timing
    &engineTaskHandle,
    1  // Core 1
  );

  Serial.println("[boot] FreeRTOS tasks created:");
  Serial.println("  - ESP-NOW sync task (Core 0, Priority 3)");
  Serial.println("  - State machine engine (Core 1, Highest Priority)");
  Serial.println("\n[boot] System ready. Waiting for configuration...\n");
}

// ==========================================
// MAIN LOOP (Network Polling Only)
// ==========================================
uint32_t lastStatusMs = 0;

void loop() {
  uint32_t now = millis();

  // Reconnect WiFi if disconnected
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[wifi] Connection lost. Reconnecting...");
    connectWiFi();
    registerWithServer();
  }

  // Poll for configuration updates every 1 second
  if (now - lastPollMs > 1000) {
    lastPollMs = now;
    pollForConfig();
  }

  // Status heartbeat every 5 seconds
  if (now - lastStatusMs > 5000) {
    lastStatusMs = now;
    
    if (!clockSynced && !is_master_clock) {
      Serial.println("[status] Waiting for ESP-NOW clock sync from Grandmaster...");
    } else if (sequenceRunning) {
      Serial.printf("[status] Running: %d states, Master: %s\n", 
                   seqConfigs[activeConfigIdx].stateCount,
                   is_master_clock ? "YES" : "NO");
    }
  }

  // Prevent watchdog resets
  vTaskDelay(pdMS_TO_TICKS(10));
}

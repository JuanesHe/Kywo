#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <esp_now.h>

// ==========================================
// CONFIGURATION
// ==========================================
#define HOME 0
#define ESP_DEVICE 301

#if HOME
const char* ssid     = "0e94fc-2.4GHz"; 
const char* password = "yxnzJuan25";
// Server config
const char* SERVER_URL = "http://192.168.87.62:8000";
const char* API_KEY    = "change-me";

#else
const char* ssid     = "TP-Link_9414"; 
const char* password = "TP-Link_9414";
// Server config
const char* SERVER_URL = "http://192.168.0.100:8000";
const char* API_KEY    = "change-me";
#endif


#if ESP_DEVICE == 301
static const int PIN_OUT_1 = 15;
static const int PIN_OUT_2 = 7; 
#elif ESP_DEVICE  == 401
static const int PIN_OUT_1 = 15;
static const int PIN_OUT_2 = 6; 
#endif

String deviceId;

// ==========================================
// THREAD-SAFE STATE MACHINE MEMORY
// ==========================================
#define MAX_STATES 20

struct StateNode {
  bool pin1High;
  bool pin2High;
  uint32_t durationMs;
};

// Double-buffering structure to avoid race conditions when updating from network
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

// ==========================================
// ESP-NOW SYNC MEMORY
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

const uint32_t SYNC_MAGIC = 0xA2C22024;
uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// ==========================================
// WIFI
// ==========================================
void connectWiFi() {
  Serial.printf("\n[wifi] connecting to %s\n", ssid);
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  WiFi.setSleep(false);
  delay(500);

  const int maxRetries = 5;
  for (int attempt = 1; attempt <= maxRetries; attempt++) {
    Serial.printf("[wifi] attempt %d/%d\n", attempt, maxRetries);
    WiFi.begin(ssid, password);

    uint32_t startMs = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - startMs) < 10000) {
      delay(500);
      Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("[wifi] connected, IP: %s, Channel: %d\n", WiFi.localIP().toString().c_str(), WiFi.channel());
      return;
    }

    WiFi.disconnect(true);
    delay(1000);
  }

  Serial.println("[wifi] all attempts failed. Rebooting.");
  delay(5000);
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
  if (is_master_clock) return; // Master ignores incoming clocks
  
  if (len == sizeof(sync_message_t)) {
    sync_message_t msg;
    memcpy(&msg, incomingData, sizeof(msg));
    
    if (msg.magic == SYNC_MAGIC) {
      // Account for the ESP-NOW median time of flight (from arch2_sync_test)
      int64_t LATENCY_COMPENSATION_US = 1054;
      int64_t serverTimeUs = msg.master_time_us + LATENCY_COMPENSATION_US;
      int64_t localUptimeUs = esp_timer_get_time();
      int64_t instantOffsetUs = serverTimeUs - localUptimeUs;
      
      if (!clockSynced) {
        clockOffsetUs = instantOffsetUs;
        clockSynced = true;
        Serial.println("[ESP-NOW] Initial hardware clock synchronized to Grandmaster!");
      } else {
        Serial.print(">");
        clockOffsetUs = instantOffsetUs;
      }
    }
  }
}

void configureEspNow() {
  if (!esp_now_initialized) {
    if (esp_now_init() != ESP_OK) {
      Serial.println("[ESP-NOW] Error initializing");
      return;
    }
    esp_now_register_recv_cb(OnDataRecv);
    esp_now_initialized = true;
  }
  
  if (is_master_clock) {
    Serial.println("[ESP-NOW] Configuring as GRANDMASTER. Adding broadcast peer.");
    esp_now_peer_info_t peerInfo;
    memset(&peerInfo, 0, sizeof(peerInfo));
    for (int i=0; i<6; i++) peerInfo.peer_addr[i] = 0xFF;
    peerInfo.channel = WiFi.channel(); 
    peerInfo.encrypt = false;
    peerInfo.ifidx = WIFI_IF_STA; 
    
    esp_now_del_peer(broadcastAddress);
    if (esp_now_add_peer(&peerInfo) != ESP_OK) {
      Serial.println("[ESP-NOW] Failed to add broadcast peer");
    } else {
      Serial.println("[ESP-NOW] Broadcast peer added successfully.");
    }
    clockSynced = true;
    clockOffsetUs = 0;
  } else {
    Serial.printf("[ESP-NOW] Configuring as FOLLOWER on channel %d. Listening...\n", master_channel);
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

  StaticJsonDocument<200> doc;
  doc["device_id"] = deviceId;
  doc["device_token"] = "arch2-token-123";
  doc["firmware_version"] = "2.3-ESPNOW_Sync_Refactored";
  doc["wifi_channel"] = WiFi.channel();
  
  String payload;
  serializeJson(doc, payload);

  int httpCode = http.POST(payload);
  if (httpCode == 200) {
    Serial.println("[server] Registration successful");
  }
  http.end();
}

// ==========================================
// TCP POLLING FOR STATE MACHINE UPDATES
// ==========================================
uint32_t lastPollMs = 0;
String lastPayload = "";

void pollForConfig() {
  if (WiFi.status() != WL_CONNECTED) return;
  
  HTTPClient http;
  String url = String(SERVER_URL) + "/arch2/devices/" + deviceId + "/config";
  http.begin(url);
  http.addHeader("x-api-key", API_KEY);
  
  int httpCode = http.GET();
  if (httpCode == 200) {
    String payload = http.getString();
    
    if (payload != lastPayload) {
      Serial.println("[config] Detected new payload from server. Parsing...");
      DynamicJsonDocument doc(4096);
      DeserializationError err = deserializeJson(doc, payload);
      
      if (!err) {
        // Handle ESP-NOW Role configuration
        bool new_is_master = doc["is_master"].as<bool>();
        int  new_master_channel = doc["master_channel"].as<int>();
        
        if (new_is_master != is_master_clock || new_master_channel != master_channel || !esp_now_initialized) {
          is_master_clock = new_is_master;
          master_channel = new_master_channel;
          configureEspNow();
        }

        JsonArray arr = doc["sequence"].as<JsonArray>();
        
        // Build parsing into the inactive buffer safely
        int nextIdx = (activeConfigIdx + 1) % 2;
        SequenceConfig* nxCfg = &seqConfigs[nextIdx];
        
        nxCfg->stateCount = 0;
        uint32_t sumDuration = 0;
        
        for (JsonObject st : arr) {
          if (nxCfg->stateCount >= MAX_STATES) break;
          nxCfg->states[nxCfg->stateCount].pin1High   = st["pin1"].as<bool>();
          nxCfg->states[nxCfg->stateCount].pin2High   = st["pin2"].as<bool>();
          nxCfg->states[nxCfg->stateCount].durationMs = st["duration_ms"].as<uint32_t>();
          sumDuration += st["duration_ms"].as<uint32_t>();
          nxCfg->stateCount++;
        }
        
        nxCfg->totalSequenceTimeMs = sumDuration;
        nxCfg->isValid = (nxCfg->stateCount > 0 && sumDuration > 0);
        
        // Atomic swap of buffers makes it immediately live to the execution engine
        activeConfigIdx = nextIdx;
        sequenceRunning = nxCfg->isValid;
        lastPayload = payload; 
        
        Serial.printf("[config] SUCCESS! New config applied: %d states, %u ms total loop\n", nxCfg->stateCount, nxCfg->totalSequenceTimeMs);
      } else {
        Serial.printf("[config] ERROR: JSON deserialization failed: %s\n", err.c_str());
      }
    }
  } else {
    Serial.printf("[config] ERROR: HTTP GET failed with code %d\n", httpCode);
  }
  http.end();
}

// ==========================================
// TIME HELPER
// ==========================================
int64_t getSyncedTimeUs() {
  if (!clockSynced) return 0;
  return esp_timer_get_time() + clockOffsetUs;
}

// ==========================================
// TASKS: SYNC BROADCAST & ENGINE LOGIC
// ==========================================

// Task to handle Grandmaster syncing independent of the network HTTP delays
void syncBroadcastTask(void * pvParameters) {
  while (true) {
    if (is_master_clock && clockSynced) {
      sync_message_t msg;
      msg.magic = SYNC_MAGIC;
      msg.master_time_us = esp_timer_get_time();
      
      esp_now_send(broadcastAddress, (uint8_t *) &msg, sizeof(sync_message_t));
    }
    vTaskDelay(pdMS_TO_TICKS(2000));
  }
}

// High Precision Execution Engine
void stateMachineEngineTask(void * pvParameters) {
  while (true) {
    SequenceConfig* cfg = &seqConfigs[activeConfigIdx];
    
    if (sequenceRunning && cfg->isValid && clockSynced) {
      int64_t nowUs = getSyncedTimeUs();
      int64_t totalSequenceTimeUs = (int64_t)cfg->totalSequenceTimeMs * 1000LL;
      
      int64_t phaseUs = nowUs % totalSequenceTimeUs;
      int64_t accumulatorUs = 0;
      
      bool p1 = cfg->states[0].pin1High;
      bool p2 = cfg->states[0].pin2High;
      int64_t timeToNextStateUs = 1000;
      
      for (int i = 0; i < cfg->stateCount; i++) {
        accumulatorUs += ((int64_t)cfg->states[i].durationMs * 1000LL);
        if (phaseUs < accumulatorUs) {
          p1 = cfg->states[i].pin1High;
          p2 = cfg->states[i].pin2High;
          timeToNextStateUs = accumulatorUs - phaseUs;
          break;
        }
      }
      
      digitalWrite(PIN_OUT_1, p1 ? HIGH : LOW);
      digitalWrite(PIN_OUT_2, p2 ? HIGH : LOW);
      
      // Calculate delay. Don't block indefinitely to stay responsive to updates.
      uint32_t waitUs = timeToNextStateUs;
      if (waitUs > 10000) waitUs = 10000; // sleep 10ms at most to pick up new configs instantly
      
      if (waitUs > 2000) {
        // Yield entirely if we have enough time 
        vTaskDelay(pdMS_TO_TICKS(waitUs / 1000));
      } else {
        // Busy-wait the final <2ms precisely without yielding the core heavily
        int64_t targetTime = esp_timer_get_time() + waitUs;
        while(esp_timer_get_time() < targetTime) {
          taskYIELD(); 
        }
      }
      
    } else {
      digitalWrite(PIN_OUT_1, LOW);
      digitalWrite(PIN_OUT_2, LOW);
      vTaskDelay(pdMS_TO_TICKS(10));
    }
  }
}

// ==========================================
// SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(PIN_OUT_1, OUTPUT);
  pinMode(PIN_OUT_2, OUTPUT);
  digitalWrite(PIN_OUT_1, LOW);
  digitalWrite(PIN_OUT_2, LOW);

  // Init structures
  seqConfigs[0].isValid = false;
  seqConfigs[1].isValid = false;

  Serial.println("\n--- ESP32 Arch 2 ESP-NOW SYNC State Machine ---");

  connectWiFi();

  uint8_t mac[6];
  WiFi.macAddress(mac);
  char idBuf[32];
  snprintf(idBuf, sizeof(idBuf), "ESP32-C6-%02X%02X", mac[4], mac[5]);
  deviceId = String(idBuf);
  
  Serial.printf("[boot] Assigned Device ID: %s\n", deviceId.c_str());

  registerWithServer();

  // Initially configure ESP-NOW as follower (until config says otherwise)
  configureEspNow();

  // Create Broadcast Task
  xTaskCreate(
    syncBroadcastTask, 
    "syncTask", 
    3072, 
    NULL, 
    3, 
    &syncBroadcastTaskHandle
  );

  // Create Engine Task
  xTaskCreate(
    stateMachineEngineTask, 
    "sm_engine", 
    4096, 
    NULL, 
    configMAX_PRIORITIES - 1, 
    &engineTaskHandle
  );

  Serial.println("[boot] Engine & Sync Tasks running. Waiting for clock sync...");
}

// ==========================================
// MAIN LOOP (Network Polling ONLY)
// ==========================================
uint32_t lastPrintMs = 0;

void loop() {
  uint32_t now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    registerWithServer();
  }

  // Poll TCP Config every 1 second
  if (now - lastPollMs > 1000) {
    lastPollMs = now;
    pollForConfig();
    
    // Status heartbeat
    if (!clockSynced && !is_master_clock && (now - lastPrintMs > 2000)) {
      lastPrintMs = now;
      Serial.println("[status] Waiting for ESP-NOW Grandmaster clock sync...");
    }
  }

  // Back off slightly to avoid watchdog resets
  vTaskDelay(pdMS_TO_TICKS(10));
}


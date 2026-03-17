#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// Fill these values before uploading.
static const char* WIFI_SSID = "YOUR_WIFI_SSID";
static const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
static const char* SERVER_BASE_URL = "http://172.20.10.7:8000";

static const char* DEVICE_ID = "esp32-a";
static const char* DEVICE_TOKEN = "token-device-a";
static const char* FIRMWARE_VERSION = "1.0.0";

// Adjust to match your hardware. Use -1 to disable GPIO actions.
static const int ACTUATOR_PIN = -1;

static const uint32_t WIFI_RETRY_MS = 3000;
static const uint32_t COMMAND_POLL_MS = 2000;

uint32_t lastPollMs = 0;
uint32_t lastRegisterRetryMs = 0;
bool isRegistered = false;
int lastCommandId = 0;

String buildUrl(const String& path) {
  return String(SERVER_BASE_URL) + path;
}

bool ensureWifiConnected() {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  Serial.println("[wifi] connecting...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint32_t startMs = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - startMs) < 10000) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[wifi] connected, ip=");
    Serial.println(WiFi.localIP());
    return true;
  }

  Serial.println("[wifi] connection failed");
  return false;
}

bool checkServerHealth() {
  HTTPClient http;
  String url = buildUrl("/health");
  Serial.printf("[health] url=%s\n", url.c_str());
  http.begin(url);

  int code = http.GET();
  if (code <= 0) {
    Serial.printf("[health] failed, error=%s\n", http.errorToString(code).c_str());
    http.end();
    return false;
  }

  String response = http.getString();
  if (code != 200) {
    Serial.printf("[health] status=%d body=%s\n", code, response.c_str());
    http.end();
    return false;
  }

  StaticJsonDocument<128> doc;
  DeserializationError err = deserializeJson(doc, response);
  if (err) {
    Serial.printf("[health] json parse error=%s\n", err.c_str());
    http.end();
    return false;
  }

  const char* status = doc["status"] | "";
  bool ok = String(status) == "ok";
  Serial.printf("[health] status_field=%s\n", status);
  http.end();
  return ok;
}

bool registerDevice() {
  if (!ensureWifiConnected()) {
    return false;
  }

  if (!checkServerHealth()) {
    Serial.println("[register] skipped: health check failed");
    return false;
  }

  HTTPClient http;
  String url = buildUrl("/devices/register");
  Serial.printf("[register] url=%s\n", url.c_str());
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<256> body;
  body["device_id"] = DEVICE_ID;
  body["device_token"] = DEVICE_TOKEN;
  body["firmware_version"] = FIRMWARE_VERSION;

  String payload;
  serializeJson(body, payload);

  int code = http.POST(payload);
  if (code > 0) {
    String response = http.getString();
    Serial.printf("[register] status=%d body=%s\n", code, response.c_str());
    http.end();
    return code == 200;
  }

  Serial.printf("[register] failed, error=%s\n", http.errorToString(code).c_str());
  http.end();
  return false;
}

bool ackCommand(int commandId) {
  HTTPClient http;
  String path = String("/devices/") + DEVICE_ID + "/ack?token=" + DEVICE_TOKEN;
  http.begin(buildUrl(path));
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<128> body;
  body["command_id"] = commandId;

  String payload;
  serializeJson(body, payload);

  int code = http.POST(payload);
  if (code > 0) {
    String response = http.getString();
    Serial.printf("[ack] id=%d status=%d body=%s\n", commandId, code, response.c_str());
    http.end();
    return code == 200;
  }

  Serial.printf("[ack] failed id=%d error=%s\n", commandId, http.errorToString(code).c_str());
  http.end();
  return false;
}

void applyActuatorState(bool on) {
  if (ACTUATOR_PIN < 0) {
    return;
  }
  digitalWrite(ACTUATOR_PIN, on ? HIGH : LOW);
}

void handleCommand(const String& command) {
  // Keep commands very simple and deterministic.
  if (command == "relay:on" || command == "led:on") {
    applyActuatorState(true);
    Serial.println("[command] actuator ON");
    return;
  }

  if (command == "relay:off" || command == "led:off") {
    applyActuatorState(false);
    Serial.println("[command] actuator OFF");
    return;
  }

  Serial.printf("[command] unhandled=%s\n", command.c_str());
}

bool pollCommands() {
  HTTPClient http;
  String path = String("/devices/") + DEVICE_ID + "/commands?token=" + DEVICE_TOKEN +
                "&after_command_id=" + String(lastCommandId) + "&limit=10";
  String url = buildUrl(path);
  Serial.printf("[poll] url=%s\n", url.c_str());
  http.begin(url);

  int code = http.GET();
  if (code <= 0) {
    Serial.printf("[poll] failed, error=%s\n", http.errorToString(code).c_str());
    http.end();
    return false;
  }

  String response = http.getString();
  if (code != 200) {
    Serial.printf("[poll] status=%d body=%s\n", code, response.c_str());
    http.end();
    return false;
  }

  StaticJsonDocument<2048> doc;
  DeserializationError err = deserializeJson(doc, response);
  if (err) {
    Serial.printf("[poll] json parse error=%s\n", err.c_str());
    http.end();
    return false;
  }

  JsonArray commands = doc["commands"].as<JsonArray>();
  for (JsonObject cmd : commands) {
    int commandId = cmd["command_id"] | 0;
    const char* command = cmd["command"] | "";

    if (commandId <= 0) {
      continue;
    }

    Serial.printf("[poll] command_id=%d command=%s\n", commandId, command);
    handleCommand(String(command));

    if (ackCommand(commandId)) {
      lastCommandId = commandId;
    }
  }

  http.end();
  return true;
}

void scanNetworks() {
  Serial.println("[wifi] Scanning for networks...");
  int n = WiFi.scanNetworks();
  Serial.println("[wifi] Scan done");
  if (n == 0) {
    Serial.println("[wifi] No networks found");
  } else {
    Serial.printf("[wifi] %d networks found\n", n);
    for (int i = 0; i < n; ++i) {
      String encryption = (WiFi.encryptionType(i) == WIFI_AUTH_OPEN) ? " " : "*";
      Serial.printf("[wifi] %2d: %s (%d)%s\n", i + 1, WiFi.SSID(i).c_str(), WiFi.RSSI(i), encryption.c_str());
      delay(10);
    }
  }
  Serial.println("");
}

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("[boot] esp32-c6 client starting");
  Serial.printf("[boot] ssid=%s\n", WIFI_SSID);
  Serial.printf("[boot] server=%s\n", SERVER_BASE_URL);
  Serial.printf("[boot] device_id=%s\n", DEVICE_ID);

  if (ACTUATOR_PIN >= 0) {
    pinMode(ACTUATOR_PIN, OUTPUT);
    digitalWrite(ACTUATOR_PIN, LOW);
  }

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);

  scanNetworks();
}

void loop() {
  if (!ensureWifiConnected()) {
    delay(WIFI_RETRY_MS);
    return;
  }

  uint32_t nowMs = millis();

  if (!isRegistered && (nowMs - lastRegisterRetryMs > 5000)) {
    lastRegisterRetryMs = nowMs;
    isRegistered = registerDevice();
    if (!isRegistered) {
      return;
    }
  }

  if (nowMs - lastPollMs >= COMMAND_POLL_MS) {
    lastPollMs = nowMs;
    if (!checkServerHealth()) {
      // Force a fresh register flow when the server is temporarily unreachable.
      isRegistered = false;
      return;
    }

    bool pollOk = pollCommands();
    if (!pollOk) {
      // Re-register after transport failures or non-200 responses.
      isRegistered = false;
    }
  }

  delay(20);
}

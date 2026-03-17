#include <Arduino.h>
#include <WiFi.h>
#include <lwip/netdb.h>
#include <lwip/sockets.h> // POSIX sockets for blocking recvfrom
#include <string.h>

// ---- Configuration ----
static const char *WIFI_SSID = "0e94fc-2.4GHz";
static const char *WIFI_PASSWORD = "yxnzJuan25";

// Output pin — wire your LED or relay here
static const int ACTUATOR_PIN = 15;

// UDP port must match the server's broadcast port
static const int UDP_PORT = 4210;

// FreeRTOS task priority (higher = preempts lower-priority tasks instantly)
// WiFi internal task runs at priority 23. We run just below it.
static const int UDP_TASK_PRIORITY = 22;
static const int UDP_TASK_STACK = 4096;

// How often the main loop checks WiFi health (ms)
static const uint32_t WIFI_CHECK_INTERVAL_MS = 5000;

// ---- State ----
static int udp_sock = -1; // raw POSIX socket
static volatile uint32_t lastWifiCheckMs = 0;

// ---- WiFi connection (runs on Arduino core task) ----
void connectWiFi() {
  Serial.print("[wifi] connecting to ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(200);

  WiFi.setSleep(false); // Disable modem sleep for lowest latency

  int retries = 0;
  const int maxRetries = 5;

  while (retries < maxRetries) {
    Serial.printf("[wifi] attempt %d/%d\n", retries + 1, maxRetries);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    uint32_t startMs = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - startMs) < 10000) {
      delay(500);
      Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
      Serial.print("[wifi] connected, IP: ");
      Serial.println(WiFi.localIP());
      return;
    }

    Serial.println("[wifi] attempt failed, retrying...");
    WiFi.disconnect(true);
    delay(1000);
    retries++;
  }

  Serial.println("[wifi] all attempts failed! Rebooting in 5s...");
  delay(5000);
  ESP.restart();
}

// ---- Create raw POSIX UDP socket ----
int createUdpSocket() {
  int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (sock < 0) {
    Serial.println("[udp] socket() failed");
    return -1;
  }

  // Allow address reuse
  int opt = 1;
  setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

  // Bind to port
  struct sockaddr_in addr;
  memset(&addr, 0, sizeof(addr));
  addr.sin_family = AF_INET;
  addr.sin_port = htons(UDP_PORT);
  addr.sin_addr.s_addr = htonl(INADDR_ANY);

  if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
    Serial.printf("[udp] bind() to port %d failed\n", UDP_PORT);
    close(sock);
    return -1;
  }

  Serial.printf("[udp] POSIX socket bound to port %d\n", UDP_PORT);
  return sock;
}

// ┌─────────────────────────────────────────────────────────────────────┐
// │  HIGH-PRIORITY FreeRTOS TASK                                       │
// │                                                                    │
// │  This task blocks on recvfrom(). The RTOS scheduler wakes it the   │
// │  instant a packet arrives in the LwIP buffer — acting like a       │
// │  hardware interrupt. No polling, no wasted CPU, minimal latency.   │
// └─────────────────────────────────────────────────────────────────────┘
void udpReceiverTask(void *param) {
  char rxBuf[256];
  char txBuf[256];
  struct sockaddr_in senderAddr;
  socklen_t addrLen;

  Serial.printf("[task] UDP receiver running on core %d at priority %d\n",
                xPortGetCoreID(), uxTaskPriorityGet(NULL));

  while (true) {
    // BLOCKING call — task sleeps here until a packet arrives
    addrLen = sizeof(senderAddr);
    int len = recvfrom(udp_sock, rxBuf, sizeof(rxBuf) - 1, 0,
                       (struct sockaddr *)&senderAddr, &addrLen);

    if (len <= 0)
      continue;
    rxBuf[len] = '\0';

    // ── Ping/Pong (fastest path: respond before ANYTHING else) ──
    if (len > 5 && strncmp(rxBuf, "ping:", 5) == 0) {
      int txLen = snprintf(txBuf, sizeof(txBuf), "pong:%s", rxBuf + 5);

      // Reply to sender on the known port
      struct sockaddr_in replyAddr;
      memset(&replyAddr, 0, sizeof(replyAddr));
      replyAddr.sin_family = AF_INET;
      replyAddr.sin_port = htons(UDP_PORT);
      replyAddr.sin_addr = senderAddr.sin_addr;

      sendto(udp_sock, txBuf, txLen, 0, (struct sockaddr *)&replyAddr,
             sizeof(replyAddr));

      // Log AFTER sending (non-blocking path)
      Serial.printf("[ping] pong:%s\n", rxBuf + 5);
      continue;
    }

    // ── Relay commands (GPIO first, log second) ──
    if (strcmp(rxBuf, "relay:on") == 0) {
      digitalWrite(ACTUATOR_PIN, HIGH);
      Serial.println("[cmd] relay ON");
    } else if (strcmp(rxBuf, "relay:off") == 0) {
      digitalWrite(ACTUATOR_PIN, LOW);
      Serial.println("[cmd] relay OFF");
    } else {
      Serial.printf("[cmd] unknown: %s\n", rxBuf);
    }
  }
}

// ---- Arduino setup ----
void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("\n[boot] ESP32 UDP Real-Time Receiver v2.0 (interrupt-like)");

  if (ACTUATOR_PIN >= 0) {
    pinMode(ACTUATOR_PIN, OUTPUT);
    digitalWrite(ACTUATOR_PIN, LOW);
  }

  connectWiFi();

  // Create raw POSIX socket (replaces Arduino WiFiUDP)
  udp_sock = createUdpSocket();
  if (udp_sock < 0) {
    Serial.println("[fatal] Could not create UDP socket. Rebooting...");
    delay(3000);
    ESP.restart();
  }

  // Launch the high-priority receiver task
  // Note: ESP32-C6 is single-core — use xTaskCreate (not PinnedToCore)
  xTaskCreate(
    udpReceiverTask,     // Task function
    "udp_rx",            // Name
    UDP_TASK_STACK,      // Stack size (bytes)
    NULL,                // Parameter
    UDP_TASK_PRIORITY,   // Priority (22 = just below WiFi driver)
    NULL                 // Task handle (not needed)
  );

  Serial.println("[boot] Setup complete. Receiver task launched.");
}

// ---- Arduino loop (low-priority housekeeping only) ----
void loop() {
  uint32_t now = millis();
  if (now - lastWifiCheckMs > WIFI_CHECK_INTERVAL_MS) {
    lastWifiCheckMs = now;
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[wifi] lost! reconnecting...");
      connectWiFi();

      // Recreate socket after reconnection
      if (udp_sock >= 0)
        close(udp_sock);
      udp_sock = createUdpSocket();
    }
  }

  delay(100); // Main loop can sleep — all real work is in the RTOS task
}

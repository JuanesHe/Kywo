#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_http_client.h"
#include "cJSON.h"
#include "driver/gpio.h"

#define WIFI_SSID      "YOUR_WIFI_SSID"
#define WIFI_PASS      "YOUR_WIFI_PASSWORD"
#define SERVER_BASE_URL "http://192.168.87.62:8000"

#define DEVICE_ID      "esp32-a"
#define DEVICE_TOKEN   "token-device-a"
#define FIRMWARE_VERSION "1.0.0"

#define ACTUATOR_PIN   -1  // Change to match your hardware (-1 disables)

#define WIFI_RETRY_MS   3000
#define COMMAND_POLL_MS 2000
#define MAX_HTTP_RECV_BUFFER 2048

static const char *TAG = "kywo_client";
static int last_command_id = 0;
static bool is_registered = false;
static EventGroupHandle_t s_wifi_event_group;
#define WIFI_CONNECTED_BIT BIT0

static void event_handler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        esp_wifi_connect();
        xEventGroupClearBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
        ESP_LOGI(TAG, "retry to connect to the AP");
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "got ip:" IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

void wifi_init_sta(void) {
    s_wifi_event_group = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &event_handler, NULL, &instance_any_id));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &event_handler, NULL, &instance_got_ip));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = WIFI_SSID,
            .password = WIFI_PASS,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
}

bool ensure_wifi_connected() {
    EventBits_t bits = xEventGroupWaitBits(s_wifi_event_group, WIFI_CONNECTED_BIT, pdFALSE, pdFALSE, portMAX_DELAY);
    return (bits & WIFI_CONNECTED_BIT) != 0;
}

esp_err_t perform_http_request(esp_http_client_config_t *config, char* response_buffer, int* status_code, const char* post_data) {
    esp_http_client_handle_t client = esp_http_client_init(config);
    if (!client) return ESP_FAIL;
    
    if (post_data) {
        esp_http_client_set_url(client, config->url);
        esp_http_client_set_method(client, HTTP_METHOD_POST);
        esp_http_client_set_header(client, "Content-Type", "application/json");
        esp_http_client_set_post_field(client, post_data, strlen(post_data));
    }
    
    esp_err_t err = esp_http_client_open(client, post_data ? strlen(post_data) : 0);
    if (err != ESP_OK) {
        esp_http_client_cleanup(client);
        return err;
    }
    
    int content_length = esp_http_client_fetch_headers(client);
    if (content_length < 0) content_length = 0;
    
    if (response_buffer) {
        int total_read = 0;
        while (1) {
            int to_read = MAX_HTTP_RECV_BUFFER - total_read - 1;
            if (to_read <= 0) break;
            
            int read_len = esp_http_client_read(client, response_buffer + total_read, to_read);
            if (read_len <= 0) break;
            total_read += read_len;
        }
        response_buffer[total_read] = 0;
    }
    
    *status_code = esp_http_client_get_status_code(client);
    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    return ESP_OK;
}

bool check_server_health() {
    char url[256];
    snprintf(url, sizeof(url), "%s/health", SERVER_BASE_URL);
    
    char response[MAX_HTTP_RECV_BUFFER] = {0};
    int status_code = 0;
    
    esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = 5000,
    };
    
    esp_err_t err = perform_http_request(&config, response, &status_code, NULL);
    if (err != ESP_OK || status_code != 200) {
        ESP_LOGE(TAG, "[health] failed err=%s status=%d", esp_err_to_name(err), status_code);
        return false;
    }
    
    cJSON *json = cJSON_Parse(response);
    if (!json) {
        ESP_LOGE(TAG, "[health] json parse error");
        return false;
    }
    
    cJSON *status = cJSON_GetObjectItem(json, "status");
    bool ok = (status && status->valuestring && strcmp(status->valuestring, "ok") == 0);
    cJSON_Delete(json);
    return ok;
}

bool register_device() {
    if (!check_server_health()) return false;
    
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "device_id", DEVICE_ID);
    cJSON_AddStringToObject(root, "device_token", DEVICE_TOKEN);
    cJSON_AddStringToObject(root, "firmware_version", FIRMWARE_VERSION);
    char *post_data = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    
    char url[256];
    snprintf(url, sizeof(url), "%s/devices/register", SERVER_BASE_URL);
    
    char response[MAX_HTTP_RECV_BUFFER] = {0};
    int status_code = 0;
    
    esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = 5000,
    };
    
    esp_err_t err = perform_http_request(&config, response, &status_code, post_data);
    free(post_data);
    
    if (err == ESP_OK && status_code == 200) {
        ESP_LOGI(TAG, "[register] success");
        return true;
    }
    
    ESP_LOGE(TAG, "[register] failed err=%s status=%d", esp_err_to_name(err), status_code);
    return false;
}

bool ack_command(int command_id) {
    cJSON *root = cJSON_CreateObject();
    cJSON_AddNumberToObject(root, "command_id", command_id);
    char *post_data = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    
    char url[256];
    snprintf(url, sizeof(url), "%s/devices/%s/ack?token=%s", SERVER_BASE_URL, DEVICE_ID, DEVICE_TOKEN);
    
    char response[MAX_HTTP_RECV_BUFFER] = {0};
    int status_code = 0;
    
    esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = 5000,
    };
    
    esp_err_t err = perform_http_request(&config, response, &status_code, post_data);
    free(post_data);
    
    if (err == ESP_OK && status_code == 200) {
        ESP_LOGI(TAG, "[ack] id=%d success", command_id);
        return true;
    }
    
    ESP_LOGE(TAG, "[ack] failed id=%d err=%s status=%d", command_id, esp_err_to_name(err), status_code);
    return false;
}

void apply_actuator_state(bool on) {
    if (ACTUATOR_PIN < 0) return;
    gpio_set_level((gpio_num_t)ACTUATOR_PIN, on ? 1 : 0);
}

void handle_command(const char* command) {
    if (strcmp(command, "relay:on") == 0 || strcmp(command, "led:on") == 0) {
        apply_actuator_state(true);
        ESP_LOGI(TAG, "[command] actuator ON");
    } else if (strcmp(command, "relay:off") == 0 || strcmp(command, "led:off") == 0) {
        apply_actuator_state(false);
        ESP_LOGI(TAG, "[command] actuator OFF");
    } else {
        ESP_LOGW(TAG, "[command] unhandled=%s", command);
    }
}

bool poll_commands() {
    char url[256];
    snprintf(url, sizeof(url), "%s/devices/%s/commands?token=%s&after_command_id=%d&limit=10", 
             SERVER_BASE_URL, DEVICE_ID, DEVICE_TOKEN, last_command_id);
             
    char response[MAX_HTTP_RECV_BUFFER] = {0};
    int status_code = 0;
    
    esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = 5000,
    };
    
    esp_err_t err = perform_http_request(&config, response, &status_code, NULL);
    if (err != ESP_OK || status_code != 200) {
        ESP_LOGE(TAG, "[poll] failed err=%s status=%d", esp_err_to_name(err), status_code);
        return false;
    }
    
    cJSON *json = cJSON_Parse(response);
    if (!json) {
        ESP_LOGE(TAG, "[poll] json parse error");
        return false;
    }
    
    cJSON *commands = cJSON_GetObjectItem(json, "commands");
    if (cJSON_IsArray(commands)) {
        int num_items = cJSON_GetArraySize(commands);
        for (int i=0; i<num_items; i++) {
            cJSON *cmd = cJSON_GetArrayItem(commands, i);
            int command_id = cJSON_GetObjectItem(cmd, "command_id") ? cJSON_GetObjectItem(cmd, "command_id")->valueint : 0;
            const char* command = cJSON_GetObjectItem(cmd, "command") ? cJSON_GetObjectItem(cmd, "command")->valuestring : "";
            
            if (command_id <= 0) continue;
            
            ESP_LOGI(TAG, "[poll] command_id=%d command=%s", command_id, command);
            handle_command(command);
            
            if (ack_command(command_id)) {
                last_command_id = command_id;
            }
        }
    }
    
    cJSON_Delete(json);
    return true;
}

void app_main(void) {
    ESP_LOGI(TAG, "[boot] esp32-c6 native client starting");
    
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    if (ACTUATOR_PIN >= 0) {
        gpio_reset_pin((gpio_num_t)ACTUATOR_PIN);
        gpio_set_direction((gpio_num_t)ACTUATOR_PIN, GPIO_MODE_OUTPUT);
        gpio_set_level((gpio_num_t)ACTUATOR_PIN, 0);
    }

    wifi_init_sta();

    while (1) {
        if (!ensure_wifi_connected()) {
            vTaskDelay(pdMS_TO_TICKS(WIFI_RETRY_MS));
            continue;
        }

        if (!is_registered) {
            is_registered = register_device();
            if (!is_registered) {
                vTaskDelay(pdMS_TO_TICKS(5000));
                continue;
            }
        }

        if (check_server_health()) {
            bool poll_ok = poll_commands();
            if (!poll_ok) {
                is_registered = false;
            }
        } else {
            is_registered = false;
        }
        
        vTaskDelay(pdMS_TO_TICKS(COMMAND_POLL_MS));
    }
}

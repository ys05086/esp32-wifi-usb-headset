#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "bootloader_random.h"
#include "cJSON.h"
#include "esp_app_desc.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_system.h"
#include "nvs.h"
#include "board_config.h"
#include "board_identity.h"
#include "usb_profile.h"
#include "wifi_bridge.h"

static const char *TAG = "board";
static char ssid[BOARD_SSID_LEN + 1];
static char password[64];

const char *board_ap_ssid(void) { return ssid; }
const char *board_ap_password(void) { return password; }

static esp_err_t save_password(const char *value) {
    nvs_handle_t handle;
    esp_err_t error = nvs_open("vs_board", NVS_READWRITE, &handle);
    if (error != ESP_OK) return error;
    error = nvs_set_str(handle, "ap_pass", value);
    if (error == ESP_OK) error = nvs_commit(handle);
    nvs_close(handle);
    if (error == ESP_OK) snprintf(password, sizeof password, "%s", value);
    return error;
}

static void fresh_password(char out[BOARD_PASSWORD_LEN + 1]) {
    uint8_t random[BOARD_PASSWORD_RANDOM];
    esp_fill_random(random, sizeof random);
    board_password_make(random, out);
}

void board_config_load(void) {
    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP));
    board_ssid_make(mac, ssid);
    nvs_handle_t handle;
    size_t size = sizeof password;
    if (nvs_open("vs_board", NVS_READONLY, &handle) == ESP_OK) {
        if (nvs_get_str(handle, "ap_pass", password, &size) != ESP_OK || !board_password_valid(password)) password[0] = 0;
        nvs_close(handle);
    }
    if (password[0]) return;
    // First boot: the radio is still off, so take the ADC noise source for real entropy.
    char made[BOARD_PASSWORD_LEN + 1];
    bootloader_random_enable();
    fresh_password(made);
    bootloader_random_disable();
    if (save_password(made) != ESP_OK) {
        snprintf(password, sizeof password, "%s", made);
        ESP_LOGE(TAG, "Could not save the board Wi-Fi password; it changes on the next boot");
    }
}

static const char *mode_name(vs_usb_mode_t mode) {
    return mode == VS_USB_ADAPTIVE ? "adaptive" : mode == VS_USB_APPLE ? "apple" : "standard";
}

static void reply(cJSON *body) {
    char *text = body ? cJSON_PrintUnformatted(body) : NULL;
    if (text) printf("@ok %s\n", text); else printf("@err out of memory\n");
    fflush(stdout);
    cJSON_free(text);
    cJSON_Delete(body);
}

static void fail(const char *message) { printf("@err %s\n", message); fflush(stdout); }

static cJSON *state(void) {
    cJSON *s = cJSON_CreateObject();
    if (!s) return NULL;
    char station[33], ip[16];
    bool connected = wifi_bridge_station(station, ip);
    cJSON_AddStringToObject(s, "board", "esp32-wifi-usb-headset");
    cJSON_AddStringToObject(s, "firmware", esp_app_get_description()->version);
    cJSON_AddStringToObject(s, "ap_ssid", ssid);
    cJSON_AddStringToObject(s, "ap_password", password);
    cJSON_AddStringToObject(s, "ap_ip", "192.168.4.1");
    cJSON_AddStringToObject(s, "wifi_ssid", station);
    cJSON_AddBoolToObject(s, "wifi_connected", connected);
    cJSON_AddStringToObject(s, "router_ip", connected ? ip : "");
    cJSON_AddStringToObject(s, "usb_mode", vs_usb_mode_name());
    cJSON_AddStringToObject(s, "usb_mode_saved", mode_name(usb_profile_saved()));
    cJSON_AddNumberToObject(s, "udp_port", 49152);
    return s;
}

static void set(const char *text) {
    cJSON *json = cJSON_Parse(text);
    if (!cJSON_IsObject(json)) { cJSON_Delete(json); fail("set needs a JSON object"); return; }
    const cJSON *usb = cJSON_GetObjectItemCaseSensitive(json, "usb_mode");
    const cJSON *ap = cJSON_GetObjectItemCaseSensitive(json, "ap_password");
    const cJSON *wifi = cJSON_GetObjectItemCaseSensitive(json, "wifi_ssid");
    const cJSON *wifi_password = cJSON_GetObjectItemCaseSensitive(json, "wifi_password");
    vs_usb_mode_t mode = VS_USB_STANDARD;
    // Check everything first, so a bad field changes nothing.
    const char *problem = NULL;
    if (usb) {
        const char *v = cJSON_IsString(usb) ? usb->valuestring : "";
        if (!strcmp(v, "apple")) mode = VS_USB_APPLE;
        else if (!strcmp(v, "adaptive")) mode = VS_USB_ADAPTIVE;
        else if (strcmp(v, "standard")) problem = "usb_mode is standard, apple or adaptive";
    }
    if (ap && (!cJSON_IsString(ap) || !board_password_valid(ap->valuestring)))
        problem = "ap_password needs 8-63 printable ASCII characters";
    if (wifi) {
        const char *p = cJSON_IsString(wifi_password) ? wifi_password->valuestring : wifi_password ? NULL : "";
        if (!cJSON_IsString(wifi) || strlen(wifi->valuestring) > 32 || !p || strlen(p) > 63 || (*p && strlen(p) < 8))
            problem = "wifi_ssid up to 32 bytes; wifi_password empty or 8-63 characters";
    }
    if (!usb && !ap && !wifi) problem = "nothing to set: usb_mode, ap_password, wifi_ssid/wifi_password";
    if (problem) { cJSON_Delete(json); fail(problem); return; }
    esp_err_t error = ESP_OK;
    if (usb) error = usb_profile_save(mode);
    if (error == ESP_OK && ap && strcmp(ap->valuestring, password)) {
        error = save_password(ap->valuestring);
        if (error == ESP_OK) error = wifi_bridge_apply_ap();
    }
    if (error == ESP_OK && wifi)
        error = wifi_bridge_set_station(wifi->valuestring, cJSON_IsString(wifi_password) ? wifi_password->valuestring : "");
    cJSON_Delete(json);
    if (error != ESP_OK) { fail(esp_err_to_name(error)); return; }
    reply(state());
}

void board_config_command(const char *line) {
    while (*line == ' ') line++;
    if (!strcmp(line, "get")) reply(state());
    else if (!strncmp(line, "set ", 4)) set(line + 4);
    else if (!strcmp(line, "new-password")) {
        char made[BOARD_PASSWORD_LEN + 1];
        fresh_password(made);   // Wi-Fi is running: esp_fill_random is hardware entropy now
        esp_err_t error = save_password(made);
        if (error == ESP_OK) error = wifi_bridge_apply_ap();
        if (error != ESP_OK) fail(esp_err_to_name(error)); else reply(state());
    }
    else if (!strcmp(line, "reboot")) {
        reply(cJSON_CreateObject());
        vTaskDelay(pdMS_TO_TICKS(100));
        esp_restart();
    }
    else if (!strcmp(line, "help")) {
        cJSON *help = cJSON_CreateObject();
        if (help) cJSON_AddStringToObject(help, "commands", "@get | @set {\"wifi_ssid\":..,\"wifi_password\":..,"
                                          "\"ap_password\":..,\"usb_mode\":..} | @new-password | @reboot");
        reply(help);
    }
    else fail("unknown command; try @help");
}

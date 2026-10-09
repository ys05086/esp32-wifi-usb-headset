#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "usb_device_uac.h"
#include "probe_tone.h"
#include "wifi_bridge.h"
#include "usb_profile.h"
#include "board_config.h"
#include "uart_command.h"

static const char *TAG = "vs_mic";
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static int64_t tone_start = -1;
static uint32_t usb_blocks;
static uint32_t callback_max_us;

static void trigger(bool active)
{
    portENTER_CRITICAL(&lock);
    tone_start = active ? esp_timer_get_time() : -1;
    portEXIT_CRITICAL(&lock);
    ESP_LOGI(TAG, "%s", active ? "Four-second probe started (660/880 Hz, -26 dBFS)" : "Silent");
}

static esp_err_t microphone(uint8_t *buf, size_t len, size_t *bytes_read, void *ctx)
{
    (void)ctx;
    static probe_stream_t stream = {.start_us = -1}; // Owned only by the UAC microphone task.
    int64_t start;
    portENTER_CRITICAL(&lock);
    start = tone_start;
    usb_blocks++;
    portEXIT_CRITICAL(&lock);
    int64_t began = esp_timer_get_time();
    if (start >= 0 && began - start < PROBE_DURATION_US) probe_render(&stream, start, began, buf, len);
    else wifi_bridge_read(buf, len);
    uint32_t duration = (uint32_t)(esp_timer_get_time() - began);
    portENTER_CRITICAL(&lock);
    if (duration > callback_max_us) callback_max_us = duration;
    portEXIT_CRITICAL(&lock);
    *bytes_read = len;
    return ESP_OK;
}

static esp_err_t speaker(uint8_t *buf, size_t len, void *ctx)
{
    (void)ctx;
    wifi_bridge_speaker(buf, len);
    return ESP_OK;
}

void app_main(void)
{
    // Use the separate COM bridge for commands (probe tone, board setup); the native USB port is UAC only.
    const uart_config_t uart = {
        .baud_rate = 115200, .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1, .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT
    };
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &uart));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0));
    // GPIO0 is the BOOT button on the S3 development board. No RGB LED pins are driven.
    const gpio_config_t button = {
        .pin_bit_mask = 1ULL << GPIO_NUM_0, .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE, .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };
    ESP_ERROR_CHECK(gpio_config(&button));
    probe_init();
    usb_profile_init();
    uac_device_config_t uac = {.input_cb = microphone, .output_cb = speaker};
    ESP_ERROR_CHECK(uac_device_init(&uac));
    wifi_bridge_init();
    ESP_LOGI(TAG, "READY: ESP32 Wi-Fi Headset; 48000 Hz / PCM16; mono mic, stereo speaker");
    ESP_LOGI(TAG, "BOOT/UART 't': finite probe override. Otherwise: Wi-Fi PCM to USB, silence on disconnect.");
    ESP_LOGI(TAG, "Setup on this port: @get, @set {json}, @new-password, @reboot, @help");
    static uart_command_t input;  // main task only
    uart_command_init(&input);
    int previous = 1, stable = 1;
    int64_t changed_at = 0, last_report = 0;
    while (1) {
        int64_t now = esp_timer_get_time();
        int level = gpio_get_level(GPIO_NUM_0);
        if (level != previous) { previous = level; changed_at = now; }
        if (now - changed_at > 30000 && stable != level) {
            stable = level;
            if (stable == 0) trigger(true);
        }
        uint8_t bytes[64];
        int got;
        while ((got = uart_read_bytes(UART_NUM_0, bytes, sizeof bytes, 0)) > 0) {
            for (int i = 0; i < got; i++) {
                switch (uart_command_feed(&input, bytes[i])) {
                case UART_PROBE: trigger(true); break;
                case UART_SILENCE: trigger(false); break;
                case UART_LINE: board_config_command(input.line); break;
                case UART_TOO_LONG: printf("@err line too long
"); fflush(stdout); break;
                default: break;
                }
            }
        }
        if (now - last_report >= 10000000) {
            uint32_t blocks, max_us;
            portENTER_CRITICAL(&lock);
            blocks = usb_blocks;
            max_us = callback_max_us;
            portEXIT_CRITICAL(&lock);
            ESP_LOGI(TAG, "USB microphone callbacks: %"PRIu32 "; max render: %"PRIu32 " us / 10000 us budget", blocks, max_us);
            last_report = now;
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

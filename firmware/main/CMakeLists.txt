idf_component_register(SRCS "main.c" "probe_tone.c" "wifi_bridge.c" "wifi_pcm.c" "usb_profile.c" "usb_diagnostics.c" "usb_mic_trace.c" "board_identity.c" "board_config.c" "uart_command.c" INCLUDE_DIRS "."
                       LDFRAGMENTS "usb_iram.lf"
                       REQUIRES usb_device_uac esp_driver_gpio esp_driver_uart esp_timer esp_wifi esp_event esp_netif esp_http_server nvs_flash lwip json bootloader_support esp_app_format)
option(VS_MIC_TRACE_DETAILED "Enable intrusive per-packet microphone trace" OFF)
target_compile_definitions(${COMPONENT_LIB} PRIVATE VS_MIC_TRACE_DETAILED=$<BOOL:${VS_MIC_TRACE_DETAILED}>)

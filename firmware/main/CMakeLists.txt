idf_component_register(SRCS "main.c" "probe_tone.c" "wifi_bridge.c" "wifi_pcm.c" "usb_profile.c" "usb_diagnostics.c" "usb_mic_trace.c" INCLUDE_DIRS "."
                       REQUIRES usb_device_uac esp_driver_gpio esp_driver_uart esp_timer esp_wifi esp_event esp_netif esp_http_server nvs_flash lwip json)
option(VS_MIC_TRACE_DETAILED "Enable intrusive per-packet microphone trace" OFF)
target_compile_definitions(${COMPONENT_LIB} PRIVATE VS_MIC_TRACE_DETAILED=$<BOOL:${VS_MIC_TRACE_DETAILED}>)

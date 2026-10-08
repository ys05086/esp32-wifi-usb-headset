cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(esp32_wifi_usb_headset)

# Dependency resolution finishes inside project(). Patch before compilation;
# reject unexpected dependency contents instead of silently building untested code.
execute_process(
    COMMAND "${PYTHON}" "${CMAKE_CURRENT_SOURCE_DIR}/patch_uac.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/managed_components/espressif__usb_device_uac"
    RESULT_VARIABLE uac_patch_result)
if(NOT uac_patch_result EQUAL 0)
    message(FATAL_ERROR "Pinned UAC microphone FIFO patch failed")
endif()
execute_process(
    COMMAND "${PYTHON}" "${CMAKE_CURRENT_SOURCE_DIR}/patch_tinyusb.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/managed_components/espressif__tinyusb"
    RESULT_VARIABLE tinyusb_patch_result)
if(NOT tinyusb_patch_result EQUAL 0)
    message(FATAL_ERROR "Pinned TinyUSB feedback patch failed")
endif()

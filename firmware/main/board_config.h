#pragma once
#include "esp_err.h"

// The board's own Wi-Fi name and password, and the setup commands that arrive on the COM port.
// The password is made at random on first boot and kept in NVS ("vs_board"), so it survives app updates.
void board_config_load(void);               // after NVS is up, before Wi-Fi starts
const char *board_ap_ssid(void);
const char *board_ap_password(void);
// Answers one command line (without its '@') with a single "@ok {json}" or "@err message" line.
void board_config_command(const char *line);

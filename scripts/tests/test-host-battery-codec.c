/*
 * Host-only unit test of the SeaBIOS APM eight-byte bridge.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "hw/i386/host-battery.h"
#include <assert.h>
#include <string.h>

int main(void)
{
    uint8_t wire[WHP_APM_WIRE_SIZE];
    WHPHostBattery host = {true, 1, 67, true, -1};
    const uint8_t charging[] = {1, 1, 3, 8, 67, 1, 0xff, 0xff};

    assert(whp_host_battery_encode(&host, wire));
    assert(!memcmp(wire, charging, sizeof(wire)));
    host.ac_line = 0;
    host.charging = false;
    host.remaining_minutes = 300;
    assert(whp_host_battery_encode(&host, wire));
    assert(wire[2] == 0 && wire[3] == 1);
    assert(wire[6] == 0x2c && wire[7] == 0x81);
    host.percentage = 17;
    assert(whp_host_battery_encode(&host, wire));
    assert(wire[2] == 1 && wire[3] == 2);
    host.percentage = 3;
    assert(whp_host_battery_encode(&host, wire));
    assert(wire[2] == 2 && wire[3] == 4);
    host.percentage = -1;
    assert(whp_host_battery_encode(&host, wire));
    assert(wire[2] == 0xff && wire[3] == 0xff && wire[4] == 0xff);
    host.percentage = 101;
    assert(!whp_host_battery_encode(&host, wire));
    host.percentage = 40;
    host.remaining_minutes = 32767;
    assert(!whp_host_battery_encode(&host, wire));
    host.remaining_minutes = -1;
    host.present = false;
    assert(!whp_host_battery_encode(&host, wire));
    host.present = true;
    host.ac_line = 2;
    assert(!whp_host_battery_encode(&host, wire));
    return 0;
}

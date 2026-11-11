/*
 * Host power-source discovery for the opt-in WHP SeaBIOS APM profile.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/i386/host-battery.h"

#if defined(CONFIG_WHP_BATTERY_IOKIT)
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/ps/IOPowerSources.h>
#include <IOKit/ps/IOPSKeys.h>

static int whp_cf_int(CFDictionaryRef dict, CFStringRef key)
{
    CFTypeRef value = CFDictionaryGetValue(dict, key);
    int result = -1;

    if (value && CFGetTypeID(value) == CFNumberGetTypeID()) {
        CFNumberGetValue((CFNumberRef)value, kCFNumberIntType, &result);
    }
    return result;
}

static bool whp_cf_true(CFDictionaryRef dict, CFStringRef key)
{
    CFTypeRef value = CFDictionaryGetValue(dict, key);

    return value && CFGetTypeID(value) == CFBooleanGetTypeID() &&
           CFBooleanGetValue((CFBooleanRef)value);
}

bool whp_host_battery_read(WHPHostBattery *out)
{
    CFTypeRef snapshot = IOPSCopyPowerSourcesInfo();
    CFArrayRef sources;
    bool found = false;

    if (!snapshot) {
        return false;
    }
    sources = IOPSCopyPowerSourcesList(snapshot);
    if (!sources) {
        CFRelease(snapshot);
        return false;
    }

    for (CFIndex i = 0; i < CFArrayGetCount(sources); i++) {
        CFDictionaryRef desc = IOPSGetPowerSourceDescription(
            snapshot, CFArrayGetValueAtIndex(sources, i));
        CFTypeRef transport, state;

        if (!desc || CFGetTypeID(desc) != CFDictionaryGetTypeID()) {
            continue;
        }
        transport = CFDictionaryGetValue(desc, CFSTR(kIOPSTransportTypeKey));
        if (!transport || CFGetTypeID(transport) != CFStringGetTypeID() ||
            !CFEqual(transport, CFSTR(kIOPSInternalType)) ||
            !whp_cf_true(desc, CFSTR(kIOPSIsPresentKey))) {
            continue; /* UPSs and absent batteries are not laptop batteries */
        }
        if (found) {
            found = false; /* one battery only until multi-battery ABI exists */
            break;
        }
        found = true;
        out->present = true;
        out->percentage = -1;
        out->remaining_minutes = -1;
        out->ac_line = 0xff;
        out->charging = whp_cf_true(desc, CFSTR(kIOPSIsChargingKey));

        int current = whp_cf_int(desc, CFSTR(kIOPSCurrentCapacityKey));
        int maximum = whp_cf_int(desc, CFSTR(kIOPSMaxCapacityKey));
        if (current >= 0 && maximum > 0 && current <= maximum) {
            out->percentage = (int)((int64_t)current * 100 / maximum);
        }
        state = CFDictionaryGetValue(desc, CFSTR(kIOPSPowerSourceStateKey));
        if (state && CFGetTypeID(state) == CFStringGetTypeID()) {
            if (CFEqual(state, CFSTR(kIOPSACPowerValue))) {
                out->ac_line = 1;
            } else if (CFEqual(state, CFSTR(kIOPSBatteryPowerValue))) {
                out->ac_line = 0;
            }
        }
        if (!out->charging && out->ac_line == 0) {
            int minutes = whp_cf_int(desc, CFSTR(kIOPSTimeToEmptyKey));
            if (minutes >= 0 && minutes <= 32766) {
                out->remaining_minutes = minutes;
            }
        }
    }

    CFRelease(sources);
    CFRelease(snapshot);
    return found;
}

#elif defined(CONFIG_LINUX)

static char *whp_supply_attr(const char *supply, const char *attr)
{
    char *path = g_build_filename("/sys/class/power_supply", supply,
                                  attr, NULL);
    char *contents = NULL;

    if (!g_file_get_contents(path, &contents, NULL, NULL)) {
        g_clear_pointer(&contents, g_free);
    } else {
        g_strstrip(contents);
    }
    g_free(path);
    return contents;
}

static int whp_supply_int(const char *supply, const char *attr)
{
    g_autofree char *value = whp_supply_attr(supply, attr);
    char *end = NULL;
    gint64 n;

    if (!value || !*value) {
        return -1;
    }
    n = g_ascii_strtoll(value, &end, 10);
    if (!end || *end != '\0' || n < 0 || n > G_MAXINT) {
        return -1;
    }
    return (int)n;
}

bool whp_host_battery_read(WHPHostBattery *out)
{
    GDir *dir = g_dir_open("/sys/class/power_supply", 0, NULL);
    const char *supply;
    int batteries = 0;
    int ac_online = 0;
    bool seen_ac = false;

    if (!dir) {
        return false;
    }
    out->present = false;
    out->ac_line = 0xff;
    out->percentage = -1;
    out->charging = false;
    out->remaining_minutes = -1;

    while ((supply = g_dir_read_name(dir))) {
        g_autofree char *type = whp_supply_attr(supply, "type");

        if (!g_strcmp0(type, "Battery")) {
            int present = whp_supply_int(supply, "present");
            if (present == 0) {
                continue;
            }
            batteries++;
            if (batteries > 1) {
                g_dir_close(dir);
                return false; /* never silently drop a second battery */
            }

            out->present = true;
            int capacity = whp_supply_int(supply, "capacity");
            if (capacity >= 0 && capacity <= 100) {
                out->percentage = capacity;
            }
            g_autofree char *status = whp_supply_attr(supply, "status");
            out->charging = !g_strcmp0(status, "Charging");
            if (!g_strcmp0(status, "Discharging")) {
                out->ac_line = 0;
            } else if (!g_strcmp0(status, "Charging") ||
                       !g_strcmp0(status, "Full")) {
                out->ac_line = 1;
            }
            int remaining = whp_supply_int(supply, "time_to_empty_now");
            if (remaining >= 0 && remaining / 60 <= 32766) {
                out->remaining_minutes = remaining / 60;
            }
        } else if (!g_strcmp0(type, "Mains") ||
                   !g_strcmp0(type, "USB") ||
                   !g_strcmp0(type, "USB_C") ||
                   !g_strcmp0(type, "USB_PD")) {
            int online = whp_supply_int(supply, "online");
            if (online >= 0) {
                seen_ac = true;
                ac_online |= online > 0;
            }
        }
    }
    if (seen_ac) {
        out->ac_line = ac_online ? 1 : 0;
    }
    g_dir_close(dir);
    return batteries == 1;
}

#else
bool whp_host_battery_read(WHPHostBattery *out)
{
    (void)out;
    return false;
}
#endif

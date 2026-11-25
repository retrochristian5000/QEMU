/* SPDX-License-Identifier: GPL-2.0-or-later */
#undef NDEBUG
#include <assert.h>
#include <stdint.h>
#include "hw/block/mmc-rom.h"

int main(void)
{
    static const uint16_t profiles[] = {
        MMC_PROFILE_NONE, MMC_PROFILE_CD_ROM, MMC_PROFILE_DVD_ROM,
    };
    static const uint8_t disc_info[MMC_ROM_DISC_INFO_SIZE] = {
        0, 32, 0x0e, 1, 1, 1, 1, 0x20,
    };
    uint8_t buf[MMC_ROM_DISC_INFO_SIZE + 2];

    for (unsigned i = 0; i < sizeof(profiles) / sizeof(profiles[0]); i++) {
        uint8_t expected[MMC_ROM_PROFILE_LIST_SIZE] = {
            0, 0, 0, 16, 0, 0, 0, profiles[i],
            0, 0, 3, 8,
            0, MMC_PROFILE_DVD_ROM, profiles[i] == MMC_PROFILE_DVD_ROM, 0,
            0, MMC_PROFILE_CD_ROM, profiles[i] == MMC_PROFILE_CD_ROM, 0,
        };

        memset(buf, 0xa5, sizeof(buf));
        mmc_rom_profile_list(buf + 1, profiles[i]);
        assert(memcmp(buf + 1, expected, sizeof(expected)) == 0);
        assert(buf[0] == 0xa5);
        for (unsigned j = sizeof(expected) + 1; j < sizeof(buf); j++) {
            assert(buf[j] == 0xa5);
        }
    }

    memset(buf, 0xa5, sizeof(buf));
    mmc_rom_disc_information(buf + 1);
    assert(memcmp(buf + 1, disc_info, sizeof(disc_info)) == 0);
    assert(!(buf[3] & 0x10)); /* Erasable bit */
    assert(buf[0] == 0xa5 && buf[sizeof(buf) - 1] == 0xa5);
    return 0;
}

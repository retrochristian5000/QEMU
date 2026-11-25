/* SPDX-License-Identifier: GPL-2.0-or-later */
#undef NDEBUG
#include <assert.h>
#include <stdint.h>
#include "hw/block/cdrom-sector.h"

int main(void)
{
    static const CdromSectorMatch expected[] = {
        CDROM_SECTOR_MATCH, CDROM_SECTOR_MISMATCH,
        CDROM_SECTOR_MATCH, CDROM_SECTOR_MISMATCH,
        CDROM_SECTOR_MISMATCH, CDROM_SECTOR_MISMATCH,
        CDROM_SECTOR_RESERVED, CDROM_SECTOR_RESERVED,
    };
    static const uint32_t lbas[] = { 0, 74, 75, 4350, 4499, 449999 };
    unsigned i, j;

    for (i = 0; i < 256; i++) {
        assert(cdrom_mode1_expected_type(i) == expected[(i / 4) % 8]);
    }
    for (i = 0; i < sizeof(lbas) / sizeof(lbas[0]); i++) {
        uint8_t buf[CDROM_RAW_SECTOR_SIZE + 2];
        uint8_t *sector = buf + 1;
        uint32_t frames = lbas[i] + 150;

        memset(buf, 0xa5, sizeof(buf));
        for (j = 0; j < CDROM_MODE1_DATA_SIZE; j++) {
            sector[CDROM_MODE1_DATA_OFFSET + j] = j % 251;
        }
        cdrom_synthesize_mode1_sector(sector, lbas[i]);
        assert(buf[0] == 0xa5 && buf[sizeof(buf) - 1] == 0xa5);
        assert(sector[0] == 0 && sector[11] == 0);
        for (j = 1; j < 11; j++) {
            assert(sector[j] == 0xff);
        }
        assert(sector[12] == frames / 4500);
        assert(sector[13] == frames / 75 % 60);
        assert(sector[14] == frames % 75);
        assert(sector[15] == 1);
        for (j = 0; j < CDROM_MODE1_DATA_SIZE; j++) {
            assert(sector[CDROM_MODE1_DATA_OFFSET + j] == j % 251);
        }
        for (j = CDROM_MODE1_DATA_OFFSET + CDROM_MODE1_DATA_SIZE;
             j < CDROM_RAW_SECTOR_SIZE; j++) {
            assert(sector[j] == 0);
        }
    }
    return 0;
}

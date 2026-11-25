/* SPDX-License-Identifier: GPL-2.0-or-later */
#undef NDEBUG
#include <assert.h>
#include "block/eltorito.h"

int main(void)
{
    uint8_t record[ELTORITO_BLOCK_SIZE] = { 0 };
    uint8_t cat[ELTORITO_BLOCK_SIZE] = { 0 };
    uint32_t lba;
    ElToritoInitialExtent extent;
    const uint64_t size = 100 * ELTORITO_BLOCK_SIZE;

    memcpy(record + 1, "CD001", 5);
    record[6] = 1;
    memcpy(record + 7, "EL TORITO SPECIFICATION", 23);
    record[71] = 20;
    assert(eltorito_catalog_lba(record, size, &lba));
    assert(lba == 20);
    assert(!eltorito_catalog_lba(record, 21 * ELTORITO_BLOCK_SIZE - 1, &lba));
    record[6] = 2;
    assert(!eltorito_catalog_lba(record, size, &lba));
    record[6] = 1;
    record[74] = 0xff;
    assert(!eltorito_catalog_lba(record, size, &lba));

    cat[0] = 1;
    cat[30] = 0x55;
    cat[31] = 0xaa;
    /* Checksum of 0001 + aa55 + 55aa = 0 mod 65536. */
    cat[28] = 0xaa;
    cat[29] = 0x55;
    cat[32] = 0x88;
    cat[40] = 30;

    for (unsigned count = 1; count <= 280; count++) {
        cat[38] = count;
        cat[39] = count >> 8;
        assert(eltorito_initial_extent(cat, size, &extent));
        assert(extent.offset == 30 * ELTORITO_BLOCK_SIZE);
        assert(extent.bytes == ((count + 3) / 4) * ELTORITO_BLOCK_SIZE);
        assert(!eltorito_initial_extent(cat, extent.offset + extent.bytes - 1,
                                        &extent));
    }
    cat[38] = 4;
    cat[39] = 0;
    cat[64] = 0x91;
    assert(!eltorito_initial_extent(cat, size, &extent));
    cat[64] = 0;
    cat[33] = 2;
    assert(!eltorito_initial_extent(cat, size, &extent));
    cat[33] = 0;
    cat[1] = 0xef;
    assert(!eltorito_initial_extent(cat, size, &extent));
    cat[1] = 0;
    cat[28] ^= 1;
    assert(!eltorito_initial_extent(cat, size, &extent));
    cat[28] ^= 1;
    cat[38] = 0;
    assert(!eltorito_initial_extent(cat, size, &extent));
    return 0;
}

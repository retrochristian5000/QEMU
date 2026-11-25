/* SPDX-License-Identifier: GPL-2.0-or-later */
#undef NDEBUG
#include <assert.h>
#include "block/eltorito.h"

typedef struct DescriptorFixture {
    uint8_t sectors[ELTORITO_DESCRIPTOR_LIMIT][ELTORITO_BLOCK_SIZE];
    unsigned reads;
} DescriptorFixture;

static bool fixture_read(void *opaque, uint32_t lba, uint8_t *buf)
{
    DescriptorFixture *f = opaque;

    assert(lba >= 16 && lba < 16 + ELTORITO_DESCRIPTOR_LIMIT);
    f->reads++;
    memcpy(buf, f->sectors[lba - 16], ELTORITO_BLOCK_SIZE);
    return true;
}

static void fixture_descriptor(DescriptorFixture *f, unsigned index,
                               uint8_t type)
{
    uint8_t *block = f->sectors[index];

    memset(block, 0, ELTORITO_BLOCK_SIZE);
    block[0] = type;
    memcpy(block + 1, "CD001", 5);
    block[6] = 1;
}

static void test_descriptor_scan(void)
{
    static DescriptorFixture f;
    uint8_t block[ELTORITO_BLOCK_SIZE];
    uint32_t catalog_lba = 0;
    const uint64_t size = 100 * ELTORITO_BLOCK_SIZE;

    fixture_descriptor(&f, 0, 1);
    fixture_descriptor(&f, 1, 2);
    memcpy(f.sectors[1] + 88, "%/E", 3);
    fixture_descriptor(&f, 2, 255);
    assert(eltorito_scan_descriptors(fixture_read, &f, size, block,
                                    &catalog_lba) == ELTORITO_SCAN_NO_BOOT);
    assert(f.reads == 3);

    /* A primary-only data disc needs no filename interpretation either. */
    f.reads = 0;
    fixture_descriptor(&f, 1, 255);
    assert(eltorito_scan_descriptors(fixture_read, &f, size, block,
                                    &catalog_lba) == ELTORITO_SCAN_NO_BOOT);
    assert(f.reads == 2);

    /* Advisory scan can find a boot record after supplementary metadata. */
    fixture_descriptor(&f, 1, 2);
    fixture_descriptor(&f, 2, 0);
    memcpy(f.sectors[2] + 7, "EL TORITO SPECIFICATION", 23);
    f.sectors[2][71] = 40;
    f.reads = 0;
    assert(eltorito_scan_descriptors(fixture_read, &f, size, block,
                                    &catalog_lba) == ELTORITO_SCAN_FOUND);
    assert(catalog_lba == 40 && f.reads == 3);

    f.reads = 0;
    assert(eltorito_scan_descriptors(fixture_read, &f, 18 * ELTORITO_BLOCK_SIZE,
                                    block, &catalog_lba) ==
           ELTORITO_SCAN_FALLBACK);
    assert(f.reads == 2);

    /* Unknown descriptors and versions keep the library fallback. */
    fixture_descriptor(&f, 1, 3);
    assert(eltorito_scan_descriptors(fixture_read, &f, size, block,
                                    &catalog_lba) == ELTORITO_SCAN_FALLBACK);
    fixture_descriptor(&f, 1, 2);
    f.sectors[1][6] = 2;
    assert(eltorito_scan_descriptors(fixture_read, &f, size, block,
                                    &catalog_lba) == ELTORITO_SCAN_FALLBACK);

    for (unsigned i = 1; i < ELTORITO_DESCRIPTOR_LIMIT; i++) {
        fixture_descriptor(&f, i, 2);
    }
    f.reads = 0;
    assert(eltorito_scan_descriptors(fixture_read, &f, size, block,
                                    &catalog_lba) == ELTORITO_SCAN_FALLBACK);
    assert(f.reads == ELTORITO_DESCRIPTOR_LIMIT);
}

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
    test_descriptor_scan();
    return 0;
}

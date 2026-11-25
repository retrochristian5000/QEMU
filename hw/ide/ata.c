/*
 * QEMU ATA disk identification and SMART emulation
 *
 * Copyright (c) 2003 Fabrice Bellard
 * Copyright (c) 2006 Openedhand Ltd.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "qemu/osdep.h"
#include "hw/block/block.h"
#include "system/block-backend.h"
#include "ide-internal.h"

/* ATA and CompactFlash disk commands, independent of ATAPI media. */

/* These values were based on a Seagate ST3500418AS but have been modified
   to make more sense in QEMU */
static const int smart_attributes[][12] = {
    /* id,  flags, hflags, val, wrst, raw (6 bytes), threshold */
    /* raw read error rate*/
    { 0x01, 0x03, 0x00, 0x64, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x06},
    /* spin up */
    { 0x03, 0x03, 0x00, 0x64, 0x64, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    /* start stop count */
    { 0x04, 0x02, 0x00, 0x64, 0x64, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00, 0x14},
    /* remapped sectors */
    { 0x05, 0x03, 0x00, 0x64, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x24},
    /* power on hours */
    { 0x09, 0x03, 0x00, 0x64, 0x64, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    /* power cycle count */
    { 0x0c, 0x03, 0x00, 0x64, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    /* airflow-temperature-celsius */
    { 190,  0x03, 0x00, 0x45, 0x45, 0x1f, 0x00, 0x1f, 0x1f, 0x00, 0x00, 0x32},
};

static void ide_identify_size(IDEState *s)
{
    uint16_t *p = (uint16_t *)s->identify_data;
    int64_t nb_sectors_lba28 = s->nb_sectors;
    if (nb_sectors_lba28 >= 1 << 28) {
        nb_sectors_lba28 = (1 << 28) - 1;
    }
    ide_put_le16(p + 60, nb_sectors_lba28);
    ide_put_le16(p + 61, nb_sectors_lba28 >> 16);
    ide_put_le16(p + 100, s->nb_sectors);
    ide_put_le16(p + 101, s->nb_sectors >> 16);
    ide_put_le16(p + 102, s->nb_sectors >> 32);
    ide_put_le16(p + 103, s->nb_sectors >> 48);
}

void ide_identify(IDEState *s)
{
    uint16_t *p;
    unsigned int oldsize;
    IDEDevice *dev = s->unit ? s->bus->slave : s->bus->master;

    p = (uint16_t *)s->identify_data;
    if (s->identify_set) {
        goto fill_buffer;
    }
    memset(p, 0, sizeof(s->identify_data));

    ide_put_le16(p + 0, 0x0040);
    ide_put_le16(p + 1, s->cylinders);
    ide_put_le16(p + 3, s->heads);
    ide_put_le16(p + 4, 512 * s->sectors); /* XXX: retired, remove ? */
    ide_put_le16(p + 5, 512); /* XXX: retired, remove ? */
    ide_put_le16(p + 6, s->sectors);
    ide_padstr((char *)(p + 10), s->drive_serial_str, 20); /* serial number */
    ide_put_le16(p + 20, 3); /* XXX: retired, remove ? */
    ide_put_le16(p + 21, 512); /* cache size in sectors */
    ide_put_le16(p + 22, 4); /* ecc bytes */
    ide_padstr((char *)(p + 23), s->version, 8); /* firmware version */
    ide_padstr((char *)(p + 27), s->drive_model_str, 40); /* model */
#if MAX_MULT_SECTORS > 1
    ide_put_le16(p + 47, 0x8000 | MAX_MULT_SECTORS);
#endif
    ide_put_le16(p + 48, 1); /* dword I/O */
    ide_put_le16(p + 49, (1 << 11) | (1 << 9) | (1 << 8)); /* DMA and LBA supported */
    ide_put_le16(p + 51, 0x200); /* PIO transfer cycle */
    ide_put_le16(p + 52, 0x200); /* DMA transfer cycle */
    ide_put_le16(p + 53, 1 | (1 << 1) | (1 << 2)); /* words 54-58,64-70,88 are valid */
    ide_put_le16(p + 54, s->cylinders);
    ide_put_le16(p + 55, s->heads);
    ide_put_le16(p + 56, s->sectors);
    oldsize = s->cylinders * s->heads * s->sectors;
    ide_put_le16(p + 57, oldsize);
    ide_put_le16(p + 58, oldsize >> 16);
    if (s->mult_sectors)
        ide_put_le16(p + 59, 0x100 | s->mult_sectors);
    /* *(p + 60) := nb_sectors       -- see ide_identify_size */
    /* *(p + 61) := nb_sectors >> 16 -- see ide_identify_size */
    ide_put_le16(p + 62, 0x07); /* single word dma0-2 supported */
    ide_put_le16(p + 63, 0x07); /* mdma0-2 supported */
    ide_put_le16(p + 64, 0x03); /* pio3-4 supported */
    ide_put_le16(p + 65, 120);
    ide_put_le16(p + 66, 120);
    ide_put_le16(p + 67, 120);
    ide_put_le16(p + 68, 120);
    if (dev && dev->conf.discard_granularity) {
        ide_put_le16(p + 69, (1 << 14)); /* determinate TRIM behavior */
    }

    if (s->ncq_queues) {
        ide_put_le16(p + 75, s->ncq_queues - 1);
        /* NCQ supported */
        ide_put_le16(p + 76, (1 << 8));
    }

    ide_put_le16(p + 80, 0xf0); /* ata3 -> ata6 supported */
    ide_put_le16(p + 81, 0x16); /* conforms to ata5 */
    /* 14=NOP supported, 5=WCACHE supported, 0=SMART supported */
    ide_put_le16(p + 82, (1 << 14) | (1 << 5) | 1);
    /* 13=flush_cache_ext,12=flush_cache,10=lba48 */
    ide_put_le16(p + 83, (1 << 14) | (1 << 13) | (1 <<12) | (1 << 10));
    /* 14=set to 1, 8=has WWN, 1=SMART self test, 0=SMART error logging */
    if (s->wwn) {
        ide_put_le16(p + 84, (1 << 14) | (1 << 8) | 0);
    } else {
        ide_put_le16(p + 84, (1 << 14) | 0);
    }
    /* 14 = NOP supported, 5=WCACHE enabled, 0=SMART feature set enabled */
    if (blk_enable_write_cache(s->blk)) {
        ide_put_le16(p + 85, (1 << 14) | (1 << 5) | 1);
    } else {
        ide_put_le16(p + 85, (1 << 14) | 1);
    }
    /* 13=flush_cache_ext,12=flush_cache,10=lba48 */
    ide_put_le16(p + 86, (1 << 13) | (1 <<12) | (1 << 10));
    /* 14=set to 1, 8=has WWN, 1=SMART self test, 0=SMART error logging */
    if (s->wwn) {
        ide_put_le16(p + 87, (1 << 14) | (1 << 8) | 0);
    } else {
        ide_put_le16(p + 87, (1 << 14) | 0);
    }
    ide_put_le16(p + 88, 0x3f | (1 << 13)); /* udma5 set and supported */
    ide_put_le16(p + 93, 1 | (1 << 14) | 0x2000);
    /* *(p + 100) := nb_sectors       -- see ide_identify_size */
    /* *(p + 101) := nb_sectors >> 16 -- see ide_identify_size */
    /* *(p + 102) := nb_sectors >> 32 -- see ide_identify_size */
    /* *(p + 103) := nb_sectors >> 48 -- see ide_identify_size */

    if (dev && dev->conf.physical_block_size)
        ide_put_le16(p + 106, 0x6000 | get_physical_block_exp(&dev->conf));
    if (s->wwn) {
        /* LE 16-bit words 111-108 contain 64-bit World Wide Name */
        ide_put_le16(p + 108, s->wwn >> 48);
        ide_put_le16(p + 109, s->wwn >> 32);
        ide_put_le16(p + 110, s->wwn >> 16);
        ide_put_le16(p + 111, s->wwn);
    }
    if (dev && dev->conf.discard_granularity) {
        ide_put_le16(p + 169, 1); /* TRIM support */
    }
    if (dev) {
        ide_put_le16(p + 217, dev->rotation_rate); /* Nominal media rotation rate */
    }

    ide_identify_size(s);
    s->identify_set = 1;

fill_buffer:
    memcpy(s->io_buffer, p, sizeof(s->identify_data));
}

static void ide_cfata_identify_size(IDEState *s)
{
    uint16_t *p = (uint16_t *)s->identify_data;
    ide_put_le16(p + 7, s->nb_sectors >> 16);  /* Sectors per card */
    ide_put_le16(p + 8, s->nb_sectors);        /* Sectors per card */
    ide_put_le16(p + 60, s->nb_sectors);       /* Total LBA sectors */
    ide_put_le16(p + 61, s->nb_sectors >> 16); /* Total LBA sectors */
}

void ide_cfata_identify(IDEState *s)
{
    uint16_t *p;
    uint32_t cur_sec;

    p = (uint16_t *)s->identify_data;
    if (s->identify_set) {
        goto fill_buffer;
    }
    memset(p, 0, sizeof(s->identify_data));

    cur_sec = s->cylinders * s->heads * s->sectors;

    ide_put_le16(p + 0, 0x848a);                    /* CF Storage Card signature */
    ide_put_le16(p + 1, s->cylinders);              /* Default cylinders */
    ide_put_le16(p + 3, s->heads);                  /* Default heads */
    ide_put_le16(p + 6, s->sectors);                /* Default sectors per track */
    /* *(p + 7) := nb_sectors >> 16 -- see ide_cfata_identify_size */
    /* *(p + 8) := nb_sectors       -- see ide_cfata_identify_size */
    ide_padstr((char *)(p + 10), s->drive_serial_str, 20); /* serial number */
    ide_put_le16(p + 22, 0x0004);                   /* ECC bytes */
    ide_padstr((char *) (p + 23), s->version, 8);   /* Firmware Revision */
    ide_padstr((char *) (p + 27), s->drive_model_str, 40);/* Model number */
#if MAX_MULT_SECTORS > 1
    ide_put_le16(p + 47, 0x8000 | MAX_MULT_SECTORS);
#else
    ide_put_le16(p + 47, 0x0000);
#endif
    ide_put_le16(p + 49, 0x0f00);                   /* Capabilities */
    ide_put_le16(p + 51, 0x0002);                   /* PIO cycle timing mode */
    ide_put_le16(p + 52, 0x0001);                   /* DMA cycle timing mode */
    ide_put_le16(p + 53, 0x0003);                   /* Translation params valid */
    ide_put_le16(p + 54, s->cylinders);             /* Current cylinders */
    ide_put_le16(p + 55, s->heads);                 /* Current heads */
    ide_put_le16(p + 56, s->sectors);               /* Current sectors */
    ide_put_le16(p + 57, cur_sec);                  /* Current capacity */
    ide_put_le16(p + 58, cur_sec >> 16);            /* Current capacity */
    if (s->mult_sectors)                        /* Multiple sector setting */
        ide_put_le16(p + 59, 0x100 | s->mult_sectors);
    /* *(p + 60) := nb_sectors       -- see ide_cfata_identify_size */
    /* *(p + 61) := nb_sectors >> 16 -- see ide_cfata_identify_size */
    ide_put_le16(p + 63, 0x0203);                   /* Multiword DMA capability */
    ide_put_le16(p + 64, 0x0001);                   /* Flow Control PIO support */
    ide_put_le16(p + 65, 0x0096);                   /* Min. Multiword DMA cycle */
    ide_put_le16(p + 66, 0x0096);                   /* Rec. Multiword DMA cycle */
    ide_put_le16(p + 68, 0x00b4);                   /* Min. PIO cycle time */
    ide_put_le16(p + 82, 0x400c);                   /* Command Set supported */
    ide_put_le16(p + 83, 0x7068);                   /* Command Set supported */
    ide_put_le16(p + 84, 0x4000);                   /* Features supported */
    ide_put_le16(p + 85, 0x000c);                   /* Command Set enabled */
    ide_put_le16(p + 86, 0x7044);                   /* Command Set enabled */
    ide_put_le16(p + 87, 0x4000);                   /* Features enabled */
    ide_put_le16(p + 91, 0x4060);                   /* Current APM level */
    ide_put_le16(p + 129, 0x0002);                  /* Current features option */
    ide_put_le16(p + 130, 0x0005);                  /* Reassigned sectors */
    ide_put_le16(p + 131, 0x0001);                  /* Initial power mode */
    ide_put_le16(p + 132, 0x0000);                  /* User signature */
    ide_put_le16(p + 160, 0x8100);                  /* Power requirement */
    ide_put_le16(p + 161, 0x8001);                  /* CF command set */

    ide_cfata_identify_size(s);
    s->identify_set = 1;

fill_buffer:
    memcpy(s->io_buffer, p, sizeof(s->identify_data));
}

static void ide_resize_cb(void *opaque)
{
    IDEState *s = opaque;
    uint64_t nb_sectors;

    if (!s->identify_set) {
        return;
    }

    blk_get_geometry(s->blk, &nb_sectors);
    s->nb_sectors = nb_sectors;

    /* Update the identify data buffer. */
    if (s->drive_kind == IDE_CFATA) {
        ide_cfata_identify_size(s);
    } else {
        /* IDE_CD uses a different set of callbacks entirely. */
        assert(s->drive_kind != IDE_CD);
        ide_identify_size(s);
    }
}

const BlockDevOps ide_hd_block_ops = {
    .resize_cb = ide_resize_cb,
};

/*** SMART commands ***/

bool ide_ata_cmd_smart(IDEState *s, uint8_t cmd)
{
    int n;

    if (s->hcyl != 0xc2 || s->lcyl != 0x4f) {
        goto abort_cmd;
    }

    if (!s->smart_enabled && s->feature != SMART_ENABLE) {
        goto abort_cmd;
    }

    switch (s->feature) {
    case SMART_DISABLE:
        s->smart_enabled = 0;
        return true;

    case SMART_ENABLE:
        s->smart_enabled = 1;
        return true;

    case SMART_ATTR_AUTOSAVE:
        switch (s->sector) {
        case 0x00:
            s->smart_autosave = 0;
            break;
        case 0xf1:
            s->smart_autosave = 1;
            break;
        default:
            goto abort_cmd;
        }
        return true;

    case SMART_STATUS:
        if (!s->smart_errors) {
            s->hcyl = 0xc2;
            s->lcyl = 0x4f;
        } else {
            s->hcyl = 0x2c;
            s->lcyl = 0xf4;
        }
        return true;

    case SMART_READ_THRESH:
        memset(s->io_buffer, 0, 0x200);
        s->io_buffer[0] = 0x01; /* smart struct version */

        for (n = 0; n < ARRAY_SIZE(smart_attributes); n++) {
            s->io_buffer[2 + 0 + (n * 12)] = smart_attributes[n][0];
            s->io_buffer[2 + 1 + (n * 12)] = smart_attributes[n][11];
        }

        /* checksum */
        for (n = 0; n < 511; n++) {
            s->io_buffer[511] += s->io_buffer[n];
        }
        s->io_buffer[511] = 0x100 - s->io_buffer[511];

        s->status = READY_STAT | SEEK_STAT;
        ide_transfer_start(s, s->io_buffer, 0x200, ide_transfer_stop);
        ide_bus_set_irq(s->bus);
        return false;

    case SMART_READ_DATA:
        memset(s->io_buffer, 0, 0x200);
        s->io_buffer[0] = 0x01; /* smart struct version */

        for (n = 0; n < ARRAY_SIZE(smart_attributes); n++) {
            int i;
            for (i = 0; i < 11; i++) {
                s->io_buffer[2 + i + (n * 12)] = smart_attributes[n][i];
            }
        }

        s->io_buffer[362] = 0x02 | (s->smart_autosave ? 0x80 : 0x00);
        if (s->smart_selftest_count == 0) {
            s->io_buffer[363] = 0;
        } else {
            s->io_buffer[363] =
                s->smart_selftest_data[3 +
                           (s->smart_selftest_count - 1) *
                           24];
        }
        s->io_buffer[364] = 0x20;
        s->io_buffer[365] = 0x01;
        /* offline data collection capacity: execute + self-test*/
        s->io_buffer[367] = (1 << 4 | 1 << 3 | 1);
        s->io_buffer[368] = 0x03; /* smart capability (1) */
        s->io_buffer[369] = 0x00; /* smart capability (2) */
        s->io_buffer[370] = 0x01; /* error logging supported */
        s->io_buffer[372] = 0x02; /* minutes for poll short test */
        s->io_buffer[373] = 0x36; /* minutes for poll ext test */
        s->io_buffer[374] = 0x01; /* minutes for poll conveyance */

        for (n = 0; n < 511; n++) {
            s->io_buffer[511] += s->io_buffer[n];
        }
        s->io_buffer[511] = 0x100 - s->io_buffer[511];

        s->status = READY_STAT | SEEK_STAT;
        ide_transfer_start(s, s->io_buffer, 0x200, ide_transfer_stop);
        ide_bus_set_irq(s->bus);
        return false;

    case SMART_READ_LOG:
        switch (s->sector) {
        case 0x01: /* summary smart error log */
            memset(s->io_buffer, 0, 0x200);
            s->io_buffer[0] = 0x01;
            s->io_buffer[1] = 0x00; /* no error entries */
            s->io_buffer[452] = s->smart_errors & 0xff;
            s->io_buffer[453] = (s->smart_errors & 0xff00) >> 8;

            for (n = 0; n < 511; n++) {
                s->io_buffer[511] += s->io_buffer[n];
            }
            s->io_buffer[511] = 0x100 - s->io_buffer[511];
            break;
        case 0x06: /* smart self test log */
            memset(s->io_buffer, 0, 0x200);
            s->io_buffer[0] = 0x01;
            if (s->smart_selftest_count == 0) {
                s->io_buffer[508] = 0;
            } else {
                s->io_buffer[508] = s->smart_selftest_count;
                for (n = 2; n < 506; n++)  {
                    s->io_buffer[n] = s->smart_selftest_data[n];
                }
            }

            for (n = 0; n < 511; n++) {
                s->io_buffer[511] += s->io_buffer[n];
            }
            s->io_buffer[511] = 0x100 - s->io_buffer[511];
            break;
        default:
            goto abort_cmd;
        }
        s->status = READY_STAT | SEEK_STAT;
        ide_transfer_start(s, s->io_buffer, 0x200, ide_transfer_stop);
        ide_bus_set_irq(s->bus);
        return false;

    case SMART_EXECUTE_OFFLINE:
        switch (s->sector) {
        case 0: /* off-line routine */
        case 1: /* short self test */
        case 2: /* extended self test */
            s->smart_selftest_count++;
            if (s->smart_selftest_count > 21) {
                s->smart_selftest_count = 1;
            }
            n = 2 + (s->smart_selftest_count - 1) * 24;
            s->smart_selftest_data[n] = s->sector;
            s->smart_selftest_data[n + 1] = 0x00; /* OK and finished */
            s->smart_selftest_data[n + 2] = 0x34; /* hour count lsb */
            s->smart_selftest_data[n + 3] = 0x12; /* hour count msb */
            break;
        default:
            goto abort_cmd;
        }
        return true;
    }

abort_cmd:
    ide_abort_command(s);
    return true;
}

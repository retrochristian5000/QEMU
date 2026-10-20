/*
 * Classic Macintosh Disk Copy NDIF self-mounting images in MacBinary.
 *
 * Read-only conversion of the bcem resource's zero, raw, and ADC chunks.
 * A self-mounting image is a Classic Mac application, not a raw disk.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "block/block-io.h"
#include "block/block_int.h"
#include "qemu/bswap.h"
#include "qemu/units.h"
#include "qemu/module.h"

#define SMI_FORK_MAX          (16 * MiB)
#define SMI_CHUNK_MAX         (16 * MiB)
#define SMI_SECTOR_SIZE       512
#define SMI_RESOURCE_HEADER   128
#define SMI_CHUNK_ENTRY       12

typedef struct SmiChunk {
    uint32_t sector;
    uint32_t count;
    uint32_t position;
    uint32_t length;
    uint8_t type;
} SmiChunk;

typedef struct BDRVSmiState {
    uint64_t data_base;
    uint32_t data_length;
    uint32_t backing_offset;
    SmiChunk *chunks;
    uint32_t n_chunks;
    uint8_t *compressed;
    uint8_t *decoded;
    uint32_t cached;
    QemuCoMutex lock;
} BDRVSmiState;

static bool smi_range(uint64_t pos, uint64_t len, uint64_t size)
{
    return pos <= size && len <= size - pos;
}

static uint32_t smi_be24(const uint8_t *p)
{
    return (uint32_t)p[0] << 16 | (uint32_t)p[1] << 8 | p[2];
}

static int smi_probe(const uint8_t *buf, int size, const char *filename)
{
    size_t len;

    /* Never confuse an arbitrary MacBinary application with a disk image. */
    if (!filename || size < 128 || buf[0] || buf[1] == 0 ||
        buf[1] > 63 || !ld_be32(buf + 83) || !ld_be32(buf + 87)) {
        return 0;
    }
    len = strlen(filename);
    if (len >= 4 && !g_ascii_strcasecmp(filename + len - 4, ".smi")) {
        return 30;
    }
    if (len >= 8 && !g_ascii_strcasecmp(filename + len - 8, ".smi.bin")) {
        return 30;
    }
    return 0;
}

/* Locate NDIF bcem resource 128 in the classic Macintosh resource map. */
static const uint8_t *smi_bcem(const uint8_t *fork, uint32_t fork_size,
                               uint32_t *bcem_size)
{
    uint32_t data_off, data_size, map_off, map_size;
    uint32_t type_start, ntypes, i;

    if (fork_size < 16) {
        return NULL;
    }
    data_off = ld_be32(fork);
    map_off = ld_be32(fork + 4);
    data_size = ld_be32(fork + 8);
    map_size = ld_be32(fork + 12);
    if (!smi_range(data_off, data_size, fork_size) ||
        !smi_range(map_off, map_size, fork_size) || map_size < 30) {
        return NULL;
    }

    type_start = map_off + ld_be16(fork + map_off + 24);
    if (!smi_range(type_start, 2, map_off + map_size)) {
        return NULL;
    }
    ntypes = (uint32_t)ld_be16(fork + type_start) + 1;
    if (ntypes > 4096 || !smi_range(type_start + 2, ntypes * 8,
                                     map_off + map_size)) {
        return NULL;
    }
    for (i = 0; i < ntypes; i++) {
        const uint8_t *type = fork + type_start + 2 + 8 * i;
        uint32_t refs, nrefs, j;

        if (memcmp(type, "bcem", 4)) {
            continue;
        }
        nrefs = (uint32_t)ld_be16(type + 4) + 1;
        refs = type_start + ld_be16(type + 6);
        if (nrefs > 8192 ||
            !smi_range(refs, nrefs * 12, map_off + map_size)) {
            return NULL;
        }
        for (j = 0; j < nrefs; j++) {
            const uint8_t *ref = fork + refs + j * 12;
            uint64_t rsrc_pos;
            uint32_t size;

            if (ld_be16(ref) != 128) {
                continue;
            }
            rsrc_pos = (uint64_t)data_off + smi_be24(ref + 5);
            if (!smi_range(rsrc_pos, 4, data_off + data_size)) {
                return NULL;
            }
            size = ld_be32(fork + rsrc_pos);
            if (!smi_range(rsrc_pos + 4, size, data_off + data_size)) {
                return NULL;
            }
            *bcem_size = size;
            return fork + rsrc_pos + 4;
        }
    }
    return NULL;
}

/* ADC literals and backward copies, with bounds checks on every command. */
static bool smi_adc_decode(const uint8_t *in, size_t inlen,
                           uint8_t *out, size_t outlen)
{
    size_t ip = 0, op = 0;

    while (ip < inlen && op < outlen) {
        uint8_t code = in[ip++];
        size_t count, distance, j;

        if (code & 0x80) {
            count = (code & 0x7f) + 1;
            if (count > inlen - ip || count > outlen - op) {
                return false;
            }
            memcpy(out + op, in + ip, count);
            op += count;
            ip += count;
            continue;
        }
        if (ip >= inlen) {
            return false;
        }
        if (code & 0x40) {
            if (inlen - ip < 2) {
                return false;
            }
            count = (code & 0x3f) + 4;
            distance = ((uint32_t)in[ip] << 8 | in[ip + 1]) + 1;
            ip += 2;
        } else {
            count = (code >> 2) + 3;
            distance = (((uint32_t)code << 8 | in[ip++]) & 0x3ff) + 1;
        }
        if (distance > op || count > outlen - op) {
            return false;
        }
        /* An ADC back-reference may overlap its own output. */
        for (j = 0; j < count; j++) {
            out[op + j] = out[op + j - distance];
        }
        op += count;
    }
    return ip == inlen && op == outlen;
}

static int smi_open(BlockDriverState *bs, QDict *options, int flags,
                    Error **errp)
{
    BDRVSmiState *s = bs->opaque;
    uint8_t header[128];
    uint8_t *fork = NULL;
    const uint8_t *bcem;
    uint32_t data_length, fork_length, rsrc_size, bcem_size;
    uint32_t sectors, n_chunks, max_blocks, i, prev;
    uint64_t file_size, data_base, rsrc_base, max_compressed = 0;
    bool has_adc = false;
    int64_t file_length;
    int ret;

    GLOBAL_STATE_CODE();
    bdrv_graph_rdlock_main_loop();
    ret = bdrv_apply_auto_read_only(bs, NULL, errp);
    bdrv_graph_rdunlock_main_loop();
    if (ret < 0) {
        return ret;
    }
    ret = bdrv_open_file_child(NULL, options, "file", bs, errp);
    if (ret < 0) {
        return ret;
    }
    GRAPH_RDLOCK_GUARD_MAINLOOP();
    file_length = bdrv_getlength(bs->file->bs);
    if (file_length < 0) {
        return file_length;
    }
    file_size = file_length;
    if (!smi_range(0, sizeof(header), file_size)) {
        goto invalid;
    }
    ret = bdrv_pread(bs->file, 0, sizeof(header), header, 0);
    if (ret < 0) {
        return ret;
    }
    data_length = ld_be32(header + 83);
    fork_length = ld_be32(header + 87);
    data_base = sizeof(header);
    rsrc_base = data_base + QEMU_ALIGN_UP((uint64_t)data_length, 128);
    if (header[0] || !header[1] || header[1] > 63 ||
        !data_length || !fork_length || fork_length > SMI_FORK_MAX ||
        !smi_range(data_base, data_length, file_size) ||
        !smi_range(rsrc_base, fork_length, file_size)) {
        goto invalid;
    }

    fork = g_try_malloc(fork_length);
    if (!fork) {
        return -ENOMEM;
    }
    ret = bdrv_pread(bs->file, rsrc_base, fork_length, fork, 0);
    if (ret < 0) {
        goto fail;
    }
    bcem = smi_bcem(fork, fork_length, &bcem_size);
    if (!bcem || bcem_size < SMI_RESOURCE_HEADER) {
        goto invalid;
    }
    if (ld_be16(bcem) < 10 || ld_be16(bcem) > 12 ||
        ld_be32(bcem + 84) != 0) {
        error_setg(errp, "SMI NDIF version or segmented image is unsupported");
        goto unsupported;
    }
    sectors = ld_be32(bcem + 68);
    max_blocks = ld_be32(bcem + 72);
    s->backing_offset = ld_be32(bcem + 76);
    n_chunks = ld_be32(bcem + 124);
    if (!sectors || !max_blocks ||
        (uint64_t)max_blocks * SMI_SECTOR_SIZE > SMI_CHUNK_MAX ||
        !n_chunks || n_chunks > (SMI_FORK_MAX - 128) / SMI_CHUNK_ENTRY ||
        (uint64_t)SMI_RESOURCE_HEADER + (uint64_t)n_chunks *
            SMI_CHUNK_ENTRY != bcem_size) {
        goto invalid;
    }

    s->chunks = g_try_new0(SmiChunk, n_chunks);
    if (!s->chunks) {
        ret = -ENOMEM;
        goto fail;
    }
    prev = 0;
    for (i = 0; i < n_chunks; i++) {
        const uint8_t *entry = bcem + 128 + SMI_CHUNK_ENTRY * i;
        SmiChunk *chunk = &s->chunks[i];
        uint32_t next;
        uint64_t pos;

        chunk->sector = smi_be24(entry);
        chunk->type = entry[3];
        chunk->position = ld_be32(entry + 4);
        chunk->length = ld_be32(entry + 8);
        if (i && chunk->sector <= prev) {
            goto invalid;
        }
        if ((!i && chunk->sector != 0) || chunk->sector > sectors) {
            goto invalid;
        }
        prev = chunk->sector;
        if (chunk->type == 255) {
            if (i != n_chunks - 1 || chunk->sector != sectors) {
                goto invalid;
            }
            s->n_chunks = i;
            break;
        }
        next = i + 1 < n_chunks ?
               smi_be24(bcem + 128 + SMI_CHUNK_ENTRY * (i + 1)) :
               sectors;
        if (next <= chunk->sector || next > sectors ||
            next - chunk->sector > max_blocks) {
            goto invalid;
        }
        chunk->count = next - chunk->sector;
        s->n_chunks = i + 1;
        if (chunk->type == 0) {
            continue;
        }
        if (chunk->type == 2) {
            pos = chunk->position;
            if (!smi_range(pos, (uint64_t)chunk->count * 512,
                           data_length)) {
                goto invalid;
            }
        } else if (chunk->type == 131) {
            pos = (uint64_t)s->backing_offset + chunk->position;
            if (!chunk->length || chunk->length > SMI_CHUNK_MAX ||
                !smi_range(pos, chunk->length, data_length)) {
                goto invalid;
            }
            max_compressed = MAX(max_compressed, chunk->length);
            has_adc = true;
        } else {
            error_setg(errp, "SMI NDIF chunk compression type %u unsupported",
                       chunk->type);
            goto unsupported;
        }
    }
    if (!s->n_chunks ||
        s->chunks[s->n_chunks - 1].sector +
        s->chunks[s->n_chunks - 1].count != sectors) {
        goto invalid;
    }
    if (has_adc) {
        s->compressed = g_try_malloc(max_compressed);
        s->decoded = g_try_malloc((size_t)max_blocks * 512);
        if (!s->compressed || !s->decoded) {
            ret = -ENOMEM;
            goto fail;
        }
    }
    s->data_base = data_base;
    s->data_length = data_length;
    s->cached = UINT32_MAX;
    bs->total_sectors = sectors;
    qemu_co_mutex_init(&s->lock);
    g_free(fork);
    return 0;

invalid:
    error_setg(errp, "Invalid or incomplete MacBinary NDIF SMI (check forks)");
unsupported:
    ret = -EINVAL;
fail:
    g_free(fork);
    g_free(s->chunks);
    s->chunks = NULL;
    g_free(s->decoded);
    s->decoded = NULL;
    g_free(s->compressed);
    s->compressed = NULL;
    return ret;
}

static void smi_refresh_limits(BlockDriverState *bs, Error **errp)
{
    bs->bl.request_alignment = SMI_SECTOR_SIZE;
}

static uint32_t smi_find_chunk(const BDRVSmiState *s, uint64_t sector)
{
    uint32_t lo = 0, hi = s->n_chunks;

    while (lo < hi) {
        uint32_t mid = lo + (hi - lo) / 2;

        if (s->chunks[mid].sector <= sector) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    return lo ? lo - 1 : UINT32_MAX;
}

static int coroutine_fn GRAPH_RDLOCK
smi_co_preadv(BlockDriverState *bs, int64_t offset, int64_t bytes,
              QEMUIOVector *qiov, BdrvRequestFlags flags)
{
    BDRVSmiState *s = bs->opaque;
    QEMUIOVector local;
    uint64_t done = 0;
    uint64_t request_size = bytes;
    int ret = 0;

    assert(QEMU_IS_ALIGNED(offset, SMI_SECTOR_SIZE));
    assert(QEMU_IS_ALIGNED(bytes, SMI_SECTOR_SIZE));

    qemu_iovec_init(&local, qiov->niov);
    qemu_co_mutex_lock(&s->lock);
    while (done < request_size) {
        uint64_t sector = ((uint64_t)offset + done) / 512;
        uint32_t index = smi_find_chunk(s, sector);
        const SmiChunk *chunk;
        uint64_t within, length;

        if (index >= s->n_chunks) {
            ret = -EIO;
            break;
        }
        chunk = &s->chunks[index];
        within = ((uint64_t)sector - chunk->sector) * 512;
        length = MIN(request_size - done,
                     (uint64_t)chunk->count * 512 - within);
        if (!length) {
            ret = -EIO;
            break;
        }

        if (chunk->type == 0) {
            qemu_iovec_memset(qiov, done, 0, length);
        } else if (chunk->type == 2) {
            qemu_iovec_reset(&local);
            qemu_iovec_concat(&local, qiov, done, length);
            ret = bdrv_co_preadv(bs->file, s->data_base + chunk->position +
                                 within, length, &local, 0);
            if (ret < 0) {
                break;
            }
        } else {
            if (s->cached != index) {
                size_t decoded_len = (size_t)chunk->count * 512;
                uint64_t src = s->data_base + s->backing_offset +
                               chunk->position;

                ret = bdrv_co_pread(bs->file, src, chunk->length,
                                    s->compressed, 0);
                if (ret < 0) {
                    break;
                }
                if (!smi_adc_decode(s->compressed, chunk->length,
                                    s->decoded, decoded_len)) {
                    ret = -EIO;
                    break;
                }
                s->cached = index;
            }
            qemu_iovec_from_buf(qiov, done, s->decoded + within, length);
        }
        done += length;
    }
    qemu_co_mutex_unlock(&s->lock);
    qemu_iovec_destroy(&local);
    return ret;
}

static void smi_close(BlockDriverState *bs)
{
    BDRVSmiState *s = bs->opaque;

    g_free(s->chunks);
    g_free(s->compressed);
    g_free(s->decoded);
}

static BlockDriver bdrv_smi = {
    .format_name = "smi",
    .instance_size = sizeof(BDRVSmiState),
    .bdrv_probe = smi_probe,
    .bdrv_open = smi_open,
    .bdrv_child_perm = bdrv_default_perms,
    .bdrv_refresh_limits = smi_refresh_limits,
    .bdrv_co_preadv = smi_co_preadv,
    .bdrv_close = smi_close,
    .is_format = true,
};

static void bdrv_smi_init(void)
{
    bdrv_register(&bdrv_smi);
}

block_init(bdrv_smi_init);

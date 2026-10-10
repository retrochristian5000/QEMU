/* Synthetic PPC32/PPC64 Mach-O executable mapping regression.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "darwin-user/include/macho_exec.h"
#include "darwin-user/include/target_macho.h"
#include "darwin-user/ppc/target_abi.h"
#include <assert.h>
#include <string.h>
#define IMAGE_SIZE 0x800U

static void be32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}
static void be64(uint8_t *p, uint64_t v)
{
    be32(p, (uint32_t)(v >> 32)); be32(p + 4, (uint32_t)v);
}
static void make_exec(uint8_t *p, bool wide)
{
    size_t hdr = wide ? sizeof(QemuDarwinMachHeader64) :
                        sizeof(QemuDarwinMachHeader32);
    size_t sz = wide ? sizeof(QemuDarwinSegmentCommand64) :
                       sizeof(QemuDarwinSegmentCommand32);
    size_t thread_sz = 16 + (wide ? sizeof(QemuDarwinPpcThreadState64) :
                                     sizeof(QemuDarwinPpcThreadState32));
    uint64_t base = wide ? UINT64_C(0x100000000) : 0x1000;
    uint8_t *text, *data, *thread;
    memset(p, 0, IMAGE_SIZE);
    be32(p, wide ? QEMU_DARWIN_MH_MAGIC_64 : QEMU_DARWIN_MH_MAGIC);
    be32(p + 4, wide ? QEMU_DARWIN_CPU_TYPE_POWERPC64 :
                       QEMU_DARWIN_CPU_TYPE_POWERPC);
    be32(p + 8, wide ? QEMU_DARWIN_CPU_SUBTYPE_POWERPC_970 :
                       QEMU_DARWIN_CPU_SUBTYPE_POWERPC_7400);
    be32(p + 12, QEMU_DARWIN_MH_EXECUTE);
    be32(p + 16, 3);
    be32(p + 20, (uint32_t)(2 * sz + thread_sz));
    text = p + hdr; data = text + sz; thread = data + sz;
    be32(text, wide ? QEMU_DARWIN_LC_SEGMENT_64 : QEMU_DARWIN_LC_SEGMENT);
    be32(data, wide ? QEMU_DARWIN_LC_SEGMENT_64 : QEMU_DARWIN_LC_SEGMENT);
    be32(text + 4, (uint32_t)sz); be32(data + 4, (uint32_t)sz);
    memcpy(text + 8, "__TEXT", 6); memcpy(data + 8, "__DATA", 6);
    if (wide) {
        be64(text + 24, base); be64(text + 32, 0x1000);
        be64(text + 40, 0); be64(text + 48, 0x400);
        be32(text + 56, 7); be32(text + 60, 5);
        be64(data + 24, base + 0x2000); be64(data + 32, 0x1000);
        be64(data + 40, 0x400); be64(data + 48, 16);
        be32(data + 56, 3); be32(data + 60, 3);
    } else {
        be32(text + 24, (uint32_t)base); be32(text + 28, 0x1000);
        be32(text + 32, 0); be32(text + 36, 0x400);
        be32(text + 40, 7); be32(text + 44, 5);
        be32(data + 24, (uint32_t)(base + 0x2000));
        be32(data + 28, 0x1000); be32(data + 32, 0x400);
        be32(data + 36, 16); be32(data + 40, 3); be32(data + 44, 3);
    }
    be32(thread, QEMU_DARWIN_LC_UNIXTHREAD);
    be32(thread + 4, (uint32_t)thread_sz);
    be32(thread + 8, wide ? QEMU_DARWIN_PPC_THREAD_STATE64 :
                            QEMU_DARWIN_PPC_THREAD_STATE);
    be32(thread + 12, wide ? QEMU_DARWIN_PPC_THREAD_STATE64_COUNT :
                             QEMU_DARWIN_PPC_THREAD_STATE_COUNT);
    if (wide) { be64(thread + 16, base + 0x100); }
    else { be32(thread + 16, (uint32_t)base + 0x100); }
    memcpy(p + 0x400, "guest data file!", 16);
}

typedef struct Log { int n; int fail_second; uint64_t a[2], zero; } Log;
static bool map(void *opaque, const QemuDarwinPpcExecSegment *s,
                const uint8_t *bytes)
{
    Log *log = opaque;
    assert(log->n < 2);
    log->a[log->n] = s->vmaddr;
    log->zero += s->vmsize - s->filesize;
    if (log->n == 0) {
        assert(s->initprot == 5 && s->filesize == 0x400);
        assert(bytes[0] == 0xfe && bytes[1] == 0xed);
    } else {
        assert(s->initprot == 3 && s->filesize == 16);
        assert(memcmp(bytes, "guest data file!", 16) == 0);
    }
    ++log->n;
    return !(log->fail_second && log->n == 2);
}
static int plan(const uint8_t *p, size_t size, int32_t cpu,
                QemuDarwinPpcExecSegment *segments, size_t capacity,
                QemuDarwinPpcExecImage *out, const uint8_t **slice,
                size_t *length)
{
    return qemu_darwin_ppc_executable_plan(p, size, cpu, segments, capacity,
                                            out, slice, length);
}
int main(void)
{
    uint8_t p32[IMAGE_SIZE], p64[IMAGE_SIZE], bad[IMAGE_SIZE];
    uint8_t fat[0x3000] = { 0 };
    QemuDarwinPpcExecSegment seg[4];
    QemuDarwinPpcExecImage img;
    const uint8_t *slice;
    size_t length, hdr = sizeof(QemuDarwinMachHeader32);
    int32_t cpu32 = QEMU_DARWIN_CPU_TYPE_POWERPC;
    int32_t cpu64 = QEMU_DARWIN_CPU_TYPE_POWERPC64;
    Log log = { 0 };
    make_exec(p32, false); make_exec(p64, true);

    assert(plan(p32, IMAGE_SIZE, cpu32, seg, 4, &img, &slice, &length) == 0);
    assert(img.entry == 0x1100 && img.nsegments == 2 && slice == p32);
    assert(qemu_darwin_ppc_executable_apply(slice, length, seg, 2, map, &log) == 0);
    assert(log.n == 2 && log.a[0] == 0x1000 && log.a[1] == 0x3000);
    assert(log.zero == 0x1000 - 0x400 + 0x1000 - 16);

    memset(&log, 0, sizeof(log));
    assert(plan(p64, IMAGE_SIZE, cpu64, seg, 4, &img, &slice, &length) == 0);
    assert(img.entry == UINT64_C(0x100000100) && img.nsegments == 2);
    assert(qemu_darwin_ppc_executable_apply(slice, length, seg, 2, map, &log) == 0);
    assert(log.a[0] == UINT64_C(0x100000000));
    assert(log.a[1] == UINT64_C(0x100002000));

    be32(fat, QEMU_DARWIN_FAT_MAGIC); be32(fat + 4, 2);
    be32(fat + 8, (uint32_t)cpu32);
    be32(fat + 16, 0x1000); be32(fat + 20, IMAGE_SIZE); be32(fat + 24, 12);
    be32(fat + 28, (uint32_t)cpu64);
    be32(fat + 36, 0x2000); be32(fat + 40, IMAGE_SIZE); be32(fat + 44, 12);
    memcpy(fat + 0x1000, p32, IMAGE_SIZE);
    memcpy(fat + 0x2000, p64, IMAGE_SIZE);
    assert(plan(fat, sizeof(fat), cpu64, seg, 4, &img, &slice, &length) == 0);
    assert(slice == fat + 0x2000 && img.entry == UINT64_C(0x100000100));

    img.entry = 0xabcdef;
    memcpy(bad, p32, IMAGE_SIZE);
    be32(bad + hdr + 36, 0x2000); /* filesize > vmsize */
    assert(plan(bad, IMAGE_SIZE, cpu32, seg, 4, &img, &slice, &length) == -1);
    assert(img.entry == 0xabcdef); /* no partial outputs */

    memcpy(bad, p32, IMAGE_SIZE);
    be32(bad + hdr + 56 + 24, 0x1800); /* overlapping VM ranges */
    assert(plan(bad, IMAGE_SIZE, cpu32, seg, 4, &img, &slice, &length) == -1);
    memcpy(bad, p32, IMAGE_SIZE);
    be32(bad + hdr + 40, 1); /* initial executable protection > max */
    assert(plan(bad, IMAGE_SIZE, cpu32, seg, 4, &img, &slice, &length) == -1);
    memcpy(bad, p32, IMAGE_SIZE);
    be32(bad + hdr + 28, 0xfffff800U); /* wraps PPC32 address range */
    assert(plan(bad, IMAGE_SIZE, cpu32, seg, 4, &img, &slice, &length) == -1);

    memcpy(bad, p32, IMAGE_SIZE);
    be32(bad + hdr + 112 + 16, 0x1300); /* valid file-backed code */
    assert(plan(bad, IMAGE_SIZE, cpu32, seg, 4, &img, &slice, &length) == 0);
    be32(bad + hdr + 112 + 16, 0x1500); /* PC in zero-fill area */
    assert(plan(bad, IMAGE_SIZE, cpu32, seg, 4, &img, &slice, &length) == -1);
    memcpy(bad, p32, IMAGE_SIZE);
    be32(bad + 24, 4); /* MH_DYLDLINK */
    assert(plan(bad, IMAGE_SIZE, cpu32, seg, 4, &img, &slice, &length) ==
           QEMU_DARWIN_EXEC_NEEDS_DYLD);
    memcpy(bad, p32, IMAGE_SIZE);
    be32(bad + hdr + 112, QEMU_DARWIN_LC_LOAD_DYLINKER);
    assert(plan(bad, IMAGE_SIZE, cpu32, seg, 4, &img, &slice, &length) ==
           QEMU_DARWIN_EXEC_NEEDS_DYLD);

    assert(plan(p32, IMAGE_SIZE, cpu64, seg, 4, &img, &slice, &length) == -1);
    assert(plan(p32, IMAGE_SIZE, cpu32, seg, 1, &img, &slice, &length) == -1);
    assert(plan(p32, 20, cpu32, seg, 4, &img, &slice, &length) == -1);

    assert(plan(p32, IMAGE_SIZE, cpu32, seg, 4, &img, &slice, &length) == 0);
    memset(&log, 0, sizeof(log)); log.fail_second = 1;
    assert(qemu_darwin_ppc_executable_apply(slice, length, seg, 2, map, &log) == -1);
    assert(log.n == 2); /* caller must roll back partial guest mappings */
    seg[1].fileoff = IMAGE_SIZE + 1;
    memset(&log, 0, sizeof(log));
    assert(qemu_darwin_ppc_executable_apply(slice, length, seg, 2, map, &log) == -1);
    assert(log.n == 0); /* reject bad plans before any mapping */
    return 0;
}

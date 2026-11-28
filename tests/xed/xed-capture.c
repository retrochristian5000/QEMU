/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Capture a controlled flat i386 guest's MOV accesses for external XED.
 * No XED dependency, no guest writes and no host-address dereferencing.
 */
#include <glib.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <qemu-plugin.h>

QEMU_PLUGIN_EXPORT int qemu_plugin_version = QEMU_PLUGIN_VERSION;

static const char *const reg_names[] = {
    "eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi",
    "cs", "ds", "es", "ss", "fs", "gs", "cr0", "eflags"
};

enum {
    GPR_COUNT = 8, CS_INDEX = 8, CR0_INDEX = 14, FLAGS_INDEX = 15,
    REG_COUNT = G_N_ELEMENTS(reg_names)
};

typedef struct {
    struct qemu_plugin_register *handles[REG_COUNT];
    bool found[REG_COUNT];
    uint32_t regs[REG_COUNT];
    const char *hex;
    bool pending;
    bool valid;
} CaptureState;

static struct qemu_plugin_scoreboard *states;
static GHashTable *encodings;
static GMutex encoding_lock;
static uint64_t start_pc, end_pc;

static void capture_error(const char *message)
{
    g_autofree char *line = g_strdup_printf("XEDCAPTURE_ERROR %s\n", message);
    qemu_plugin_outs(line);
}

static bool parse_pc(const char *text, uint64_t *pc)
{
    if (!text || !*text || strlen(text) > 8 ||
        strspn(text, "0123456789abcdefABCDEF") != strlen(text)) {
        return false;
    }
    *pc = g_ascii_strtoull(text, NULL, 16);
    return true;
}

static void init_cpu(unsigned int cpu_index, void *userdata)
{
    CaptureState *state = qemu_plugin_scoreboard_find(states, cpu_index);
    g_autoptr(GArray) regs = qemu_plugin_get_registers();

    memset(state, 0, sizeof(*state));
    if (!regs) {
        capture_error("register list unavailable");
        return;
    }
    for (unsigned i = 0; i < regs->len; i++) {
        qemu_plugin_reg_descriptor *rd =
            &g_array_index(regs, qemu_plugin_reg_descriptor, i);
        for (unsigned j = 0; j < REG_COUNT; j++) {
            if (!strcmp(rd->name, reg_names[j])) {
                state->handles[j] = rd->handle;
                state->found[j] = true;
            }
        }
    }
}

static void before_insn(unsigned int cpu_index, void *userdata)
{
    CaptureState *state = qemu_plugin_scoreboard_find(states, cpu_index);
    g_autoptr(GByteArray) buf = g_byte_array_new();

    if (state->pending) {
        capture_error("previous selected instruction had no completed access");
    }
    state->pending = true;
    state->valid = false;
    state->hex = userdata;
    for (unsigned i = 0; i < REG_COUNT; i++) {
        uint32_t value;

        g_byte_array_set_size(buf, 0);
        /* A register handle may be NULL for register zero. */
        if (!state->found[i] ||
            !qemu_plugin_read_register(state->handles[i], buf) ||
            buf->len != sizeof(value)) {
            capture_error("required 32-bit register unavailable");
            return;
        }
        memcpy(&value, buf->data, sizeof(value));
        state->regs[i] = GUINT32_FROM_LE(value);
    }

    /*
     * This is the flat GDT contract of the controlled test guest, not
     * an inference that arbitrary descriptors have zero bases.
     */
    if (!(state->regs[CR0_INDEX] & 1) ||
        (state->regs[FLAGS_INDEX] & (1u << 17)) ||
        state->regs[CS_INDEX] != 8) {
        capture_error("guest is outside controlled protected-mode contract");
        return;
    }
    for (unsigned i = CS_INDEX + 1; i < CR0_INDEX; i++) {
        if (state->regs[i] != 0x10) {
            capture_error("guest data selector differs from flat test GDT");
            return;
        }
    }
    state->valid = true;
}

static void memory_access(unsigned int cpu_index, qemu_plugin_meminfo_t info,
                          uint64_t vaddr, void *userdata)
{
    CaptureState *state = qemu_plugin_scoreboard_find(states, cpu_index);
    unsigned shift = qemu_plugin_mem_size_shift(info);
    g_autoptr(GString) line = g_string_new(NULL);

    if (!state->pending || !state->valid || state->hex != userdata ||
        vaddr > UINT32_MAX || shift > 2) {
        capture_error("unexpected or unsupported memory access");
        state->pending = false;
        return;
    }
    state->pending = false;
    g_string_append_printf(line, "XEDMEM %s %" PRIx64 " %x %c",
                           state->hex, vaddr, 1u << shift,
                           qemu_plugin_mem_is_store(info) ? 'w' : 'r');
    for (unsigned i = 0; i < GPR_COUNT; i++) {
        g_string_append_printf(line, " %08" PRIx32, state->regs[i]);
    }
    /* The test guest's six cached bases are explicitly zero. */
    g_string_append(line, " 0 0 0 0 0 0\n");
    qemu_plugin_outs(line->str);
}

static void translate(struct qemu_plugin_tb *tb, void *userdata)
{
    for (size_t i = 0; i < qemu_plugin_tb_n_insns(tb); i++) {
        struct qemu_plugin_insn *insn = qemu_plugin_tb_get_insn(tb, i);
        uint64_t pc = qemu_plugin_insn_vaddr(insn);
        uint8_t bytes[15];
        size_t len;
        char hex[31];
        const char *key;

        if (pc < start_pc || pc >= end_pc) {
            continue;
        }
        len = qemu_plugin_insn_size(insn);
        if (!len || len > sizeof(bytes) || len > end_pc - pc ||
            qemu_plugin_insn_data(insn, bytes, len) != len) {
            capture_error("selected instruction bytes unavailable");
            continue;
        }
        for (size_t j = 0; j < len; j++) {
            g_snprintf(hex + j * 2, 3, "%02x", (unsigned)bytes[j]);
        }
        g_mutex_lock(&encoding_lock);
        key = g_hash_table_lookup(encodings, hex);
        if (!key) {
            key = g_strdup(hex);
            g_hash_table_add(encodings, (gpointer)key);
        }
        g_mutex_unlock(&encoding_lock);

        qemu_plugin_register_vcpu_insn_exec_cb(insn, before_insn,
                                               QEMU_PLUGIN_CB_R_REGS,
                                               (void *)key);
        qemu_plugin_register_vcpu_mem_cb(insn, memory_access,
                                         QEMU_PLUGIN_CB_NO_REGS,
                                         QEMU_PLUGIN_MEM_RW, (void *)key);
    }
}

static void exit_cpu(unsigned int cpu_index, void *userdata)
{
    CaptureState *state = qemu_plugin_scoreboard_find(states, cpu_index);
    if (state->pending) {
        capture_error("selected instruction did not complete a memory access");
    }
}

static void finish(void *userdata)
{
    qemu_plugin_scoreboard_free(states);
    g_hash_table_destroy(encodings);
}

QEMU_PLUGIN_EXPORT int qemu_plugin_install(qemu_plugin_id_t id,
                                           const qemu_info_t *info,
                                           int argc, char **argv)
{
    bool have_start = false, have_end = false;

    if (!info->system_emulation || strcmp(info->target_name, "i386")) {
        fputs("xed-capture requires qemu-system-i386\n", stderr);
        return -1;
    }
    for (int i = 0; i < argc; i++) {
        if (g_str_has_prefix(argv[i], "start=") && !have_start &&
            parse_pc(argv[i] + 6, &start_pc)) {
            have_start = true;
        } else if (g_str_has_prefix(argv[i], "end=") && !have_end &&
                   parse_pc(argv[i] + 4, &end_pc)) {
            have_end = true;
        } else {
            fputs("xed-capture: invalid or duplicate range argument\n", stderr);
            return -1;
        }
    }
    if (!have_start || !have_end || end_pc <= start_pc ||
        end_pc - start_pc > 4096) {
        fputs("xed-capture: require start/end hex PCs, range <= 4096 bytes\n",
              stderr);
        return -1;
    }

    states = qemu_plugin_scoreboard_new(sizeof(CaptureState));
    encodings = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, NULL);
    qemu_plugin_register_vcpu_init_cb(id, init_cpu, NULL);
    qemu_plugin_register_vcpu_exit_cb(id, exit_cpu, NULL);
    qemu_plugin_register_vcpu_tb_trans_cb(id, translate, NULL);
    qemu_plugin_register_atexit_cb(id, finish, NULL);
    return 0;
}

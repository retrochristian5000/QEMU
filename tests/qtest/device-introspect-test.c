/*
 * Device introspection test cases
 *
 * Copyright (c) 2015 Red Hat Inc.
 *
 * Authors:
 *  Markus Armbruster <armbru@redhat.com>,
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the COPYING file in the top-level directory.
 */

/*
 * Covers QMP device-list-properties and HMP device_add help.  The generic
 * sweep primarily checks that QEMU survives; targeted cases also validate
 * user-facing property output where regressions have been found.
 */

#include "qemu/osdep.h"
#include "qobject/qstring.h"
#include "qobject/qdict.h"
#include "qobject/qlist.h"
#include "libqtest.h"

const char common_args[] = "-nodefaults -machine none";

static QList *qom_list_types(QTestState * qts, const char *implements,
                             bool abstract)
{
    QDict *resp;
    QList *ret;
    QDict *args = qdict_new();

    qdict_put_bool(args, "abstract", abstract);
    if (implements) {
        qdict_put_str(args, "implements", implements);
    }
    resp = qtest_qmp(qts, "{'execute': 'qom-list-types', 'arguments': %p }",
                     args);
    g_assert(qdict_haskey(resp, "return"));
    ret = qdict_get_qlist(resp, "return");
    qobject_ref(ret);
    qobject_unref(resp);
    return ret;
}

/* Build a name -> ObjectTypeInfo index from a ObjectTypeInfo list */
static QDict *qom_type_index(QList *types)
{
    QDict *index = qdict_new();
    QListEntry *e;

    QLIST_FOREACH_ENTRY(types, e) {
        QDict *d = qobject_to(QDict, qlist_entry_obj(e));
        const char *name = qdict_get_str(d, "name");
        qobject_ref(d);
        qdict_put(index, name, d);
    }
    return index;
}

/* Check if @parent is present in the parent chain of @type */
static bool qom_has_parent(QDict *index, const char *type, const char *parent)
{
    while (type) {
        QDict *d = qdict_get_qdict(index, type);
        const char *p = d && qdict_haskey(d, "parent") ?
                        qdict_get_str(d, "parent") :
                        NULL;

        if (!strcmp(type, parent)) {
            return true;
        }

        type = p;
    }

    return false;
}

/* Find an entry on a list returned by qom-list-types */
static QDict *type_list_find(QList *types, const char *name)
{
    QListEntry *e;

    QLIST_FOREACH_ENTRY(types, e) {
        QDict *d = qobject_to(QDict, qlist_entry_obj(e));
        const char *ename = qdict_get_str(d, "name");
        if (!strcmp(ename, name)) {
            return d;
        }
    }

    return NULL;
}

static QList *device_type_list(QTestState *qts, bool abstract)
{
    return qom_list_types(qts, "device", abstract);
}

static bool property_list_has_name(QList *props, const char *name)
{
    QListEntry *e;

    QLIST_FOREACH_ENTRY(props, e) {
        QDict *prop = qobject_to(QDict, qlist_entry_obj(e));

        if (!strcmp(qdict_get_str(prop, "name"), name)) {
            return true;
        }
    }

    return false;
}

static void test_one_device(QTestState *qts, const char *type)
{
    QDict *resp;
    char *help, *escaped;
    GRegex *comma;

    g_test_message("Testing device '%s'", type);

    resp = qtest_qmp(qts, "{'execute': 'device-list-properties',"
                          " 'arguments': {'typename': %s}}",
               type);
    qobject_unref(resp);

    comma = g_regex_new(",", 0, 0, NULL);
    escaped = g_regex_replace_literal(comma, type, -1, 0, ",,", 0, NULL);
    g_regex_unref(comma);

    help = qtest_hmp(qts, "device_add \"%s,help\"", escaped);
    g_free(help);
    g_free(escaped);
}

static void test_device_intro_settable_only(void)
{
    QTestState *qts = qtest_init(common_args);
    QList *types = device_type_list(qts, false);
    static const char *const ati_types[] = {
        "ati-vga", "ati-rage128p", "ati-rv100",
    };
    QDict *resp;
    QList *props;
    char *help;
    size_t i;

    if (!type_list_find(types, "ati-vga")) {
        g_test_skip("ATI VGA is not available for this target");
        qobject_unref(types);
        qtest_quit(qts);
        return;
    }

    for (i = 0; i < ARRAY_SIZE(ati_types); i++) {
        const char *name = ati_types[i];

        g_assert_nonnull(type_list_find(types, name));
        resp = qtest_qmp(qts, "{'execute': 'device-list-properties',"
                              " 'arguments': {'typename': %s}}", name);
        g_assert_true(qdict_haskey(resp, "return"));
        props = qdict_get_qlist(resp, "return");

        g_assert_true(property_list_has_name(props, "vgamem_mb"));
        g_assert_false(property_list_has_name(props, "model"));
        g_assert_false(property_list_has_name(props, "x-device-id"));
        g_assert_false(property_list_has_name(props, "busnr"));
        g_assert_false(property_list_has_name(props, "edid"));
        g_assert_false(property_list_has_name(props, "sriov-pf"));

        help = qtest_hmp(qts, "device_add \"%s,help\"", name);
        g_assert_null(strstr(help, "model="));
        g_assert_null(strstr(help, "x-device-id="));
        g_assert_null(strstr(help, "busnr="));
        g_assert_null(strstr(help, "edid="));
        g_assert_null(strstr(help, "sriov-pf="));
        g_free(help);
        qobject_unref(resp);
    }

    qobject_unref(types);
    qtest_quit(qts);
}

static void test_device_intro_list(void)
{
    QList *types;
    char *help;
    QTestState *qts;

    qts = qtest_init(common_args);

    types = device_type_list(qts, true);
    qobject_unref(types);

    help = qtest_hmp(qts, "device_add help");
    g_free(help);

    qtest_quit(qts);
}

static void assert_device_help_desc(const char *help,
                                    const char *name,
                                    const char *desc)
{
    g_autofree char *name_needle = g_strdup_printf("name \"%s\"", name);
    g_autofree char *desc_needle = g_strdup_printf("desc \"%s\"", desc);
    const char *line = strstr(help, name_needle);
    const char *line_end;

    g_assert_nonnull(line);
    line_end = strchr(line, '\n');
    if (!line_end) {
        line_end = line + strlen(line);
    }
    g_assert_nonnull(g_strstr_len(line, line_end - line, desc_needle));
}

static void test_device_intro_display_descriptions(void)
{
    static const struct {
        const char *name;
        const char *desc;
    } devices[] = {
        { "att-kbd301",
          "AT&T 301 keyboard (Intel 8741 included; guest I/O pending)" },
        { "att-kbd302",
          "AT&T 302 keyboard (Intel UPI-41; experimental I/O optional)" },
        { "ati-vga", "ATI Rage 128 Pro / Radeon RV100 PCI VGA controller" },
        { "cirrus-vga-generic",
          "Generic Cirrus Logic VGA (PCI default)" },
        { "cirrus-vga-generic-pci",
          "Generic Cirrus Logic PCI VGA" },
        { "cirrus-vga-generic-isa",
          "Generic Cirrus Logic ISA VGA" },
        { "gd5422",
          "Cirrus Logic CL-GD5422 ISA VGA" },
        { "gd5426",
          "Cirrus Logic CL-GD5426 ISA VGA" },
        { "gd5428",
          "Cirrus Logic CL-GD5428 ISA VGA" },
        { "gd5430-pci",
          "Cirrus Logic CL-GD5430 PCI VGA" },
        { "gd5430-vlb",
          "Cirrus Logic CL-GD5430 VLB VGA" },
        { "gd5446-pci",
          "Cirrus Logic CL-GD5446 PCI VGA" },
        { "gd5446a-pci",
          "Cirrus Logic CL-GD5446 Revision A PCI VGA" },
        { "gd5446b-pci",
          "Cirrus Logic CL-GD5446 Revision B PCI VGA" },
        { "sb16-generic", "Generic Sound Blaster 16 compatible (ISA, non-PnP)" },
        { "sb16", "Creative Sound Blaster 16 CT1740 (experimental PCM and MIDI)" },
        { "sb16-ct1730", "Creative Sound Blaster 16 CT1730 (experimental PCM and MIDI)" },
        { "sb16-ct1750", "Creative Sound Blaster 16 MultiCD CT1750 (PCM and MIDI only)" },
        { "sb16-ct1770", "Creative Sound Blaster 16 SCSI-2 CT1770 (PCM and MIDI only)" },
        { "sb16-ct1790", "Creative Sound Blaster 16 Sony CT1790 (PCM and MIDI only)" },
        { "mpu401-uart-compat", "MPU-401 UART-compatible ISA MIDI interface" },
        { "intel-8041",
          "Intel 8041 UPI-41 controller (keyboard link; guest I/O pending)" },
        { "intel-8741",
          "Intel 8741 UPI-41 controller (keyboard link; guest I/O pending)" },
        { "isa-vga", "QEMU Standard VGA ISA controller" },
        { "sierra-falcon64",
          "Sierra Semiconductor Falcon/64 SC15064 PCI VGA controller" },
        { "VGA", "QEMU Standard VGA PCI controller" },
        { "virtio-vga", "VirtIO VGA graphics adapter" },
        { "vmware-svga", "VMware SVGA II PCI VGA controller" },
    };
    QTestState *qts = qtest_init(common_args);
    g_autofree char *help = qtest_hmp(qts, "device_add help");
    QList *types = device_type_list(qts, false);

    for (size_t i = 0; i < ARRAY_SIZE(devices); i++) {
        if (type_list_find(types, devices[i].name)) {
            assert_device_help_desc(help, devices[i].name, devices[i].desc);
        }
    }

    qobject_unref(types);
    qtest_quit(qts);
}

static void test_storage_controller_descriptions(void)
{
    static const struct {
        const char *name;
        const char *desc;
    } devices[] = {
        { "isa-ide", "Generic ISA IDE controller" },
        { "piix3-ide", "Intel 82371SB PIIX3 PCI IDE controller" },
        { "piix4-ide", "Intel 82371AB PIIX4 PCI IDE controller" },
        { "ich9-ahci", "Intel ICH9 PCI SATA AHCI controller" },
        { "cmd646-ide", "CMD Technology PCI-646 PCI IDE controller" },
        { "sii3112", "Silicon Image SiI3112A PCI SATA controller" },
        { "sysbus-ahci", "Generic system-bus AHCI SATA controller" },
        { "allwinner-ahci", "Allwinner AHCI SATA controller" },
        { "am53c974", "AMD Am53C974 PCI SCSI controller" },
        { "dc390", "Tekram DC-390 PCI SCSI adapter" },
        { "lsi53c895a", "LSI Logic 53C895A PCI SCSI controller" },
        { "lsi53c810", "NCR 53C810 PCI SCSI controller" },
        { "megasas", "LSI MegaRAID SAS 1078 PCI RAID controller" },
        { "megasas-gen2", "LSI MegaRAID SAS 2108 PCI RAID controller" },
        { "mptsas1068", "LSI Logic SAS1068 PCI SAS controller" },
        { "pvscsi", "VMware PVSCSI paravirtualized PCI SCSI controller" },
        { "isa-fdc", "Generic ISA floppy disk controller" },
        { "sysbus-fdc", "Generic system-bus floppy disk controller" },
        { "sun-fdtwo", "Sun FDTWO floppy disk controller" },
    };
    QTestState *qts = qtest_init(common_args);
    g_autofree char *help = qtest_hmp(qts, "info qdm");
    QList *types = device_type_list(qts, false);

    for (size_t i = 0; i < ARRAY_SIZE(devices); i++) {
        if (type_list_find(types, devices[i].name)) {
            assert_device_help_desc(help, devices[i].name, devices[i].desc);
        }
    }

    qobject_unref(types);
    qtest_quit(qts);
}

static void test_device_help_cli(void)
{
    const char *binary = qtest_qemu_binary("QTEST_QEMU_BINARY");
    char *args[] = {
        (char *)binary, "-device", "help", NULL,
    };
    g_autofree char *plain = NULL;
    g_autofree char *explicit_text = NULL;
    g_autoptr(GError) err = NULL;
    int status;

    g_assert_true(g_spawn_sync(NULL, args, NULL, G_SPAWN_SEARCH_PATH,
                               NULL, NULL, &plain, NULL, &status, &err));
    g_assert_no_error(err);
    g_assert_true(g_spawn_check_wait_status(status, &err));
    g_assert_no_error(err);
    g_assert_nonnull(strstr(plain, " devices:\n"));
    g_assert_nonnull(strstr(plain, "name \""));

    args[2] = "help,window=off";
    g_assert_true(g_spawn_sync(NULL, args, NULL, G_SPAWN_SEARCH_PATH,
                               NULL, NULL, &explicit_text, NULL,
                               &status, &err));
    g_assert_no_error(err);
    g_assert_true(g_spawn_check_wait_status(status, &err));
    g_assert_no_error(err);
    g_assert_cmpstr(plain, ==, explicit_text);
}

static void test_generic_device_types(void)
{
    static const struct {
        const char *type;
        const char *old_type;
        const char *args;
    } models[] = {
        { "cirrus-vga-generic", "cirrus-vga", "-vga none" },
        { "cirrus-vga-generic-isa", "isa-cirrus-vga-generic", "-vga none" },
        { "cirrus-vga-generic-pci", NULL, "-vga none" },
        { "gd5428", "isa-cirrus-gd5428", "-vga none" },
        { "sb16-generic", NULL, "-audiodev none,id=snd" },
    };
    static const char *const retired_types[] = {
        "isa-cirrus-vga", "isa-cirrus-gd5422", "isa-cirrus-gd5426",
        "cirrus-gd5430-pci", "cirrus-gd5430-vlb", "cirrus-gd5446-pci",
        "gd5428-pci",
    };
    static const char *const retired_aliases[] = {
        "ac97", "ahci", "e1000-82540em", "motorola-mc146818",
    };
    QTestState *qts = qtest_init(common_args);
    QList *types = device_type_list(qts, false);
    g_autofree char *help = qtest_hmp(qts, "device_add help");

    for (size_t i = 0; i < ARRAY_SIZE(models); i++) {
        g_autofree char *needle = NULL;
        g_autofree char *old_help = NULL;
        const char *line;
        const char *end;

        if (models[i].old_type) {
            g_assert_null(type_list_find(types, models[i].old_type));
        }
        if (!type_list_find(types, models[i].type)) {
            continue;
        }
        needle = g_strdup_printf("name \"%s\"", models[i].type);
        line = strstr(help, needle);
        g_assert_nonnull(line);
        end = strchr(line, '\n');
        g_assert_nonnull(end);
        g_assert_null(g_strstr_len(line, end - line, "alias \""));
        if (models[i].old_type) {
            old_help = qtest_hmp(qts, "device_add \"%s,help\"",
                                 models[i].old_type);
            g_assert_null(strstr(old_help, " options:"));
        } else if (!strcmp(models[i].type, "sb16-generic")) {
            g_assert_nonnull(type_list_find(types, "sb16"));
        }
    }
    for (size_t i = 0; i < ARRAY_SIZE(retired_types); i++) {
        g_assert_null(type_list_find(types, retired_types[i]));
    }
    for (size_t i = 0; i < ARRAY_SIZE(retired_aliases); i++) {
        g_autofree char *needle =
            g_strdup_printf("alias \"%s\"", retired_aliases[i]);

        g_assert_null(strstr(help, needle));
    }
    qobject_unref(types);
    qtest_quit(qts);

    if (!qtest_has_machine("pc")) {
        return;
    }
    for (size_t i = 0; i < ARRAY_SIZE(models); i++) {
        const char *audio = !strcmp(models[i].type, "sb16-generic")
                            ? ",audiodev=snd" : "";
        g_autofree char *tree = NULL;
        g_autofree char *expected = NULL;

        if (!qtest_has_device(models[i].type)) {
            continue;
        }
        qts = qtest_initf("-M pc -nodefaults %s -device %s,id=model%s",
                          models[i].args, models[i].type, audio);
        g_assert_true(qtest_qom_get_bool(qts,
                      "/machine/peripheral/model", "realized"));
        tree = qtest_hmp(qts, "info qtree");
        expected = g_strdup_printf("dev: %s,", models[i].type);
        g_assert_nonnull(strstr(tree, expected));
        qtest_quit(qts);
    }
}

static void test_att_kbd301_controller(void)
{
    QTestState *qts = qtest_init(common_args);
    QList *types = device_type_list(qts, false);
    bool supported = type_list_find(types, "att-kbd301") != NULL;
    const char *parent = "/machine/peripheral/kbd301";
    const char *child = "/machine/peripheral/kbd301/controller";

    if (supported) {
        g_assert_nonnull(type_list_find(types, "intel-8741"));
    }
    qobject_unref(types);
    qtest_quit(qts);

    if (!supported) {
        g_test_skip("AT&T 301 keyboard is not built for this target");
        return;
    }

    qts = qtest_init("-machine none -nodefaults "
                     "-device att-kbd301,id=kbd301");
    g_assert_true(qtest_qom_get_bool(qts, parent, "realized"));
    g_assert_true(qtest_qom_get_bool(qts, child, "realized"));
    g_assert_true(qtest_qom_get_bool(qts, child, "keyboard-attached"));
    qtest_quit(qts);

    if (qtest_has_machine("pc")) {
        qts = qtest_init("-machine pc -nodefaults "
                         "-device att-kbd301,id=kbd301");
        g_assert_true(qtest_qom_get_bool(qts, parent, "realized"));
        g_assert_true(qtest_qom_get_bool(qts, child, "realized"));
        g_assert_true(qtest_qom_get_bool(qts, child, "keyboard-attached"));
        qtest_quit(qts);
    }
}


static void test_att_kbd302_controller(void)
{
    QTestState *qts = qtest_init(common_args);
    QList *types = device_type_list(qts, false);
    bool supported = type_list_find(types, "att-kbd302") != NULL;
    const char *parent = "/machine/peripheral/kbd302";
    const char *child = "/machine/peripheral/kbd302/controller";

    if (supported) {
        g_assert_nonnull(type_list_find(types, "intel-8741"));
    }
    qobject_unref(types);
    qtest_quit(qts);

    if (!supported) {
        g_test_skip("AT&T 302 keyboard is not built for this target");
        return;
    }

    qts = qtest_init("-machine none -nodefaults "
                     "-device att-kbd302,id=kbd302");
    g_assert_true(qtest_qom_get_bool(qts, parent, "realized"));
    g_assert_true(qtest_qom_get_bool(qts, child, "realized"));
    g_assert_true(qtest_qom_get_bool(qts, child, "keyboard-attached"));
    qtest_quit(qts);

    if (qtest_has_machine("pc")) {
        qts = qtest_init("-machine pc -nodefaults "
                         "-device att-kbd302,id=kbd302");
        g_assert_true(qtest_qom_get_bool(qts, parent, "realized"));
        g_assert_true(qtest_qom_get_bool(qts, child, "realized"));
        g_assert_true(qtest_qom_get_bool(qts, child, "keyboard-attached"));
        qtest_quit(qts);
    }
}

static void test_att_kbd302_io(void)
{
    QTestState *qts = qtest_init(common_args);
    QList *types = device_type_list(qts, false);
    bool supported = type_list_find(types, "att-kbd302") != NULL;

    qobject_unref(types);
    qtest_quit(qts);
    if (!supported) {
        g_test_skip("AT&T 302 keyboard is unavailable");
        return;
    }

    qts = qtest_init("-machine none -nodefaults "
                     "-device att-kbd302,id=kbd,io=on");
    g_assert_cmphex(qtest_inb(qts, 0x64), ==, 0);
    g_assert_cmphex(qtest_inb(qts, 0x60), ==, 0xff);
    qtest_outb(qts, 0x64, 0x37);
    g_assert_cmphex(qtest_inb(qts, 0x64), ==, 0x0a);
    qtest_outb(qts, 0x60, 0x55);
    g_assert_cmphex(qtest_inb(qts, 0x64), ==, 0x0a);
    g_assert_cmphex(qtest_inb(qts, 0x60), ==, 0xff);
    qtest_quit(qts);

    qts = qtest_init("-machine none -nodefaults "
                     "-device intel-8041,id=upi "
                     "-device att-kbd302,id=kbd,controller-id=upi,io=on");
    qtest_outb(qts, 0x60, 0x51);
    g_assert_cmphex(qtest_inb(qts, 0x64), ==, 0x02);
    qtest_quit(qts);
}

static void test_att_keyboard_explicit_controller(void)
{
    static const char *const args[] = {
        "-device intel-8741,id=upi -device att-kbd302,id=kbd",
        "-device att-kbd302,id=kbd -device intel-8741,id=upi",
        "-device att-kbd301,id=kbd -device intel-8741,id=upi",
        "-device att-kbd302,id=kbd,controller-id=upi "
        "-device intel-8741,id=other -device intel-8741,id=upi",
        "-device att-kbd302,id=kbd "
        "-device '{\"driver\":\"intel-8741\",\"id\":\"upi\"}'",
        "-device intel-8041,id=upi -device att-kbd302,id=kbd",
        "-device att-kbd302,id=kbd -device intel-8041,id=upi",
        "-device att-kbd301,id=kbd -device intel-8041,id=upi",
        "-device att-kbd302,id=kbd,controller-id=upi "
        "-device intel-8741,id=other -device intel-8041,id=upi",
    };
    QTestState *qts = qtest_init(common_args);
    QList *types = device_type_list(qts, false);
    bool supported = type_list_find(types, "att-kbd302") != NULL;

    qobject_unref(types);
    qtest_quit(qts);
    if (!supported) {
        g_test_skip("AT&T keyboards are not built for this target");
        return;
    }

    for (unsigned int i = 0; i < ARRAY_SIZE(args); i++) {
        g_autofree char *cmd = g_strdup_printf("%s %s", common_args, args[i]);
        QDict *reply;

        qts = qtest_init(cmd);
        g_assert_true(qtest_qom_get_bool(qts, "/machine/peripheral/kbd",
                                        "realized"));
        g_assert_true(qtest_qom_get_bool(qts, "/machine/peripheral/upi",
                                        "keyboard-attached"));
        reply = qtest_qmp(qts,
            "{'execute':'qom-get','arguments':"
            "{'path':'/machine/peripheral/kbd','property':'active-controller'}}");
        g_assert_true(qdict_haskey(reply, "return"));
        g_assert_cmpstr(qdict_get_str(reply, "return"), ==,
                        "/machine/peripheral/upi");
        qobject_unref(reply);
        reply = qtest_qmp_assert_failure_ref(qts,
            "{'execute':'qom-get','arguments':"
            "{'path':'/machine/peripheral/kbd/controller','property':'realized'}}");
        qobject_unref(reply);
        reply = qtest_qmp(qts,
            "{'execute':'qom-get','arguments':"
            "{'path':'/machine/peripheral/upi',"
            "'property':'program-memory-type'}}");
        g_assert_true(qdict_haskey(reply, "return"));
        g_assert_cmpstr(qdict_get_str(reply, "return"), ==,
                        i < 5 ? "eprom" : "mask-rom");
        qobject_unref(reply);
        if (i == 3 || i == 8) {
            g_assert_false(qtest_qom_get_bool(qts, "/machine/peripheral/other",
                                             "keyboard-attached"));
        }
        qtest_quit(qts);
    }
}

/*
 * Ensure all entries returned by qom-list-types implements=<parent>
 * have <parent> as a parent.
 */
static void test_qom_list_parents(QTestState *qts, const char *parent)
{
    QList *types;
    QListEntry *e;
    QDict *index;

    types = qom_list_types(qts, parent, true);
    index = qom_type_index(types);

    QLIST_FOREACH_ENTRY(types, e) {
        QDict *d = qobject_to(QDict, qlist_entry_obj(e));
        const char *name = qdict_get_str(d, "name");

        g_assert(qom_has_parent(index, name, parent));
    }

    qobject_unref(types);
    qobject_unref(index);
}

static void test_qom_list_fields(void)
{
    QList *all_types;
    QList *non_abstract;
    QListEntry *e;
    QTestState *qts;

    qts = qtest_init(common_args);

    all_types = qom_list_types(qts, NULL, true);
    non_abstract = qom_list_types(qts, NULL, false);

    QLIST_FOREACH_ENTRY(all_types, e) {
        QDict *d = qobject_to(QDict, qlist_entry_obj(e));
        const char *name = qdict_get_str(d, "name");
        bool abstract = qdict_haskey(d, "abstract") ?
                        qdict_get_bool(d, "abstract") :
                        false;
        bool expected_abstract = !type_list_find(non_abstract, name);

        g_assert(abstract == expected_abstract);
    }

    test_qom_list_parents(qts, "object");
    test_qom_list_parents(qts, "device");
    test_qom_list_parents(qts, "sys-bus-device");

    qobject_unref(all_types);
    qobject_unref(non_abstract);
    qtest_quit(qts);
}

static void test_device_intro_none(void)
{
    QTestState *qts = qtest_init(common_args);
    g_autofree char *qom_tree_start = qtest_hmp(qts, "info qom-tree");
    g_autofree char *qom_tree_end = NULL;
    g_autofree char *qtree_start = qtest_hmp(qts, "info qtree");
    g_autofree char *qtree_end = NULL;

    test_one_device(qts, "nonexistent");

    /* Make sure that really nothing changed in the trees */
    qom_tree_end = qtest_hmp(qts, "info qom-tree");
    g_assert_cmpstr(qom_tree_start, ==, qom_tree_end);
    qtree_end = qtest_hmp(qts, "info qtree");
    g_assert_cmpstr(qtree_start, ==, qtree_end);

    qtest_quit(qts);
}

static void test_device_intro_abstract(void)
{
    QTestState *qts = qtest_init(common_args);
    g_autofree char *qom_tree_start = qtest_hmp(qts, "info qom-tree");
    g_autofree char *qom_tree_end = NULL;
    g_autofree char *qtree_start = qtest_hmp(qts, "info qtree");
    g_autofree char *qtree_end = NULL;

    test_one_device(qts, "device");

    /* Make sure that really nothing changed in the trees */
    qom_tree_end = qtest_hmp(qts, "info qom-tree");
    g_assert_cmpstr(qom_tree_start, ==, qom_tree_end);
    qtree_end = qtest_hmp(qts, "info qtree");
    g_assert_cmpstr(qtree_start, ==, qtree_end);

    qtest_quit(qts);
}

static void test_device_intro_concrete(const void *args)
{
    QList *types;
    QListEntry *entry;
    const char *type;
    QTestState *qts = qtest_init(args);
    g_autofree char *qom_tree_start = qtest_hmp(qts, "info qom-tree");
    g_autofree char *qom_tree_end = NULL;
    g_autofree char *qtree_start = qtest_hmp(qts, "info qtree");
    g_autofree char *qtree_end = NULL;

    types = device_type_list(qts, false);

    QLIST_FOREACH_ENTRY(types, entry) {
        type = qdict_get_try_str(qobject_to(QDict, qlist_entry_obj(entry)),
                                 "name");
        g_assert(type);
        test_one_device(qts, type);
    }

    /*
     * Some devices leave dangling pointers in QOM behind.
     * "info qom-tree" or "info qtree" have a good chance at crashing then.
     * Also make sure that the tree did not change.
     */
    qom_tree_end = qtest_hmp(qts, "info qom-tree");
    g_assert_cmpstr(qom_tree_start, ==, qom_tree_end);

    qtree_end = qtest_hmp(qts, "info qtree");
    g_assert_cmpstr(qtree_start, ==, qtree_end);

    qobject_unref(types);
    qtest_quit(qts);
}

static void test_abstract_interfaces(void)
{
    QList *all_types;
    QListEntry *e;
    QDict *index;
    QTestState *qts;

    qts = qtest_init(common_args);

    all_types = qom_list_types(qts, "interface", true);
    index = qom_type_index(all_types);

    QLIST_FOREACH_ENTRY(all_types, e) {
        QDict *d = qobject_to(QDict, qlist_entry_obj(e));
        const char *name = qdict_get_str(d, "name");

        /*
         * qom-list-types implements=interface returns all types
         * that implement _any_ interface (not just interface
         * types), so skip the ones that don't have "interface"
         * on the parent type chain.
         */
        if (!qom_has_parent(index, name, "interface")) {
            /* Not an interface type */
            continue;
        }

        g_assert(qdict_haskey(d, "abstract") && qdict_get_bool(d, "abstract"));
    }

    qobject_unref(all_types);
    qobject_unref(index);
    qtest_quit(qts);
}

static void add_machine_test_case(const char *mname)
{
    char *path, *args;

    path = g_strdup_printf("device/introspect/concrete/defaults/%s", mname);
    args = g_strdup_printf("-M %s", mname);
    qtest_add_data_func_full(path, args, test_device_intro_concrete, g_free);
    g_free(path);

    path = g_strdup_printf("device/introspect/concrete/nodefaults/%s", mname);
    args = g_strdup_printf("-nodefaults -M %s", mname);
    qtest_add_data_func_full(path, args, test_device_intro_concrete, g_free);
    g_free(path);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    qtest_add_func("device/introspect/list", test_device_intro_list);
    qtest_add_func("device/introspect/display-descriptions",
                   test_device_intro_display_descriptions);
    qtest_add_func("device/introspect/storage-descriptions",
                   test_storage_controller_descriptions);
    qtest_add_func("device/introspect/cli-help", test_device_help_cli);
    qtest_add_func("device/introspect/generic-types",
                   test_generic_device_types);
    qtest_add_func("device/introspect/att-kbd301-controller",
                   test_att_kbd301_controller);
    qtest_add_func("device/introspect/att-kbd302-controller",
                   test_att_kbd302_controller);
    qtest_add_func("device/introspect/att-kbd302-io",
                   test_att_kbd302_io);
    qtest_add_func("device/introspect/att-keyboard-explicit-controller",
                   test_att_keyboard_explicit_controller);
    qtest_add_func("device/introspect/list-fields", test_qom_list_fields);
    qtest_add_func("device/introspect/settable-only",
                   test_device_intro_settable_only);
    qtest_add_func("device/introspect/none", test_device_intro_none);
    qtest_add_func("device/introspect/abstract", test_device_intro_abstract);
    qtest_add_func("device/introspect/abstract-interfaces", test_abstract_interfaces);
    if (g_test_quick()) {
        qtest_add_data_func("device/introspect/concrete/defaults/none",
                            common_args, test_device_intro_concrete);
    } else {
        qtest_cb_for_every_machine(add_machine_test_case, true);
    }

    return g_test_run();
}

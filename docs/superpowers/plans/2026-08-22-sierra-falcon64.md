# Sierra Falcon/64 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a staged Sierra Semiconductor Falcon/64 SC15064 PCI VGA device with real PCI identity, constrained VRAM sizes, and QEMU VGA compatibility for PowerPC guests.

**Architecture:** Implement `sierra-falcon64` as a QOM subtype of the existing PCI `VGA` device. Override PCI identity and wrap the inherited realize callback only to validate the SC15064 VRAM envelope; inherit QEMU's proven VGA framebuffer/MMIO/EDID/NDRV compatibility path and do not model undocumented Sierra acceleration registers.

**Tech Stack:** QEMU QOM/qdev, PCI, VGA core, Meson/Kconfig, qtest/QMP.

**Spec:** `docs/superpowers/specs/2026-08-22-sierra-falcon64-design.md`

## Global Constraints

- PCI identity is exactly vendor `0x1a08`, device `0x0000`.
- User-visible QEMU device name is exactly `sierra-falcon64`.
- `vgamem_mb` accepts exactly 1, 2, or 4 MiB; default is 4 MiB.
- The inherited QEMU VGA/Bochs extension ABI is compatibility infrastructure, not native SC15064 register emulation.
- Do not replace the PowerMac3,1 AGP default display.
- Do not add speculative Sierra 2D accelerator registers.

---

### Task 1: Lock the device contract with qtest

**Files:**
- Create: `tests/qtest/sierra-falcon64-test.c`
- Modify: `tests/qtest/meson.build`

**Interfaces:**
- Consumes: QMP `query-pci` and qtest process launch.
- Produces: a regression test that requires a `sierra-falcon64` PCI device with vendor `0x1a08` and device `0x0000` and verifies 1/2/4 MiB launch configurations.

- [ ] **Step 1: Add a qtest that launches `mac99` with `-nodefaults -display none -device sierra-falcon64,id=falcon,vgamem_mb=N`.**

The test scans `query-pci` for `qdev_id == "falcon"` and asserts:

```c
g_assert_cmpint(qdict_get_int(id, "vendor"), ==, 0x1a08);
g_assert_cmpint(qdict_get_int(id, "device"), ==, 0x0000);
g_assert_cmpint(qdict_get_int(class_info, "class"), ==,
                PCI_CLASS_DISPLAY_VGA);
```

Register cases for `N = 1`, `2`, and `4`.

- [ ] **Step 2: Add the test to `qtests_ppc` when `CONFIG_SIERRA_FALCON64` is enabled.**

```meson
(config_all_devices.has_key('CONFIG_SIERRA_FALCON64') ?
 ['sierra-falcon64-test'] : [])
```

- [ ] **Step 3: Verify the test is a genuine feature test.**

Before implementation, the required device type does not exist, so launching the test configuration must fail specifically because `sierra-falcon64` is unavailable. In environments where a local QEMU build cannot be executed, do not claim a witnessed red phase; use repository CI as the first executable verification after the complete stable commit rather than pushing a deliberately broken master commit.

### Task 2: Add the staged Falcon/64 device

**Files:**
- Create: `hw/display/sierra_falcon64.c`
- Modify: `hw/display/Kconfig`
- Modify: `hw/display/meson.build`
- Modify: `include/hw/pci/pci_ids.h`

**Interfaces:**
- Consumes: QOM parent type `VGA`, inherited `PCIDeviceClass::realize`, inherited `vgamem_mb` property.
- Produces: QOM type `sierra-falcon64`.

- [ ] **Step 1: Add sorted PCI ID constants.**

```c
#define PCI_VENDOR_ID_SIERRA             0x1a08
#define PCI_DEVICE_ID_SIERRA_SC15064     0x0000
```

- [ ] **Step 2: Add `CONFIG_SIERRA_FALCON64`.**

```text
config SIERRA_FALCON64
    bool
    default y if PCI_DEVICES
    depends on PCI
    select VGA_PCI
```

- [ ] **Step 3: Build `sierra_falcon64.c` under that symbol.**

```meson
system_ss.add(when: 'CONFIG_SIERRA_FALCON64',
              if_true: files('sierra_falcon64.c'))
```

- [ ] **Step 4: Implement the QOM subtype.**

The child class captures the inherited PCI VGA realize callback, validates `vgamem_mb`, then delegates. Class initialization replaces only `vendor_id` and `device_id`; the inherited VGA class, ROM, BAR layout, EDID and migration behavior remain intact.

```c
#define TYPE_SIERRA_FALCON64 "sierra-falcon64"

static void (*sierra_falcon64_parent_realize)(PCIDevice *dev, Error **errp);

static void sierra_falcon64_realize(PCIDevice *dev, Error **errp)
{
    uint64_t vram_mb;

    vram_mb = object_property_get_uint(OBJECT(dev), "vgamem_mb", errp);
    if (*errp) {
        return;
    }
    if (vram_mb != 1 && vram_mb != 2 && vram_mb != 4) {
        error_setg(errp, "sierra-falcon64 vgamem_mb must be 1, 2, or 4");
        return;
    }
    sierra_falcon64_parent_realize(dev, errp);
}
```

The child instance sets inherited `vgamem_mb` to 4 before command-line property overrides are applied.

- [ ] **Step 5: Document the compatibility boundary in the source.**

State explicitly that this stage presents SC15064 PCI identity while reusing QEMU's VGA/VBE compatibility implementation; Sierra acceleration registers are intentionally absent until register-level evidence is available.

### Task 3: Verify and commit

**Files:**
- Review all files from Tasks 1-2.

**Interfaces:**
- Consumes: repository CI/status checks for the final commit.
- Produces: a stable master commit with no temporary branch.

- [ ] **Step 1: Inspect the final diff for accidental edits and confirm the PCI constants, device type, Kconfig dependency, Meson entry, and qtest all agree on names and IDs.**

- [ ] **Step 2: Commit directly to `master`; do not create a feature branch.**

Use a focused message such as:

```text
hw/display: add staged Sierra Falcon/64 VGA
```

- [ ] **Step 3: Fetch fresh commit status/CI evidence.**

Do not report the build or tests as passing unless the status/check output explicitly confirms success. If no executable CI check is attached to the commit, report that verification limitation rather than inferring success.

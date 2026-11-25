#ifndef EDID_H
#define EDID_H

#define EDID_NAME_MAX_LENGTH 12

typedef struct qemu_edid_info {
    const char *vendor; /* http://www.uefi.org/pnp_id_list */
    const char *name;
    const char *serial;
    uint16_t    width_mm;
    uint16_t    height_mm;
    uint32_t    prefx;
    uint32_t    prefy;
    uint32_t    maxx;
    uint32_t    maxy;
    uint32_t    refresh_rate;
} qemu_edid_info;

typedef enum QemuEdidInput {
    QEMU_EDID_INPUT_DISPLAYPORT = 0, /* Existing virtual monitor default */
    QEMU_EDID_INPUT_VGA,
    QEMU_EDID_INPUT_HDMI_A,
} QemuEdidInput;

void qemu_edid_generate(uint8_t *edid, size_t size,
                        qemu_edid_info *info);
void qemu_edid_generate_for_input(uint8_t *edid, size_t size,
                                  qemu_edid_info *info, QemuEdidInput input);
size_t qemu_edid_size(uint8_t *edid);
void qemu_edid_region_io(MemoryRegion *region, Object *owner,
                         uint8_t *edid, size_t size);

uint32_t qemu_edid_dpi_to_mm(uint32_t dpi, uint32_t res);

#define DEFINE_EDID_PROPERTIES(_state, _edid_info)                         \
    DEFINE_PROP_UINT32("xres", _state, _edid_info.prefx, 0),               \
    DEFINE_PROP_UINT32("yres", _state, _edid_info.prefy, 0),               \
    DEFINE_PROP_UINT32("xmax", _state, _edid_info.maxx, 0),                \
    DEFINE_PROP_UINT32("ymax", _state, _edid_info.maxy, 0),                \
    DEFINE_PROP_UINT32("refresh_rate", _state, _edid_info.refresh_rate, 0)

#endif /* EDID_H */

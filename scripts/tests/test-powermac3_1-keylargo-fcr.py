#!/usr/bin/env python3
"""Source contract for PowerMac3,1 KeyLargo feature-control registers."""

from pathlib import Path


MACIO = Path("hw/misc/macio/macio.c")
source = MACIO.read_text(encoding="utf-8")

required = {
    # FCR0: Sawtooth USB cell, PHY/pad, and shared USB reference controls.
    "KL_FCR0_SCC_A_INTF_ENABLE": "(1U << 1)",
    "KL_FCR0_USB0_PAD_SUSPEND0": "(1U << 18)",
    "KL_FCR0_USB0_PAD_SUSPEND1": "(1U << 19)",
    "KL_FCR0_USB0_CELL_ENABLE": "(1U << 20)",
    "KL_FCR0_USB1_PAD_SUSPEND0": "(1U << 22)",
    "KL_FCR0_USB1_PAD_SUSPEND1": "(1U << 23)",
    "KL_FCR0_USB1_CELL_ENABLE": "(1U << 24)",
    "KL_FCR0_USB_REF_SUSPEND": "(1U << 28)",

    # FCR2: board I/O and sleep-side data control used by KeyLargo shutdown.
    "KL_FCR2_IOBUS_ENABLE": "(1U << 1)",
    "KL_FCR2_SLEEP_STATE_BIT": "(1U << 8)",
    "KL_FCR2_MPIC_ENABLE": "(1U << 17)",
    "KL_FCR2_ALT_DATA_OUT": "(1U << 25)",

    # FCR3: KeyLargo PLL shutdown and clock-domain controls used by sleep/wake.
    "KL_FCR3_SHUTDOWN_PLL_TOTAL": "(1U << 0)",
    "KL_FCR3_SHUTDOWN_PLLKW6": "(1U << 1)",
    "KL_FCR3_SHUTDOWN_PLLKW4": "(1U << 2)",
    "KL_FCR3_SHUTDOWN_PLLKW35": "(1U << 3)",
    "KL_FCR3_SHUTDOWN_PLLKW12": "(1U << 4)",
    "KL_FCR3_PLL_RESET": "(1U << 5)",
    "KL_FCR3_SHUTDOWN_PLL2X": "(1U << 7)",
    "KL_FCR3_CLK66_ENABLE": "(1U << 8)",
    "KL_FCR3_CLK49_ENABLE": "(1U << 9)",
    "KL_FCR3_CLK45_ENABLE": "(1U << 10)",
    "KL_FCR3_CLK31_ENABLE": "(1U << 11)",
    "KL_FCR3_TIMER_CLK18_ENABLE": "(1U << 12)",
    "KL_FCR3_I2S1_CLK18_ENABLE": "(1U << 13)",
    "KL_FCR3_I2S0_CLK18_ENABLE": "(1U << 14)",
    "KL_FCR3_VIA_CLK16_ENABLE": "(1U << 15)",
    "KL_FCR3_STOPPING33_ENABLED": "(1U << 19)",
}

missing = []
for name, value in required.items():
    line = f"#define {name}"
    matching = [candidate.strip() for candidate in source.splitlines()
                if candidate.startswith(line)]
    if not matching or value not in matching[0]:
        missing.append(f"{name} = {value}")

wake_macros = [
    "#define KL_FCR4_PORT_WAKEUP_ENABLE(p)",
    "#define KL_FCR4_PORT_RESUME_WAKE_EN(p)",
    "#define KL_FCR4_PORT_CONNECT_WAKE_EN(p)",
    "#define KL_FCR4_PORT_DISCONNECT_WAKE_EN(p)",
    "#define KL_FCR4_PORT_RESUME_STAT(p)",
    "#define KL_FCR4_PORT_CONNECT_STAT(p)",
    "#define KL_FCR4_PORT_DISCONNECT_STAT(p)",
]
for macro in wake_macros:
    if macro not in source:
        missing.append(macro)

if "KL_FCR0_CHOOSE_SCCA" in source:
    missing.append("remove misleading KL_FCR0_CHOOSE_SCCA alias")

if missing:
    raise SystemExit(
        "PowerMac3,1 KeyLargo FCR contract is incomplete:\n  - "
        + "\n  - ".join(missing)
    )

print("PowerMac3,1 KeyLargo FCR contract: ok")

/*
 * Copyright (C) 2006 InnoTek Systemberatung GmbH
 *
 * This file is part of VirtualBox Open Source Edition (OSE), as
 * available from http://www.virtualbox.org. This file is free software;
 * you can redistribute it and/or modify it under the terms of the GNU
 * General Public License as published by the Free Software Foundation,
 * in version 2 as it comes in the "COPYING" file of the VirtualBox OSE
 * distribution. VirtualBox OSE is distributed in the hope that it will
 * be useful, but WITHOUT ANY WARRANTY of any kind.
 *
 * If you received this file as part of a commercial VirtualBox
 * distribution, then only the terms of your commercial VirtualBox
 * license agreement apply instead of the previous paragraph.
 *
 * Contributions after 2012-01-13 are licensed under the terms of the
 * GNU GPL, version 2 or (at your option) any later version.
 */

#ifndef AC97_H
#define AC97_H

enum {
    AC97_Reset                     = 0x00,
    AC97_Master_Volume_Mute        = 0x02,
    AC97_Headphone_Volume_Mute     = 0x04,
    AC97_Master_Volume_Mono_Mute   = 0x06,
    AC97_Master_Tone_RL            = 0x08,
    AC97_PC_BEEP_Volume_Mute       = 0x0A,
    AC97_Phone_Volume_Mute         = 0x0C,
    AC97_Mic_Volume_Mute           = 0x0E,
    AC97_Line_In_Volume_Mute       = 0x10,
    AC97_CD_Volume_Mute            = 0x12,
    AC97_Video_Volume_Mute         = 0x14,
    AC97_Aux_Volume_Mute           = 0x16,
    AC97_PCM_Out_Volume_Mute       = 0x18,
    AC97_Record_Select             = 0x1A,
    AC97_Record_Gain_Mute          = 0x1C,
    AC97_Record_Gain_Mic_Mute      = 0x1E,
    AC97_General_Purpose           = 0x20,
    AC97_3D_Control                = 0x22,
    AC97_AC_97_RESERVED            = 0x24,
    AC97_Powerdown_Ctrl_Stat       = 0x26,
    AC97_Extended_Audio_ID         = 0x28,
    AC97_Extended_Audio_Ctrl_Stat  = 0x2A,
    AC97_PCM_Front_DAC_Rate        = 0x2C,
    AC97_PCM_Surround_DAC_Rate     = 0x2E,
    AC97_PCM_LFE_DAC_Rate          = 0x30,
    AC97_PCM_LR_ADC_Rate           = 0x32,
    AC97_MIC_ADC_Rate              = 0x34,
    AC97_6Ch_Vol_C_LFE_Mute        = 0x36,
    AC97_6Ch_Vol_L_R_Surround_Mute = 0x38,

    /* AC'97 2.x modem/MC'97 extension block. */
    AC97_Extended_Modem_ID         = 0x3C,
    AC97_Extended_Modem_Ctrl_Stat  = 0x3E,
    AC97_Modem_Line1_Rate          = 0x40,
    AC97_Modem_Line2_Rate          = 0x42,
    AC97_Modem_Handset_Rate        = 0x44,
    AC97_Modem_Line1_Level         = 0x46,
    AC97_Modem_Line2_Level         = 0x48,
    AC97_Modem_Handset_Level       = 0x4A,
    AC97_Modem_GPIO_Config         = 0x4C,
    AC97_Modem_GPIO_Polarity       = 0x4E,
    AC97_Modem_GPIO_Sticky         = 0x50,
    AC97_Modem_GPIO_Wakeup         = 0x52,
    AC97_Modem_GPIO_Status         = 0x54,
    AC97_Modem_Misc_AFE            = 0x56,

    AC97_Vendor_Reserved           = 0x58,
    AC97_Sigmatel_Analog           = 0x6c, /* We emulate a Sigmatel codec */
    AC97_Sigmatel_Dac2Invert       = 0x6e, /* We emulate a Sigmatel codec */
    AC97_Vendor_ID1                = 0x7c,
    AC97_Vendor_ID2                = 0x7e
};

#define EACS_VRA 1
#define EACS_VRM 8

/* Extended Modem ID. */
#define AC97_MEI_LINE1       0x0001
#define AC97_MEI_LINE2       0x0002
#define AC97_MEI_HANDSET     0x0004
#define AC97_MEI_CID1        0x0008
#define AC97_MEI_CID2        0x0010
#define AC97_MEI_ADDR_MASK   0xc000

/* Extended Modem Status and Control. */
#define AC97_MEA_GPIO        0x0001
#define AC97_MEA_MREF        0x0002
#define AC97_MEA_ADC1        0x0004
#define AC97_MEA_DAC1        0x0008
#define AC97_MEA_ADC2        0x0010
#define AC97_MEA_DAC2        0x0020
#define AC97_MEA_HADC        0x0040
#define AC97_MEA_HDAC        0x0080
#define AC97_MEA_PRA         0x0100
#define AC97_MEA_PRB         0x0200
#define AC97_MEA_PRC         0x0400
#define AC97_MEA_PRD         0x0800
#define AC97_MEA_PRE         0x1000
#define AC97_MEA_PRF         0x2000
#define AC97_MEA_PRG         0x4000
#define AC97_MEA_PRH         0x8000
#define AC97_MEA_READY_MASK  0x00ff
#define AC97_MEA_POWER_MASK  0xff00

/* Modem GPIO status bits defined by the common MC'97 register map. */
#define AC97_GPIO_LINE1_OH      0x0001
#define AC97_GPIO_LINE1_RI      0x0002
#define AC97_GPIO_LINE1_CID     0x0004
#define AC97_GPIO_LINE1_LCS     0x0008
#define AC97_GPIO_LINE1_PULSE   0x0010
#define AC97_GPIO_LINE1_HL1R    0x0020
#define AC97_GPIO_LINE1_HOHD    0x0040
#define AC97_GPIO_LINE12_AC     0x0080
#define AC97_GPIO_LINE12_DC     0x0100
#define AC97_GPIO_LINE12_RS     0x0200
#define AC97_GPIO_LINE2_OH      0x0400
#define AC97_GPIO_LINE2_RI      0x0800
#define AC97_GPIO_LINE2_CID     0x1000
#define AC97_GPIO_LINE2_LCS     0x2000
#define AC97_GPIO_LINE2_PULSE   0x4000
#define AC97_GPIO_LINE2_HL1R    0x8000

#define MUTE_SHIFT 15

#endif /* AC97_H */

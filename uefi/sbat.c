/* SPDX-License-Identifier: GPL-2.0-only */
/* This is our own SBAT identity, not an impersonation of GRUB or a distribution. */
__attribute__((section(".sbat"), used)) const char m6501_sbat[] =
    "sbat,1,SBAT Version,sbat,1,https://github.com/rhboot/shim/blob/main/SBAT.md\n"
    "m6501-gpu-lab,1,Local M6501RM GPU lab,m6501-gpu-lab,0.1,https://github.com/Zagitta/gpu-unlock\n";

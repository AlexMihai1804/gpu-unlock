/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include "port.h"

static BOOLEAN GuAutomaticNormalAllowed(const GU_PLATFORM *p) {
  return p && !p->armed && !p->started && !p->mmio_writes && !p->owned &&
      !p->allocations && !p->dma_count && !p->retained && !p->master_attributes_pending;
}

/* No GPU access here. An input/timer/log error cancels automatic activation. */
static EFI_STATUS GuAutomaticKey(EFI_SYSTEM_TABLE *table) {
  EFI_INPUT_KEY key;
  EFI_STATUS s=table->ConIn->ReadKeyStroke(table->ConIn,&key);
  if (s==EFI_NOT_READY) return EFI_SUCCESS;
  if (EFI_ERROR(s)) return s;
  return key.ScanCode==0x17 || key.UnicodeChar==27 ? EFI_ABORTED : EFI_SUCCESS;
}

static EFI_STATUS GuAutomaticCountdown(EFI_SYSTEM_TABLE *table) {
  if (!table || !table->BootServices || !table->BootServices->Stall ||
      !table->ConIn || !table->ConIn->ReadKeyStroke) return EFI_UNSUPPORTED;
  GuLogText("AUTOBOOT: unlock in 5 seconds; Esc starts normal Windows. No U key required.\n");
  if (!GuLogReady()) return EFI_DEVICE_ERROR;
  for (UINTN i=0;i<50;i++) {
    EFI_STATUS s=GuAutomaticKey(table);
    if (EFI_ERROR(s)) return s;
    s=table->BootServices->Stall(100000);
    if (EFI_ERROR(s)) return s;
    if (i%10==9 && i<49) {
      GuLog("AUTOBOOT: %u seconds remaining.\n",(unsigned)(4-i/10));
      if (!GuLogReady()) return EFI_DEVICE_ERROR;
    }
  }
  EFI_STATUS s=GuAutomaticKey(table);
  if (EFI_ERROR(s)) return s;
  GuLogText("AUTOBOOT: countdown complete; all hardware checks remain required.\n");
  return GuLogReady() ? EFI_SUCCESS : EFI_DEVICE_ERROR;
}

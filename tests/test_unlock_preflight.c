/* SPDX-License-Identifier: GPL-2.0-only
 * Saved-ROM inputs and fake EFI services only. Never accesses physical PCI.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#undef NULL
#define MODE_UNLOCK
#define M6501_HOST_TEST
#include "../uefi/m6501.c"
#include "capture_fixture.h"

static unsigned checks;
static UINT8 rom[1048576];
static UINT32 regs[0x1000000/4], cfg[64];
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); exit(1); } } while(0)
VOID GuLog(const char *format,...) { (void)format; }
VOID GuLogText(const char *text) { (void)text; }
VOID GuConsole(const char *text) { (void)text; }
BOOLEAN GuLogReady(VOID) { return TRUE; }

static EFI_STATUS EFIAPI Pool(EFI_MEMORY_TYPE type,UINTN bytes,VOID **out) {
  CHECK(type==EfiLoaderData);
  *out=calloc(1,bytes);
  return *out ? EFI_SUCCESS : EFI_OUT_OF_RESOURCES;
}
static EFI_STATUS EFIAPI Free(VOID *data) { free(data); return EFI_SUCCESS; }
static EFI_STATUS EFIAPI ReadCfg(EFI_PCI_IO_PROTOCOL *pci,EFI_PCI_IO_PROTOCOL_WIDTH width,
                                 UINT32 offset,UINTN count,VOID *out) {
  (void)pci;
  UINTN bytes=((UINTN)1<<width)*count;
  CHECK(width<=EfiPciIoWidthUint32 && offset+bytes<=sizeof(cfg));
  memcpy(out,(UINT8 *)cfg+offset,bytes);
  return EFI_SUCCESS;
}
static EFI_STATUS EFIAPI ReadMem(EFI_PCI_IO_PROTOCOL *pci,EFI_PCI_IO_PROTOCOL_WIDTH width,
                                 UINT8 bar,UINT64 offset,UINTN count,VOID *out) {
  (void)pci;
  UINTN bytes=((UINTN)1<<width)*count;
  CHECK(!bar && width<=EfiPciIoWidthUint32 && offset+bytes<=sizeof(regs));
  memcpy(out,(UINT8 *)regs+(UINTN)offset,bytes);
  return EFI_SUCCESS;
}
static EFI_STATUS EFIAPI ForbiddenMemWrite(EFI_PCI_IO_PROTOCOL *pci,EFI_PCI_IO_PROTOCOL_WIDTH width,
                                          UINT8 bar,UINT64 offset,UINTN count,VOID *data) {
  (void)pci; (void)width; (void)bar; (void)offset; (void)count; (void)data;
  CHECK(0); return EFI_ACCESS_DENIED;
}
static EFI_STATUS EFIAPI ForbiddenCfgWrite(EFI_PCI_IO_PROTOCOL *pci,EFI_PCI_IO_PROTOCOL_WIDTH width,
                                          UINT32 offset,UINTN count,VOID *data) {
  (void)pci; (void)width; (void)offset; (void)count; (void)data;
  CHECK(0); return EFI_ACCESS_DENIED;
}
static VOID Reset(VOID) {
  static EFI_PCI_IO_PROTOCOL pci;
  static EFI_BOOT_SERVICES bs;
  memset(&pci,0,sizeof(pci)); memset(&bs,0,sizeof(bs));
  bs.AllocatePool=Pool; bs.FreePool=Free;
  pci.Pci.Read=ReadCfg; pci.Pci.Write=ForbiddenCfgWrite;
  pci.Mem.Read=ReadMem; pci.Mem.Write=ForbiddenMemWrite;
  GuInit(&bs,&pci);
  Gu.bar_base=0xdc000000; Gu.bar_size=sizeof(regs);
  Gu.owned=Gu.display_ok=TRUE;
  memset(&GuProfile,0,sizeof(GuProfile));
  GuProfile.identity=0x252010de; GuProfile.subsystem=0x13131043;
  memcpy(cfg,saved_capture_config,sizeof(cfg)); cfg[1]|=2;
  memset(regs,0,sizeof(regs));
  regs[0]=0xb76000a1; regs[0x1183a4/4]=6144;
  regs[GU_FEAT_SS0_OFFSET/4]=0x10420030;
  regs[GU_FEAT_SS1_OFFSET/4]=3; regs[GU_FEAT_PLM_OFFSET/4]=0xffffff8f;
  regs[0x625f04/4]=1; regs[0x1fa7c8/4]=0x45cb8f;
  regs[0x1fa82c/4]=0x100000; regs[0x1fa830/4]=0x16ffff0;
  regs[0x1fa824/4]=0x1ffffe00;
  regs[0x824148/4]=1; regs[0x8241e0/4]=3;
  regs[GU_GFW_PLM_OFFSET/4]=0x8b8f; regs[GU_GFW_BOOT_OFFSET/4]=0x3ff;
  regs[GU_GFW_CPUCTL_OFFSET/4]=0x10;
  memcpy((UINT8 *)regs+0x300000,rom,sizeof(rom));
}

int main(int argc,char **argv) {
  CHECK(argc==2 && M6501_EVIDENCE_READY==1);
  FILE *file=fopen(argv[1],"rb"); CHECK(file!=NULL);
  CHECK(fread(rom,1,sizeof(rom),file)==sizeof(rom) && fgetc(file)==EOF);
  fclose(file);
  Reset(); CHECK(ColdAndProm(FALSE)==EFI_SUCCESS);
  CHECK(!Gu.armed && !Gu.started && !Gu.mmio_writes && GuProfile.ss1==3);
  Reset(); ((UINT8 *)regs)[0x3fffff]^=1;
  CHECK(ColdAndProm(FALSE)==EFI_SECURITY_VIOLATION);
  Reset(); regs[0]=0xb76000a2; CHECK(ColdAndProm(FALSE)==EFI_SECURITY_VIOLATION);
  Reset(); regs[0x1183a4/4]=4096; CHECK(ColdAndProm(FALSE)==EFI_NOT_READY);
  Reset(); regs[0x1fa828/4]=0x100; CHECK(ColdAndProm(FALSE)==EFI_NOT_READY);
  Reset(); regs[GU_FEAT_SS1_OFFSET/4]=32; CHECK(ColdAndProm(FALSE)==EFI_NOT_READY);
  Reset(); regs[GU_FEAT_SS0_OFFSET/4]=0x88888888; CHECK(ColdAndProm(FALSE)==EFI_NOT_READY);
  Reset(); regs[0x824148/4]=2; CHECK(ColdAndProm(FALSE)==EFI_UNSUPPORTED);
  Reset(); regs[0x8241e0/4]=7; CHECK(ColdAndProm(FALSE)==EFI_UNSUPPORTED);
  Reset(); regs[0x8241e0/4]=1; CHECK(ColdAndProm(FALSE)==EFI_UNSUPPORTED);
  Reset(); cfg[0x68/4]|=0x10000; CHECK(ColdAndProm(FALSE)==EFI_UNSUPPORTED);
  Reset(); regs[GU_FEAT_SS0_OFFSET/4]=0x10420031;
  CHECK(ColdAndProm(FALSE)==EFI_SUCCESS && GuProfile.ss0==0x10420031);
  Reset(); regs[GU_FEAT_SS1_OFFSET/4]=4;
#ifdef M6501_SS1_FULL_EXPERIMENT
  CHECK(ColdAndProm(FALSE)==EFI_NOT_READY && GuProfile.ss1==4);
  Reset(); regs[GU_FEAT_SS1_OFFSET/4]=8;
  CHECK(ColdAndProm(FALSE)==EFI_NOT_READY && GuProfile.ss1==8);
#else
  CHECK(ColdAndProm(FALSE)==EFI_SUCCESS && GuProfile.ss1==4);
#endif
  CHECK(!Gu.armed && !Gu.started && !Gu.mmio_writes);
  printf("Saved-board preflight cases passed (%u checks); writes forbidden, all services fake.\n",checks);
  return 0;
}

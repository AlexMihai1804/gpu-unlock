/* SPDX-License-Identifier: GPL-2.0-only
 * Host mocks only. Tests never call real UEFI, PCI or MMIO services.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#undef NULL
#define MODE_CAPTURE
#define M6501_HOST_TEST
#include "../uefi/m6501.c"

GU_PLATFORM Gu;
GU_RUNTIME_PROFILE GuProfile;
static unsigned checks;
static UINT16 command;
static UINT64 attributes;
static int partial_enable, restore_fail, enable_calls, set_calls;
static UINT8 sb=1, setup=0, mok=0;
static EFI_STATUS mok_status=EFI_NOT_FOUND;
static UINTN mok_bytes=1;

#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
VOID GuLog(const char *fmt,...) { (void)fmt; }
VOID GuLogText(const char *s) { (void)s; }
BOOLEAN GuLogReady(VOID) { return TRUE; }
BOOLEAN GuSafeToReturn(VOID) { return TRUE; }

static EFI_STATUS EFIAPI ConfigRead(EFI_PCI_IO_PROTOCOL *pci,EFI_PCI_IO_PROTOCOL_WIDTH w,
                                    UINT32 off,UINTN count,VOID *out) {
  (void)pci;
  CHECK(w==EfiPciIoWidthUint16 && off==4 && count==1);
  *(UINT16 *)out=command; return EFI_SUCCESS;
}
static EFI_STATUS EFIAPI Attributes(EFI_PCI_IO_PROTOCOL *pci,EFI_PCI_IO_PROTOCOL_ATTRIBUTE_OPERATION op,
                                    UINT64 value,UINT64 *out) {
  (void)pci;
  if (op==EfiPciIoAttributeOperationGet) *out=attributes;
  else if (op==EfiPciIoAttributeOperationSupported) *out=EFI_PCI_IO_ATTRIBUTE_MEMORY;
  else if (op==EfiPciIoAttributeOperationEnable) {
    CHECK(value==EFI_PCI_IO_ATTRIBUTE_MEMORY); enable_calls++;
    attributes|=value; command|=2;
    if (partial_enable) return EFI_DEVICE_ERROR;
  } else if (op==EfiPciIoAttributeOperationSet) {
    set_calls++;
    if (restore_fail) return EFI_DEVICE_ERROR;
    attributes=value; command=(UINT16)Original[1];
  } else CHECK(0);
  return EFI_SUCCESS;
}
static EFI_STATUS EFIAPI Variable(CHAR16 *name,EFI_GUID *guid,UINT32 *flags,UINTN *size,VOID *out) {
  (void)guid; (void)flags;
  if (name[0]=='S' && name[1]=='e' && name[2]=='c') *(UINT8 *)out=sb;
  else if (name[0]=='S' && name[1]=='e' && name[2]=='t') *(UINT8 *)out=setup;
  else { *size=mok_bytes; *(UINT8 *)out=mok; return mok_status; }
  *size=1; return EFI_SUCCESS;
}
static void Reset(VOID) {
  static EFI_PCI_IO_PROTOCOL pci;
  memset(&Gu,0,sizeof(Gu)); memset(Original,0,sizeof(Original));
  memset(&pci,0,sizeof(pci));
  pci.Attributes=Attributes; pci.Pci.Read=ConfigRead;
  Gu.pci=&pci; Gu.owned=Gu.display_ok=TRUE;
  command=0; attributes=0; MemTouched=FALSE; AccessObserved=FALSE;
  partial_enable=restore_fail=enable_calls=set_calls=0;
}

int main(void) {
  static EFI_SYSTEM_TABLE table;
  static EFI_RUNTIME_SERVICES runtime;
  runtime.GetVariable=Variable; table.RuntimeServices=&runtime; St=&table;
  CHECK(Secure()==EFI_SUCCESS);
  sb=0; CHECK(Secure()==EFI_SECURITY_VIOLATION); sb=1;
  setup=1; CHECK(Secure()==EFI_SECURITY_VIOLATION); setup=0;
  mok_status=EFI_SUCCESS; mok=1; CHECK(Secure()==EFI_SECURITY_VIOLATION); mok=0;
  CHECK(Secure()==EFI_SUCCESS);
  mok_bytes=2; CHECK(Secure()==EFI_SECURITY_VIOLATION); mok_bytes=1;
  mok_status=EFI_DEVICE_ERROR; CHECK(Secure()==EFI_SECURITY_VIOLATION);
  Reset(); CHECK(MemoryEnable()==EFI_SUCCESS); CHECK(command==2 && enable_calls==1 && MemTouched);
  CHECK(MemoryRestore()==EFI_SUCCESS); CHECK(command==0 && attributes==0 && set_calls==1);
  Reset(); Original[1]=command=2; attributes=EFI_PCI_IO_ATTRIBUTE_MEMORY;
  CHECK(MemoryEnable()==EFI_SUCCESS); CHECK(enable_calls==0 && !MemTouched);
  CHECK(MemoryRestore()==EFI_SUCCESS); CHECK(command==2 && set_calls==0);
  Reset(); Original[1]=4; CHECK(MemoryEnable()==EFI_ACCESS_DENIED && !enable_calls);
  Reset(); Gu.display_ok=FALSE; CHECK(MemoryEnable()==EFI_ACCESS_DENIED && !enable_calls);
  Reset(); Gu.owned=FALSE; CHECK(MemoryEnable()==EFI_ACCESS_DENIED && !enable_calls);
  Reset(); Original[1]=2; CHECK(MemoryEnable()==EFI_ACCESS_DENIED && !enable_calls);
  Reset(); Original[1]=command=2; CHECK(MemoryEnable()==EFI_UNSUPPORTED && !enable_calls);
  Reset(); command=4; CHECK(MemoryEnable()==EFI_ACCESS_DENIED && !enable_calls);
  Reset(); Original[1]=command=2; attributes=EFI_PCI_IO_ATTRIBUTE_MEMORY;
  CHECK(MemoryEnable()==EFI_SUCCESS); command|=4;
  CHECK(MemoryRestore()==EFI_DEVICE_ERROR && !set_calls);
  Reset(); partial_enable=1; CHECK(MemoryEnable()==EFI_DEVICE_ERROR && MemTouched && command==2);
  CHECK(MemoryRestore()==EFI_SUCCESS && !command);
  Reset(); CHECK(MemoryEnable()==EFI_SUCCESS); restore_fail=1;
  CHECK(MemoryRestore()==EFI_DEVICE_ERROR);
  const UINT8 strings[]="ASUS\0M6501RM.313\0\0";
  CHECK(SmbiosString(strings,strings+sizeof(strings),2,"M6501RM.313"));
  CHECK(!SmbiosString(strings,strings+sizeof(strings),2,"M6501RM.312"));
  CHECK(!SmbiosString(strings,strings+4,2,"M6501RM.313"));
  UINT8 dmi[256]={0};
  UINTN at=0;
  dmi[0]=0; dmi[1]=6; dmi[5]=1;
  const char bios[]="M6501RM.313";
  memcpy(dmi+6,bios,sizeof(bios)); at=6+sizeof(bios)+1;
  dmi[at]=1; dmi[at+1]=6; dmi[at+5]=1;
  const char product[]="Vivobook_ASUSLaptop M6501RM_M6501RM";
  memcpy(dmi+at+6,product,sizeof(product)); at+=6+sizeof(product)+1;
  dmi[at]=127; dmi[at+1]=4; at+=6;
  SMBIOS_TABLE_3_0_ENTRY_POINT ep={0};
  memcpy(ep.AnchorString,"_SM3_",5); ep.EntryPointLength=sizeof(ep);
  ep.TableAddress=(UINTN)dmi; ep.TableMaximumSize=(UINT32)at;
  UINT8 sum=0;
  for (UINTN i=0;i<sizeof(ep);i++) sum=(UINT8)(sum+((UINT8 *)&ep)[i]);
  ep.EntryPointStructureChecksum=(UINT8)(0-sum);
  EFI_GUID smbios=SMBIOS3_TABLE_GUID;
  EFI_CONFIGURATION_TABLE cfg={.VendorGuid=smbios,.VendorTable=&ep};
  table.ConfigurationTable=&cfg; table.NumberOfTableEntries=1;
  CHECK(BoardFirmware()==EFI_SUCCESS);
  dmi[15]='2'; CHECK(BoardFirmware()==EFI_UNSUPPORTED); dmi[15]='1';
  ep.EntryPointStructureChecksum++; CHECK(BoardFirmware()==EFI_CRC_ERROR);
  table.NumberOfTableEntries=0; CHECK(BoardFirmware()==EFI_UNSUPPORTED);
  printf("%u adapter guard/attribute checks passed; all services simulated.\n",checks);
  return 0;
}

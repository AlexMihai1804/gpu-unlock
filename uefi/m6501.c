/* SPDX-License-Identifier: GPL-2.0-only
 * M6501RM adapter. Upstream transaction is compiled separately and pinned.
 * MODE_PROBE: PCI/GOP/variables only; no PCI config or MMIO writes.
 * MODE_CAPTURE: opt-in temporary MEMORY enable, PROM/cold-state reads, restore.
 * MODE_UNLOCK: opt-in SS0 transaction; requires reviewed board evidence at build.
 * No image enrolls keys, writes NVRAM, flashes ROM, or changes boot entries.
 */
#include "port.h"
#include "runtime.h"
#include "app_io.h"
#include "checks.h"
#include "ownership.h"
#include "sha256.h"
#include "runtime_profile.h"
#include "vendor/gfw_eval.h"
#include "vendor/vbios_610.h"
#include "compat/compat.h"
#include "board.h"
#ifdef M6501_SS1_FULL_EXPERIMENT
#if !defined(MODE_UNLOCK) || (defined(M6501_AUTOMATIC) && !defined(M6501_AUTO_SS1_EXPERIMENT))
#error SS1 experiment requires manual MODE_UNLOCK or explicit automatic SS1 authorization
#endif
#endif
#if defined(M6501_AUTO_SS1_EXPERIMENT) && (!defined(M6501_AUTOMATIC) || !defined(M6501_SS1_FULL_EXPERIMENT))
#error Automatic SS1 mode requires both automatic boot and full SS1 policy
#endif
#ifdef M6501_AUTOMATIC
#ifndef MODE_UNLOCK
#error Automatic mode requires MODE_UNLOCK
#endif
#include "automatic_boot.h"
#endif
#include <Protocol/LoadedImage.h>
#include <Protocol/GraphicsOutput.h>
#include <Protocol/SimpleFileSystem.h>
#include <Protocol/DevicePath.h>
#include <IndustryStandard/Acpi.h>
#include <Guid/GlobalVariable.h>
#include <Guid/FileInfo.h>
#include <Guid/SmBios.h>
#include <IndustryStandard/SmBios.h>
#ifdef MODE_UNLOCK
#include "vendor/unlock_610.h"
#include "vendor/prep_610.h"
#endif

static EFI_SYSTEM_TABLE *St;
static EFI_GUID PciGuid = EFI_PCI_IO_PROTOCOL_GUID;
static EFI_GUID GopGuid = EFI_GRAPHICS_OUTPUT_PROTOCOL_GUID;
static EFI_GUID PathGuid = EFI_DEVICE_PATH_PROTOCOL_GUID;
static EFI_GUID GlobalGuid = EFI_GLOBAL_VARIABLE;
static EFI_GUID ShimGuid = {0x605dab50,0xe046,0x4300,{0xab,0xb6,0x3d,0xd8,0x10,0xdd,0x8b,0x23}};
static UINT32 Original[64];
static UINT64 OriginalAttributes;
static BOOLEAN MemTouched;
static BOOLEAN AccessObserved;

static BOOLEAN SmbiosString(const UINT8 *strings, const UINT8 *end, UINT8 index, const char *want) {
  if (!index) return FALSE;
  while (strings<end && *strings && --index) {
    while (strings<end && *strings) strings++;
    if (strings>=end) return FALSE;
    strings++;
  }
  if (index || strings>=end) return FALSE;
  UINTN n=0;
  while (strings+n<end && strings[n] && want[n] && strings[n]==(UINT8)want[n]) n++;
  return strings+n<end && !strings[n] && !want[n];
}

static EFI_STATUS BoardFirmware(VOID) {
  EFI_GUID guid=SMBIOS3_TABLE_GUID;
  if (!St->ConfigurationTable || St->NumberOfTableEntries>256) return EFI_UNSUPPORTED;
  for (UINTN i=0;i<St->NumberOfTableEntries;i++) {
    if (memcmp(&St->ConfigurationTable[i].VendorGuid,&guid,sizeof(guid))) continue;
    const SMBIOS_TABLE_3_0_ENTRY_POINT *ep=St->ConfigurationTable[i].VendorTable;
    if (!ep || memcmp(ep->AnchorString,"_SM3_",5) || ep->EntryPointLength!=sizeof(*ep) ||
        ep->TableMaximumSize<6 || ep->TableMaximumSize>1048576 || !ep->TableAddress ||
        ep->TableAddress>MAX_UINT64-ep->TableMaximumSize) return EFI_COMPROMISED_DATA;
    const UINT8 *raw=(const UINT8 *)ep;
    UINT8 sum=0;
    for (UINTN j=0;j<ep->EntryPointLength;j++) sum=(UINT8)(sum+raw[j]);
    if (sum) return EFI_CRC_ERROR;
    raw=(const UINT8 *)(UINTN)ep->TableAddress;
    const UINT8 *end=raw+ep->TableMaximumSize;
    BOOLEAN bios=FALSE,product=FALSE;
    for (UINTN j=0;j<1024 && end-raw>=6;j++) {
      if (raw[1]<4 || raw[1]>end-raw-2) return EFI_COMPROMISED_DATA;
      const UINT8 *strings=raw+raw[1],*next=strings;
      while (next+1<end && (next[0] || next[1])) next++;
      if (next+1>=end) return EFI_COMPROMISED_DATA;
      if (raw[0]==0 && raw[1]>=6) bios=SmbiosString(strings,next+1,raw[5],"M6501RM.313");
      if (raw[0]==1 && raw[1]>=6) product=SmbiosString(strings,next+1,raw[5],"Vivobook_ASUSLaptop M6501RM_M6501RM");
      if (raw[0]==127) break;
      raw=next+2;
    }
    GuLog("SMBIOS M6501RM_product=%u BIOS_313=%u\n",product,bios);
    return bios && product && GuLogReady() ? EFI_SUCCESS : EFI_UNSUPPORTED;
  }
  return EFI_UNSUPPORTED; /* No guess from a different SMBIOS layout. */
}

static EFI_STATUS Secure(VOID) {
  UINT8 value = 0xff;
  UINTN size = 1;
  EFI_STATUS s = St->RuntimeServices->GetVariable(L"SecureBoot", &GlobalGuid, NULL, &size, &value);
  if (EFI_ERROR(s) || size != 1 || value != 1) return EFI_SECURITY_VIOLATION;
  size = 1; value = 0xff;
  s = St->RuntimeServices->GetVariable(L"SetupMode", &GlobalGuid, NULL, &size, &value);
  if (EFI_ERROR(s) || size != 1 || value != 0) return EFI_SECURITY_VIOLATION;
  size = 1; value = 0xff;
  s = St->RuntimeServices->GetVariable(L"MokSBStateRT", &ShimGuid, NULL, &size, &value);
  if (s != EFI_NOT_FOUND && (EFI_ERROR(s) || size != 1 || value != 0))
    return EFI_SECURITY_VIOLATION;
  GuLogText("SECURE SecureBoot=1 SetupMode=0; MokSBStateRT absent or zero\n");
  return GuLogReady() ? EFI_SUCCESS : EFI_DEVICE_ERROR;
}

static EFI_STATUS Inventory(VOID) {
  EFI_HANDLE *handles = NULL;
  UINTN count = 0, matches = 0;
  EFI_STATUS s = Gu.bs->LocateHandleBuffer(ByProtocol, &PciGuid, NULL, &count, &handles);
  if (EFI_ERROR(s) || !handles || count > 512) return EFI_UNSUPPORTED;
  for (UINTN i = 0; i < count; i++) {
    EFI_PCI_IO_PROTOCOL *pci = NULL;
    UINTN seg, bus, dev, fun;
    UINT32 config[64];
    if (EFI_ERROR(Gu.bs->HandleProtocol(handles[i], &PciGuid, (VOID **)&pci)) || !pci ||
        EFI_ERROR(pci->GetLocation(pci, &seg, &bus, &dev, &fun)) ||
        EFI_ERROR(pci->Pci.Read(pci, EfiPciIoWidthUint32, 0, 64, config))) continue;
    if ((config[2] >> 24) == 3 || (config[2] >> 16) == 0x0604)
      GuLog("PCI %04x:%02x:%02x.%u id=%08x subsystem=%08x classrev=%08x command=%04x ROM_bytes=%llu\n",
            (unsigned)seg,(unsigned)bus,(unsigned)dev,(unsigned)fun,config[0],config[11],config[2],
            config[1]&0xffff,(unsigned long long)pci->RomSize);
    if (seg || bus != 1 || dev || fun) continue;
    if (config[0] != 0x252010deU || config[11] != 0x13131043U || config[2] != 0x030000a1U)
      continue;
    Gu.handle = handles[i]; Gu.pci = pci; matches++;
    memcpy(Original, config, sizeof(Original));
    for (UINTN j = 0; j < 64; j += 4)
      GuLog("CFG %02x %08x %08x %08x %08x\n",(unsigned)(j*4),config[j],config[j+1],config[j+2],config[j+3]);
  }
  GuFree(handles);
  GuLog("TARGET exact_matches=%u\n",(unsigned)matches);
  return matches == 1 && GuLogReady() ? EFI_SUCCESS : EFI_UNSUPPORTED;
}

static BOOLEAN DisplaySafe(VOID) {
  EFI_HANDLE *handles = NULL;
  UINTN count = 0, physical = 0;
  BOOLEAN safe = TRUE;
  EFI_STATUS s = Gu.bs->LocateHandleBuffer(ByProtocol, &GopGuid, NULL, &count, &handles);
  if (EFI_ERROR(s) || !handles || !count || count > 16) return FALSE;
  for (UINTN i = 0; i < count; i++) {
    EFI_GRAPHICS_OUTPUT_PROTOCOL *gop = NULL;
    EFI_DEVICE_PATH_PROTOCOL *path = NULL;
    s = Gu.bs->HandleProtocol(handles[i], &GopGuid, (VOID **)&gop);
    if (EFI_ERROR(s) || !gop || !gop->Mode) { safe = FALSE; break; }
    EFI_STATUS ps = Gu.bs->HandleProtocol(handles[i], &PathGuid, (VOID **)&path);
    if ((ps == EFI_NOT_FOUND || ps == EFI_UNSUPPORTED) && !path &&
        !gop->Mode->FrameBufferBase && !gop->Mode->FrameBufferSize) {
      GuLogText("GOP pathless zero-framebuffer console aggregator\n");
      continue;
    }
    EFI_HANDLE owner = NULL;
    EFI_PCI_IO_PROTOCOL *pci = NULL;
    EFI_DEVICE_PATH_PROTOCOL *remaining = path;
    UINT32 id = 0;
    BOOLEAN good = !EFI_ERROR(ps) && path &&
        GuIndependentDisplay(Gu.bs,Gu.pci,Gu.handle,path) &&
        !EFI_ERROR(Gu.bs->LocateDevicePath(&PciGuid,&remaining,&owner)) && owner &&
        !EFI_ERROR(Gu.bs->HandleProtocol(owner,&PciGuid,(VOID **)&pci)) && pci &&
        !EFI_ERROR(pci->Pci.Read(pci,EfiPciIoWidthUint32,0,1,&id)) && id == 0x16811002U &&
        gop->Mode->Info && gop->Mode->SizeOfInfo >= sizeof(*gop->Mode->Info) &&
        gop->Mode->FrameBufferBase && gop->Mode->FrameBufferSize;
    GuLog("GOP owner=%08x independent_AMD=%u framebuffer=%#llx bytes=%zu\n",id,good,
          (unsigned long long)gop->Mode->FrameBufferBase,(size_t)gop->Mode->FrameBufferSize);
    if (!good) safe = FALSE;
    else physical++;
  }
  GuFree(handles);
  return safe && physical == 1 && GuLogReady();
}

#if !defined(MODE_PROBE) && !defined(MODE_HANDOFF)
static EFI_STATUS BarAndBridges(VOID) {
  UINT32 pci_check[64];
  GU_CAPS caps;
  memcpy(pci_check,Original,sizeof(pci_check));
  /* Validate D0, MSI/MSI-X, FLR and capability layout before enabling MEM.
     Set MEM only in this CPU-owned validation copy, never through Pci.Write. */
  pci_check[1]|=2;
  if (!GuCheckConfig(pci_check,0,1,0,0,&caps)) return EFI_UNSUPPORTED;
  VOID *raw = NULL;
  EFI_STATUS s = Gu.pci->GetBarAttributes(Gu.pci,0,NULL,&raw);
  if (EFI_ERROR(s) || !raw) return EFI_UNSUPPORTED;
  EFI_ACPI_ADDRESS_SPACE_DESCRIPTOR *r = raw;
  UINT32 lo = Original[4];
  UINT64 base = lo & ~15U;
  if ((lo & 6) == 4) base |= (UINT64)Original[5] << 32;
  BOOLEAN good = !(lo & 1) && ((lo & 6) == 0 || (lo & 6) == 4) &&
      r->Desc == ACPI_ADDRESS_SPACE_DESCRIPTOR && r->Len == sizeof(*r)-3 && !r->ResType &&
      r->AddrLen == 0x1000000 && r->AddrRangeMin == base && !r->AddrTranslationOffset &&
      base && !(base & 0xffffff) && base <= MAX_UINT64-0xffffff;
  if (good) { Gu.bar_base = base; Gu.bar_size = r->AddrLen; }
  GuFree(raw);
  if (!good) return EFI_UNSUPPORTED;
  EFI_HANDLE *handles = NULL;
  UINTN count = 0, bridges = 0;
  s = Gu.bs->LocateHandleBuffer(ByProtocol,&PciGuid,NULL,&count,&handles);
  if (EFI_ERROR(s) || !handles || count > 512) return EFI_UNSUPPORTED;
  for (UINTN i=0;i<count;i++) {
    EFI_PCI_IO_PROTOCOL *pci = NULL;
    UINTN seg,bus,dev,fun;
    UINT32 c[16];
    if (EFI_ERROR(Gu.bs->HandleProtocol(handles[i],&PciGuid,(VOID **)&pci)) || !pci ||
        EFI_ERROR(pci->GetLocation(pci,&seg,&bus,&dev,&fun)) || seg ||
        EFI_ERROR(pci->Pci.Read(pci,EfiPciIoWidthUint32,0,16,c))) continue;
    if ((c[2]>>16)!=0x0604 || ((c[6]>>8)&255)>1 || ((c[6]>>16)&255)<1) continue;
    UINT64 low = (UINT64)(c[8]&0xfff0)<<16;
    UINT64 high = (UINT64)(c[8]&0xfff00000)|0xfffff;
    good = (c[1]&2) && low<=base && high>=base+Gu.bar_size-1;
    GuLog("BRIDGE %u:%u.%u MEM=%u window=%#llx:%#llx covers=%u\n",(unsigned)bus,
          (unsigned)dev,(unsigned)fun,!!(c[1]&2),(unsigned long long)low,(unsigned long long)high,good);
    bridges++; if (!good) break;
  }
  GuFree(handles);
  return good && bridges && GuLogReady() ? EFI_SUCCESS : EFI_UNSUPPORTED;
}

static EFI_STATUS Confirm(CHAR16 wanted) {
  if (!St->ConIn || !St->ConIn->ReadKeyStroke || !St->ConIn->Reset) return EFI_UNSUPPORTED;
  EFI_STATUS s = St->ConIn->Reset(St->ConIn,FALSE);
  if (EFI_ERROR(s)) return s;
  GuLog("Press %c for this one attempt; Esc or 30 seconds cancels.\n",(int)wanted);
  if (!GuLogReady()) return EFI_DEVICE_ERROR;
  for (UINTN i=0;i<300;i++) {
    EFI_INPUT_KEY k;
    s = St->ConIn->ReadKeyStroke(St->ConIn,&k);
    if (!EFI_ERROR(s)) {
      if (k.UnicodeChar==wanted || k.UnicodeChar==wanted+32) return EFI_SUCCESS;
      if (k.ScanCode==0x17 || k.UnicodeChar==27) return EFI_ABORTED;
    } else if (s!=EFI_NOT_READY) return s;
    GuStall(100000);
  }
  return EFI_TIMEOUT;
}

static EFI_STATUS MemoryEnable(VOID) {
  UINT64 supported = 0, attrs = 0;
  UINT16 command = 0xffff;
  if (!Gu.owned || !Gu.display_ok || (Original[1]&5)) return EFI_ACCESS_DENIED;
  /* Recheck live decode/BME after the interactive pause and exclusive claim.
     A stale protocol cache must not conceal a changed hardware Command. */
  EFI_STATUS s=Gu.pci->Pci.Read(Gu.pci,EfiPciIoWidthUint16,4,1,&command);
  if (EFI_ERROR(s) || command!=(Original[1]&0xffff)) return EFI_ACCESS_DENIED;
  s = Gu.pci->Attributes(Gu.pci,EfiPciIoAttributeOperationGet,0,&OriginalAttributes);
  if (!EFI_ERROR(s)) s=Gu.pci->Attributes(Gu.pci,EfiPciIoAttributeOperationSupported,0,&supported);
  if (EFI_ERROR(s) || !(supported&EFI_PCI_IO_ATTRIBUTE_MEMORY) ||
      !!(OriginalAttributes&EFI_PCI_IO_ATTRIBUTE_MEMORY)!=!!(Original[1]&2) ||
      (OriginalAttributes&EFI_PCI_IO_ATTRIBUTE_BUS_MASTER)) return EFI_UNSUPPORTED;
  AccessObserved=TRUE;
  if (!(Original[1]&2)) {
    MemTouched=TRUE; /* Restore even if Attributes returns an error after a partial change. */
    s=Gu.pci->Attributes(Gu.pci,EfiPciIoAttributeOperationEnable,EFI_PCI_IO_ATTRIBUTE_MEMORY,NULL);
  }
  if (!EFI_ERROR(s)) s=Gu.pci->Attributes(Gu.pci,EfiPciIoAttributeOperationGet,0,&attrs);
  if (!EFI_ERROR(s)) s=Gu.pci->Pci.Read(Gu.pci,EfiPciIoWidthUint16,4,1,&command);
  GuLog("MEM_ENABLE status=%#llx command=%#x attributes=%#llx\n",(unsigned long long)s,command,
        (unsigned long long)attrs);
  return !EFI_ERROR(s) && command==((Original[1]&0xffff)|2) &&
      attrs==(OriginalAttributes|EFI_PCI_IO_ATTRIBUTE_MEMORY) ? EFI_SUCCESS : EFI_DEVICE_ERROR;
}

static EFI_STATUS MemoryRestore(VOID) {
  if (!AccessObserved && !MemTouched) return EFI_SUCCESS;
  if (!GuSafeToReturn() || Gu.allocations || Gu.dma_count) return EFI_ACCESS_DENIED;
  UINT64 attrs=~0ULL;
  UINT16 command=0xffff;
  EFI_STATUS s=EFI_SUCCESS;
  if (MemTouched) s=Gu.pci->Attributes(Gu.pci,EfiPciIoAttributeOperationSet,OriginalAttributes,NULL);
  if (!EFI_ERROR(s)) s=Gu.pci->Attributes(Gu.pci,EfiPciIoAttributeOperationGet,0,&attrs);
  if (!EFI_ERROR(s)) s=Gu.pci->Pci.Read(Gu.pci,EfiPciIoWidthUint16,4,1,&command);
  BOOLEAN restored=!EFI_ERROR(s) && attrs==OriginalAttributes && command==(Original[1]&0xffff);
  GuLog("MEM_RESTORE status=%#llx confirmed=%u command=%#x\n",(unsigned long long)s,restored,command);
  return restored ? EFI_SUCCESS : EFI_DEVICE_ERROR;
}

static EFI_STATUS SaveProm(const VOID *data, UINTN bytes) {
  EFI_GUID loadedGuid=EFI_LOADED_IMAGE_PROTOCOL_GUID,fsGuid=EFI_SIMPLE_FILE_SYSTEM_PROTOCOL_GUID;
  EFI_LOADED_IMAGE_PROTOCOL *loaded=NULL;
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *fs=NULL;
  EFI_FILE_PROTOCOL *root=NULL,*file=NULL;
  EFI_STATUS s=Gu.bs->HandleProtocol(Gu.image,&loadedGuid,(VOID **)&loaded);
  if (!EFI_ERROR(s)) s=Gu.bs->HandleProtocol(loaded->DeviceHandle,&fsGuid,(VOID **)&fs);
  if (!EFI_ERROR(s)) s=fs->OpenVolume(fs,&root);
  if (EFI_ERROR(s)) return s;
  s=EFI_VOLUME_FULL;
  for (UINTN i=0;i<100;i++) {
    CHAR16 name[]=L"\\RTX-UNLOCK\\PROM00.ROM";
    name[16]=(CHAR16)('0'+i/10); name[17]=(CHAR16)('0'+i%10);
    s=root->Open(root,&file,name,EFI_FILE_MODE_READ,0);
    if (!EFI_ERROR(s)) { file->Close(file); file=NULL; s=EFI_VOLUME_FULL; continue; }
    if (s!=EFI_NOT_FOUND) break;
    s=root->Open(root,&file,name,EFI_FILE_MODE_READ|EFI_FILE_MODE_WRITE|EFI_FILE_MODE_CREATE,0);
    if (!EFI_ERROR(s)) {
      UINTN n=bytes;
      s=file->Write(file,&n,(VOID *)data);
      if (!EFI_ERROR(s) && n!=bytes) s=EFI_DEVICE_ERROR;
      if (!EFI_ERROR(s)) s=file->Flush(file);
      EFI_STATUS closed=file->Close(file); file=NULL;
      if (!EFI_ERROR(s)) s=closed;
      GuLog("PROM_FILE index=%u bytes=%zu status=%#llx\n",(unsigned)i,(size_t)bytes,(unsigned long long)s);
    }
    break;
  }
  EFI_STATUS closed=root->Close(root);
  return EFI_ERROR(s) ? s : closed;
}

static EFI_STATUS ColdAndProm(BOOLEAN save) {
  GU_CAPS caps;
  UINT32 current[64];
  EFI_STATUS s=Gu.pci->Pci.Read(Gu.pci,EfiPciIoWidthUint32,0,64,current);
  if (EFI_ERROR(s) || !GuCheckConfig(current,0,1,0,0,&caps)) return EFI_UNSUPPORTED;
  Gu.pm_cap=caps.pm; Gu.pcie_cap=caps.pcie; Gu.pcie_version=caps.pcie_version;
  Gu.msi_cap=caps.msi; Gu.msix_cap=caps.msix;
  GuProfile.chip=GuRead32(0);
  GuProfile.class_revision=current[2]; GuProfile.fb_mib=GuRead32(0x1183a4);
  GuProfile.ss0=GuRead32(GU_FEAT_SS0_OFFSET); GuProfile.ss1=GuRead32(GU_FEAT_SS1_OFFSET);
  GuProfile.plm=GuRead32(GU_FEAT_PLM_OFFSET); GuProfile.bar_size=Gu.bar_size;
  const UINT32 layout_offsets[]={0x625f04,0x1fa7c8,0x1fa82c,0x1fa830,0x1fa824,0x1fa828};
  for (UINTN i=0;i<6;i++) {
    GuProfile.layout[i]=GuRead32(layout_offsets[i]);
    GuLog("LAYOUT_REG offset=%#x value=%#x\n",layout_offsets[i],GuProfile.layout[i]);
  }
  UINT32 booter_fuse=GuRead32(0x824148);
  GuLog("BOOTER_FUSE raw=%#x\n",booter_fuse);
  struct gpu_unlock_gfw_sample sample={.config_ok=true,.plm=GuRead32(GU_GFW_PLM_OFFSET),
      .boot=GuRead32(GU_GFW_BOOT_OFFSET),.cpuctl=GuRead32(GU_GFW_CPUCTL_OFFSET)};
  UINT32 wpr=GuRead32(0x1fa828);
  GuLog("COLD chip=%#x fb_mib=%u ss0=%#x ss1=%#x plm=%#x WPR2_HI=%#x GFW=%#x/%#x/%#x\n",
        GuProfile.chip,GuProfile.fb_mib,GuProfile.ss0,GuProfile.ss1,GuProfile.plm,wpr,
        sample.plm,sample.boot,sample.cpuctl);
  /* Report rather than borrow this board's chip ID from another laptop. */
  if (Gu.fault || GuProfile.fb_mib!=6144 || !GuProfile.chip || GuProfile.chip==~0U ||
      GuProfile.ss0==~0U || GuProfile.ss0==0x88888888U || GuProfile.ss1>15 ||
      GuProfile.plm==~0U || (wpr>>4) || gpu_unlock_gfw_assess(&sample)) return EFI_NOT_READY;
#ifdef M6501_SS1_FULL_EXPERIMENT
  /* Only the SS1=3 entry state captured on this board has been reviewed. */
  if (GuProfile.ss1!=3U) return EFI_NOT_READY;
  GuLogText("EXPERIMENT SS0 target=88888888 SS1 entry=3 target=8; TF32 effect unverified\n");
#endif
  VOID *prom=GuAlloc(1048576);
  if (!prom) return EFI_OUT_OF_RESOURCES;
  GuCopyFromIo(prom,(VOID *)(UINTN)(Gu.bar_base+0x300000),1048576);
  UINT8 hash[32];
  static const char hex[]="0123456789abcdef";
  GuSha256(prom,1048576,hash);
  for (UINTN i=0;i<32;i++) { GuProfile.prom_sha256[2*i]=hex[hash[i]>>4]; GuProfile.prom_sha256[2*i+1]=hex[hash[i]&15]; }
  GuProfile.prom_sha256[64]=0;
  GuLog("PROM_SHA256 %s\n",GuProfile.prom_sha256);
  struct gpu_unlock_fwsec fw;
  int parsed=Gu.fault ? -EIO : gpu_unlock_vbios_fwsec(prom,1048576,&fw);
  if (save && !Gu.fault) s=SaveProm(prom,1048576);
  if (!parsed) GuLog("FWSEC image_off=%#x bytes=%#x imem=%#x dmem=%#x engine=%#x ucode=%u signatures=%u versions=%#x\n",
                    fw.image_off,fw.image_size,fw.imem_size,fw.dmem_size,fw.engine_mask,fw.ucode_id,fw.sig_count,fw.sig_versions);
  UINT32 fwsec_fuse=~0U;
  if (!parsed && fw.ucode_id && fw.ucode_id<=16) {
    fwsec_fuse=GuRead32(0x8241c0+(fw.ucode_id-1)*4);
    GuLog("FWSEC_FUSE raw=%#x\n",fwsec_fuse);
  }
  GuFree(prom);
  if (Gu.fault || parsed || fw.engine_mask!=0x400 || fw.ucode_id!=9) return EFI_UNSUPPORTED;
#ifdef MODE_UNLOCK
  if (GuProfile.chip!=M6501_EXPECTED_CHIP || strcmp(GuProfile.prom_sha256,M6501_EXPECTED_PROM))
    return EFI_SECURITY_VIOLATION;
  UINT32 sig_offset=0;
  UINT32 fwsec_version=gpu_unlock_fuse_version(fwsec_fuse);
  int fuse_check=gpu_unlock_fwsec_sig_offset(fw.sig_versions,fwsec_version,384,&sig_offset);
  GuLog("FUSE_PREFLIGHT booter_raw=%#x version=%u FWSEC_raw=%#x version=%u sig_offset=%#x result=%d\n",
        booter_fuse,gpu_unlock_fuse_version(booter_fuse),fwsec_fuse,fwsec_version,sig_offset,fuse_check);
  if (booter_fuse!=M6501_EXPECTED_BOOTER_FUSE || fwsec_fuse!=M6501_EXPECTED_FWSEC_FUSE ||
      fuse_check || sig_offset>fw.sig_bytes || fw.sig_bytes-sig_offset<384 || !GuLogReady())
    return EFI_UNSUPPORTED;
#endif
  return EFI_ERROR(s) || !GuLogReady() ? EFI_DEVICE_ERROR : EFI_SUCCESS;
}

static VOID Stop(VOID) {
  Gu.bs->SetWatchdogTimer(0,0,0,NULL);
  GuLogText("STOP. No further boot handoff. Use full physical power off; no same-cycle retry.\n");
  for (;;) Gu.bs->Stall(1000000);
}
#endif

#if defined(MODE_UNLOCK) || defined(MODE_HANDOFF)
static EFI_STATUS LoadWindows(EFI_HANDLE *image) {
  EFI_GUID fsGuid=EFI_SIMPLE_FILE_SYSTEM_PROTOCOL_GUID;
  EFI_HANDLE *handles=NULL,chosen=NULL;
  UINTN count=0,matches=0;
  EFI_STATUS s=Gu.bs->LocateHandleBuffer(ByProtocol,&fsGuid,NULL,&count,&handles);
  if (EFI_ERROR(s) || !handles || count>128) return EFI_UNSUPPORTED;
  for (UINTN i=0;i<count;i++) {
    EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *fs=NULL;
    EFI_FILE_PROTOCOL *root=NULL,*file=NULL;
    EFI_DEVICE_PATH_PROTOCOL *path=NULL;
    if (EFI_ERROR(Gu.bs->HandleProtocol(handles[i],&PathGuid,(VOID **)&path)) || !path) continue;
    BOOLEAN partition=FALSE;
    UINTN total=0;
    for (UINTN j=0;j<64 && total<4096;j++) {
      UINTN n=path->Length[0]+((UINTN)path->Length[1]<<8);
      if (n<4 || n>4096-total || path->Type==END_DEVICE_PATH_TYPE) break;
      if (path->Type==MEDIA_DEVICE_PATH && path->SubType==MEDIA_HARDDRIVE_DP && n==sizeof(HARDDRIVE_DEVICE_PATH)) {
        HARDDRIVE_DEVICE_PATH *hd=(VOID *)path;
        if (hd->MBRType==0x02 && hd->SignatureType==SIGNATURE_TYPE_GUID &&
            !memcmp(hd->Signature,M6501_WINDOWS_GUID,16)) partition=TRUE;
      }
      total+=n; path=(VOID *)((UINT8 *)path+n);
    }
    if (!partition || EFI_ERROR(Gu.bs->HandleProtocol(handles[i],&fsGuid,(VOID **)&fs)) || !fs ||
        EFI_ERROR(fs->OpenVolume(fs,&root))) continue;
    s=root->Open(root,&file,L"\\EFI\\Microsoft\\Boot\\bootmgfw.efi",EFI_FILE_MODE_READ,0);
    if (!EFI_ERROR(s)) { matches++; chosen=handles[i]; file->Close(file); }
    root->Close(root);
  }
  GuFree(handles);
  if (matches!=1) return EFI_NOT_FOUND;
  EFI_DEVICE_PATH_PROTOCOL *path=NULL;
  s=Gu.bs->HandleProtocol(chosen,&PathGuid,(VOID **)&path);
  if (EFI_ERROR(s) || !path) return EFI_UNSUPPORTED;
  UINTN size=0;
  for (UINTN j=0;j<64;j++) {
    EFI_DEVICE_PATH_PROTOCOL *node=(VOID *)((UINT8 *)path+size);
    UINTN n=node->Length[0]+((UINTN)node->Length[1]<<8);
    if (n<4 || n>4096-size) return EFI_COMPROMISED_DATA;
    if (node->Type==END_DEVICE_PATH_TYPE) {
      if (n!=4 || node->SubType!=END_ENTIRE_DEVICE_PATH_SUBTYPE) return EFI_UNSUPPORTED;
      break;
    }
    size+=n;
    if (j==63) return EFI_UNSUPPORTED;
  }
  const CHAR16 name[]=L"\\EFI\\Microsoft\\Boot\\bootmgfw.efi";
  UINTN fn=sizeof(FILEPATH_DEVICE_PATH)-sizeof(CHAR16)+sizeof(name);
  UINT8 *out=GuAlloc(size+fn+4);
  if (!out) return EFI_OUT_OF_RESOURCES;
  memcpy(out,path,size);
  FILEPATH_DEVICE_PATH *fp=(VOID *)(out+size);
  fp->Header.Type=MEDIA_DEVICE_PATH; fp->Header.SubType=MEDIA_FILEPATH_DP;
  fp->Header.Length[0]=(UINT8)fn; fp->Header.Length[1]=(UINT8)(fn>>8);
  memcpy(fp->PathName,name,sizeof(name));
  EFI_DEVICE_PATH_PROTOCOL *end=(VOID *)(out+size+fn);
  end->Type=END_DEVICE_PATH_TYPE; end->SubType=END_ENTIRE_DEVICE_PATH_SUBTYPE; end->Length[0]=4;
  s=Gu.bs->LoadImage(FALSE,Gu.image,(VOID *)out,NULL,0,image);
  GuFree(out);
  GuLog("WINDOWS_PRELOAD status=%#llx unique_GUID_match=1\n",(unsigned long long)s);
  return s;
}
#endif

#ifdef M6501_AUTOMATIC
/* Only a cancelled/rejected preflight may continue normally. Any transaction
 * failure still reaches Stop(), exactly as in the validated manual image. */
static EFI_STATUS AutoNormalWindows(EFI_STATUS reason) {
  if (!GuAutomaticNormalAllowed(&Gu) || !GuSafeToReturn()) return EFI_ACCESS_DENIED;
  GuLog("AUTOBOOT: skipped before GPU writes, reason=%#llx; normal Windows.\n",
        (unsigned long long)reason);
  EFI_HANDLE windows=NULL;
  EFI_STATUS s=LoadWindows(&windows);
  EFI_STATUS closed=GuIoClose();
  if (EFI_ERROR(s) || EFI_ERROR(closed)) {
    if (windows) Gu.bs->UnloadImage(windows);
    return EFI_ERROR(s) ? s : closed;
  }
  return Gu.bs->StartImage(windows,NULL,NULL);
}
#endif

#ifndef M6501_HOST_TEST
EFI_STATUS EFIAPI efi_main(EFI_HANDLE image, EFI_SYSTEM_TABLE *table) {
  if (!table || !table->BootServices || !table->RuntimeServices) return EFI_INVALID_PARAMETER;
  St=table; GuInit(table->BootServices,NULL); Gu.image=image;
  GuProfile.identity=0x252010deU; GuProfile.subsystem=0x13131043U;
  EFI_STATUS s=GuIoOpen(image,table);
  if (EFI_ERROR(s)) {
#ifdef M6501_AUTOMATIC
    return AutoNormalWindows(s);
#else
    GuIoClose(); return s;
#endif
  }
  GuLogText("M6501RM GPU lab 0.1 - experimental, hardware unlock not validated\n");
#ifdef M6501_SS1_FULL_EXPERIMENT
#ifdef M6501_AUTO_SS1_EXPERIMENT
  GuLogText("AUTOMATIC TF32 / SS1 FULL EXPERIMENT. User-requested; physical TF32 gain unverified.\n");
  GuConsole("FP16/BF16/TF32 SS1=8 experiment. Esc during countdown skips GPU changes.\n");
#else
  GuLogText("MANUAL TF32 / SS1 FULL EXPERIMENT. Not an automatic or validated daily profile.\n");
  GuConsole("TF32 SS1=8 experiment: press T only for the separately approved physical test.\n");
#endif
#endif
  s=Secure();
  if (!EFI_ERROR(s)) s=BoardFirmware();
  if (!EFI_ERROR(s)) s=Inventory();
  if (!EFI_ERROR(s)) { Gu.display_check=DisplaySafe; Gu.display_ok=DisplaySafe(); }
#ifdef MODE_PROBE
  GuLog("PROBE complete: no GPU config writes, no MMIO, no firmware load. display_safe=%u\n",Gu.display_ok);
#elif defined(MODE_HANDOFF)
  EFI_HANDLE windows=NULL;
  if (!EFI_ERROR(s) && !Gu.display_ok) s=EFI_UNSUPPORTED;
  if (!EFI_ERROR(s)) s=LoadWindows(&windows);
  GuLog("HANDOFF-ONLY status=%#llx no_GPU_writes=1 no_firmware_load=1\n",(unsigned long long)s);
  if (!EFI_ERROR(s) && GuLogReady()) {
    s=GuIoClose();
    if (EFI_ERROR(s)) { Gu.bs->UnloadImage(windows); return s; }
    return Gu.bs->StartImage(windows,NULL,NULL);
  }
  if (windows) Gu.bs->UnloadImage(windows);
#else
  if (!EFI_ERROR(s) && !Gu.display_ok) s=EFI_UNSUPPORTED;
#ifdef MODE_UNLOCK
  if (!EFI_ERROR(s) && !M6501_EVIDENCE_READY) {
    GuLogText("BLOCKED: original PROM/chip and Windows partition have not been reviewed for this build.\n");
    s=EFI_SECURITY_VIOLATION;
  }
#endif
  if (!EFI_ERROR(s)) s=BarAndBridges();
  if (!EFI_ERROR(s)) s=
#ifdef M6501_AUTOMATIC
      GuAutomaticCountdown(St);
#else
      Confirm(
#ifdef MODE_CAPTURE
      'P'
#elif defined(M6501_SS1_FULL_EXPERIMENT)
      'T'
#else
      'U'
#endif
  );
#endif
  if (!EFI_ERROR(s)) s=GuClaimController();
  if (!EFI_ERROR(s)) s=MemoryEnable();
  if (!EFI_ERROR(s)) s=ColdAndProm(
#ifdef MODE_CAPTURE
      TRUE
#else
      FALSE
#endif
  );
#ifdef MODE_UNLOCK
  EFI_HANDLE windows=NULL;
  if (!EFI_ERROR(s)) s=LoadWindows(&windows);
  if (!EFI_ERROR(s)) s=GuLoadAssets();
  if (!EFI_ERROR(s)) s=Secure();
  if (!EFI_ERROR(s)) s=Gu.bs->SetWatchdogTimer(0,0,0,NULL);
  if (!EFI_ERROR(s) && GuLogReady()) {
    Gu.armed=TRUE;
    UINT64 mask=0xffffffffULL;
    struct pci_dev device={.dev={.dma_mask=&mask,.coherent_dma_mask=0xffffffffULL},.pm_cap=Gu.pm_cap,.refs=1};
    struct gpu_unlock_610_shared shared={0};
    int ret=gpu_unlock_610_load_shared(&device,&shared);
    if (!ret) ret=gpu_unlock_610_unlock(&device,&shared);
    EFI_STATUS contained=GuClearMaster();
    GuLog("TRANSACTION result=%d contained=%#llx FLRs=%u maps=%u retained=%u quiesced=%u fault=%u\n",
          ret,(unsigned long long)contained,Gu.flrs,Gu.dma_count,Gu.retained,Gu.quiesced,Gu.fault);
    if (ret || EFI_ERROR(contained) || !GuSafeToReturn() || Gu.allocations || Gu.dma_count ||
        Gu.flrs!=1 || !GuLogReady()) Stop();
    gpu_unlock_610_release_shared(&shared);
    UINT32 ss0=GuRead32(GU_FEAT_SS0_OFFSET),ss1=GuRead32(GU_FEAT_SS1_OFFSET);
#ifdef M6501_SS1_FULL_EXPERIMENT
    GuLog("FINAL_SELECTORS SS0=%#x SS1=%#x target_SS1=8 entry_SS1=%#x EXPERIMENT=1\n",ss0,ss1,GuProfile.ss1);
    if (Gu.fault || ss0!=0x88888888U || ss1!=8U || !GuLogReady()) Stop();
#else
    GuLog("FINAL_SELECTORS SS0=%#x SS1=%#x preserved_SS1=%#x\n",ss0,ss1,GuProfile.ss1);
    if (Gu.fault || ss0!=0x88888888U || ss1!=GuProfile.ss1 || !GuLogReady()) Stop();
#endif
    GuReleaseAssets();
    if (EFI_ERROR(MemoryRestore())) Stop();
    if (Gu.owned) {
      s=Gu.bs->CloseProtocol(Gu.handle,&PciGuid,Gu.image,NULL);
      if (EFI_ERROR(s)) Stop();
      Gu.owned=FALSE;
    }
    GuLogText("HANDOFF clean resources, original PCI attributes, existing Windows Boot Manager\n");
    if (!GuLogReady() || EFI_ERROR(GuIoClose())) Stop();
    Gu.bs->StartImage(windows,NULL,NULL);
    Stop(); /* Returning from Windows is not a safe retry path. */
  }
  GuReleaseAssets();
  if (windows) Gu.bs->UnloadImage(windows);
#endif
  if (EFI_ERROR(MemoryRestore())) Stop();
  if (Gu.owned) {
    EFI_STATUS closed=Gu.bs->CloseProtocol(Gu.handle,&PciGuid,Gu.image,NULL);
    if (EFI_ERROR(closed)) Stop();
    Gu.owned=FALSE;
  }
#endif
#ifdef M6501_AUTOMATIC
  return AutoNormalWindows(s);
#endif
  GuLog("EXIT status=%#llx GPU_MMIO_writes=%u\n",(unsigned long long)s,Gu.mmio_writes);
  EFI_STATUS closed=GuIoClose();
  return EFI_ERROR(s) ? s : closed;
}
#endif

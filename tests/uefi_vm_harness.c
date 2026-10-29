/* SPDX-License-Identifier: GPL-2.0-only
 * QEMU-only test harness. Never package for the laptop.
 * Port 0x402 records test output and 0x501 exits the emulated machine.
 */
#define MODE_HANDOFF
#define M6501_HOST_TEST
#include "../uefi/m6501.c"

static VOID VmOut(UINT16 port, UINT8 value) {
  __asm__ __volatile__("outb %0,%1" : : "a"(value), "Nd"(port));
}
static VOID VmText(const char *s) { while (*s) VmOut(0x402,(UINT8)*s++); }
static VOID VmStatus(const char *name, EFI_STATUS s) {
  static const char hex[]="0123456789abcdef";
  VmText(name); VmText("=0x");
  for (INTN i=60;i>=0;i-=4) VmOut(0x402,(UINT8)hex[(s>>i)&15]);
  VmText("\n");
}
static VOID VmExit(BOOLEAN pass) {
  VmText(pass ? "VM_TEST_PASS\n" : "VM_TEST_FAIL\n");
  VmOut(0x501,pass ? 0x10 : 0x11);
  for (;;) __asm__ __volatile__("hlt");
}

static EFI_STATUS VmRoot(EFI_FILE_PROTOCOL **root, EFI_HANDLE *device) {
  EFI_GUID loadedGuid=EFI_LOADED_IMAGE_PROTOCOL_GUID,fsGuid=EFI_SIMPLE_FILE_SYSTEM_PROTOCOL_GUID;
  EFI_LOADED_IMAGE_PROTOCOL *loaded=NULL;
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *fs=NULL;
  EFI_STATUS s=Gu.bs->HandleProtocol(Gu.image,&loadedGuid,(VOID **)&loaded);
  if (!EFI_ERROR(s)) s=Gu.bs->HandleProtocol(loaded->DeviceHandle,&fsGuid,(VOID **)&fs);
  if (!EFI_ERROR(s)) { *device=loaded->DeviceHandle; s=fs->OpenVolume(fs,root); }
  return s;
}

static EFI_STATUS VmLoad(EFI_HANDLE device, EFI_HANDLE *child) {
  EFI_DEVICE_PATH_PROTOCOL *path=NULL;
  EFI_STATUS s=Gu.bs->HandleProtocol(device,&PathGuid,(VOID **)&path);
  if (EFI_ERROR(s) || !path) return EFI_NOT_FOUND;
  UINTN prefix=0;
  for (UINTN j=0;j<64;j++) {
    EFI_DEVICE_PATH_PROTOCOL *n=(VOID *)((UINT8 *)path+prefix);
    UINTN length=n->Length[0]+((UINTN)n->Length[1]<<8);
    if (length<4 || length>4096-prefix) return EFI_COMPROMISED_DATA;
    if (n->Type==END_DEVICE_PATH_TYPE) break;
    prefix+=length;
    if (j==63) return EFI_UNSUPPORTED;
  }
  const CHAR16 name[]=L"\\PROBE.EFI";
  UINTN length=sizeof(FILEPATH_DEVICE_PATH)-2+sizeof(name);
  UINT8 *bytes=GuAlloc(prefix+length+4);
  if (!bytes) return EFI_OUT_OF_RESOURCES;
  memcpy(bytes,path,prefix);
  FILEPATH_DEVICE_PATH *file=(VOID *)(bytes+prefix);
  file->Header.Type=MEDIA_DEVICE_PATH; file->Header.SubType=MEDIA_FILEPATH_DP;
  file->Header.Length[0]=(UINT8)length;file->Header.Length[1]=(UINT8)(length>>8);
  memcpy(file->PathName,name,sizeof(name));
  EFI_DEVICE_PATH_PROTOCOL *end=(VOID *)(bytes+prefix+length);
  end->Type=END_DEVICE_PATH_TYPE;end->SubType=END_ENTIRE_DEVICE_PATH_SUBTYPE;end->Length[0]=4;
  s=Gu.bs->LoadImage(FALSE,Gu.image,(VOID *)bytes,NULL,0,child);
  GuFree(bytes); return s;
}

EFI_STATUS EFIAPI efi_main(EFI_HANDLE image, EFI_SYSTEM_TABLE *table) {
  St=table; GuInit(table->BootServices,NULL);Gu.image=image;
  VmText("VM_HARNESS_ENTERED\n");
  EFI_STATUS s=GuIoOpen(image,table);VmStatus("LOG_OPEN",s);
  if (EFI_ERROR(s)) VmExit(FALSE);
  UINT8 sb=0xff,setup=0xff;UINTN bytes=1;
  s=table->RuntimeServices->GetVariable(L"SecureBoot",&GlobalGuid,NULL,&bytes,&sb);
  VmStatus("SECURE_BOOT_READ",s);VmStatus("SECURE_BOOT",sb);
  bytes=1;
  s=table->RuntimeServices->GetVariable(L"SetupMode",&GlobalGuid,NULL,&bytes,&setup);
  VmStatus("SETUP_MODE",setup);
  EFI_FILE_PROTOCOL *root=NULL,*config=NULL; EFI_HANDLE device=NULL;
  s=VmRoot(&root,&device);
  if (!EFI_ERROR(s)) s=root->Open(root,&config,L"\\EXPECT.BIN",EFI_FILE_MODE_READ,0);
  UINT8 mode=0;bytes=1;
  if (!EFI_ERROR(s)) s=config->Read(config,&bytes,&mode);
  if (config) config->Close(config);
  if (root) root->Close(root);
  if (EFI_ERROR(s) || bytes!=1 || setup!=0 || (mode!='s' && sb!=1) || (mode=='s' && sb!=0)) VmExit(FALSE);
  s=Secure(); VmStatus("ADAPTER_SECURE_GUARD",s);
  if (mode!='s' && EFI_ERROR(s)) VmExit(FALSE);
  if (mode=='s' && s!=EFI_SECURITY_VIOLATION) VmExit(FALSE);
  EFI_HANDLE child=NULL;
  s=mode=='w' ? LoadWindows(&child) : VmLoad(device,&child);
  VmStatus("CHILD_LOAD",s);
  if (mode=='t' || mode=='d') VmExit(s==EFI_SECURITY_VIOLATION || s==EFI_ACCESS_DENIED);
  if (EFI_ERROR(s) || !child) VmExit(FALSE);
  if (mode=='w') VmText("REAL_WINDOWS_BOOT_MANAGER_START\n");
  s=Gu.bs->StartImage(child,NULL,NULL);
  VmStatus("CHILD_RETURN",s);
  if (mode=='w') VmExit(TRUE);
  VmExit(s==(mode=='s' ? EFI_SECURITY_VIOLATION : EFI_UNSUPPORTED));
  return EFI_ABORTED;
}
/* Keep one absolute relocation so the VM loader checks the relocation path. */
__attribute__((used)) VOID *VmRelocAnchor=(VOID *)&efi_main;

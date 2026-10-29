/* SPDX-License-Identifier: GPL-2.0-only
 * Countdown and fallback state tests, with simulated keyboard/timer only.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#undef NULL
#include "app_io.h"
#include "../uefi/automatic_boot.h"
#define GU_SSD_EXPERIMENT
#include "boot_source.h"
static unsigned checks,reads,stalls;
static int escape_at,unicode_escape,key_error_at,stall_error_at,other_at,log_ok;
static UINT64 elapsed;
static struct { HARDDRIVE_DEVICE_PATH hd; EFI_DEVICE_PATH_PROTOCOL end; } source_path;
static EFI_PARTITION_INFO_PROTOCOL source_partition;
static int partition_error;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); exit(1); } } while(0)
VOID GuLog(const char *format,...) { (void)format; }
VOID GuLogText(const char *text) { (void)text; }
BOOLEAN GuLogReady(VOID) { return log_ok; }
static EFI_STATUS EFIAPI Key(EFI_SIMPLE_TEXT_INPUT_PROTOCOL *input,EFI_INPUT_KEY *key) {
  (void)input; unsigned i=reads++; memset(key,0,sizeof(*key));
  if ((int)i==key_error_at) return EFI_DEVICE_ERROR;
  if ((int)i==escape_at) { if (unicode_escape) key->UnicodeChar=27; else key->ScanCode=0x17; return EFI_SUCCESS; }
  if ((int)i==other_at) { key->UnicodeChar='U'; return EFI_SUCCESS; }
  return EFI_NOT_READY;
}
static EFI_STATUS EFIAPI Stall(UINTN us) {
  CHECK(us==100000);
  if ((int)stalls++==stall_error_at) return EFI_DEVICE_ERROR;
  elapsed+=us; return EFI_SUCCESS;
}
static void Reset(void) {
  reads=stalls=0; elapsed=0; escape_at=key_error_at=stall_error_at=other_at=-1;
  unicode_escape=0; log_ok=1;
}
static EFI_STATUS EFIAPI SourceProtocol(EFI_HANDLE device,EFI_GUID *guid,VOID **out) {
  (void)device; EFI_GUID path_guid=EFI_DEVICE_PATH_PROTOCOL_GUID;
  if (!memcmp(guid,&path_guid,sizeof(*guid))) { *out=&source_path; return EFI_SUCCESS; }
  if (partition_error) return EFI_NOT_FOUND;
  *out=&source_partition; return EFI_SUCCESS;
}
int main(void) {
  EFI_BOOT_SERVICES bs={0}; EFI_SIMPLE_TEXT_INPUT_PROTOCOL input={0}; EFI_SYSTEM_TABLE table={0};
  bs.Stall=Stall; input.ReadKeyStroke=Key; table.BootServices=&bs; table.ConIn=&input;
  Reset(); CHECK(GuAutomaticCountdown(&table)==EFI_SUCCESS); CHECK(elapsed==5000000 && reads==51);
  Reset(); escape_at=0; CHECK(GuAutomaticCountdown(&table)==EFI_ABORTED && elapsed==0);
  Reset(); escape_at=25; unicode_escape=1; CHECK(GuAutomaticCountdown(&table)==EFI_ABORTED && elapsed==2500000);
  Reset(); escape_at=50; CHECK(GuAutomaticCountdown(&table)==EFI_ABORTED && elapsed==5000000);
  Reset(); other_at=0; CHECK(GuAutomaticCountdown(&table)==EFI_SUCCESS && elapsed==5000000);
  Reset(); key_error_at=12; CHECK(GuAutomaticCountdown(&table)==EFI_DEVICE_ERROR && elapsed==1200000);
  Reset(); stall_error_at=5; CHECK(GuAutomaticCountdown(&table)==EFI_DEVICE_ERROR && elapsed==500000);
  Reset(); log_ok=0; CHECK(GuAutomaticCountdown(&table)==EFI_DEVICE_ERROR && reads==0);
  Reset(); table.ConIn=NULL; CHECK(GuAutomaticCountdown(&table)==EFI_UNSUPPORTED); table.ConIn=&input;
  GU_PLATFORM p={0}; CHECK(GuAutomaticNormalAllowed(&p)); CHECK(!GuAutomaticNormalAllowed(NULL));
  p.armed=TRUE; CHECK(!GuAutomaticNormalAllowed(&p)); p.armed=FALSE;
  p.started=TRUE; p.quiesced=TRUE; CHECK(!GuAutomaticNormalAllowed(&p)); p.started=FALSE;
  p.mmio_writes=1; CHECK(!GuAutomaticNormalAllowed(&p)); p.mmio_writes=0;
  p.owned=TRUE; CHECK(!GuAutomaticNormalAllowed(&p)); p.owned=FALSE;
  p.allocations=(GU_DMA *)&p; CHECK(!GuAutomaticNormalAllowed(&p)); p.allocations=NULL;
  p.dma_count=1; CHECK(!GuAutomaticNormalAllowed(&p)); p.dma_count=0;
  p.retained=TRUE; CHECK(!GuAutomaticNormalAllowed(&p)); p.retained=FALSE;
  p.master_attributes_pending=TRUE; CHECK(!GuAutomaticNormalAllowed(&p));
  memset(&source_path,0,sizeof(source_path)); memset(&source_partition,0,sizeof(source_partition));
  source_path.hd.Header.Type=MEDIA_DEVICE_PATH; source_path.hd.Header.SubType=MEDIA_HARDDRIVE_DP;
  source_path.hd.Header.Length[0]=sizeof(HARDDRIVE_DEVICE_PATH);
  source_path.end.Type=END_DEVICE_PATH_TYPE; source_path.end.SubType=END_ENTIRE_DEVICE_PATH_SUBTYPE; source_path.end.Length[0]=4;
  source_partition.Revision=EFI_PARTITION_INFO_PROTOCOL_REVISION; source_partition.Type=PARTITION_TYPE_GPT;
  EFI_GUID esp=EFI_PART_TYPE_EFI_SYSTEM_PART_GUID; source_partition.Info.Gpt.PartitionTypeGUID=esp;
  bs.HandleProtocol=SourceProtocol;
  CHECK(GuBootSourceAllowed(&table,(EFI_HANDLE)1));
  source_partition.Info.Gpt.PartitionTypeGUID.Data1^=1; CHECK(!GuBootSourceAllowed(&table,(EFI_HANDLE)1));
  source_partition.Info.Gpt.PartitionTypeGUID=esp; partition_error=1; CHECK(!GuBootSourceAllowed(&table,(EFI_HANDLE)1));
  partition_error=0; source_path.end.Length[0]=0; CHECK(!GuBootSourceAllowed(&table,(EFI_HANDLE)1));
  printf("%u automatic countdown/fallback checks passed; no hardware services used.\n",checks);
  return 0;
}

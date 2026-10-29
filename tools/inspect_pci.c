/* SPDX-License-Identifier: GPL-2.0-only
 * Offline analysis only: reads 256 bytes from a regular file, no hardware API.
 */
#include "checks.h"
#include <stdio.h>
#include <string.h>

GU_RUNTIME_PROFILE GuProfile={.identity=0x252010deU,.subsystem=0x13131043U};

int main(int argc,char **argv) {
  if (argc!=2) return 2;
  FILE *file=fopen(argv[1],"rb");
  if (!file) return 2;
  UINT32 original[64],copy[64];
  size_t got=fread(original,1,sizeof(original),file);
  int extra=fgetc(file);fclose(file);
  if (got!=sizeof(original) || extra!=EOF) return 2;
  if (original[0]!=GuProfile.identity || original[11]!=GuProfile.subsystem || original[2]!=0x030000a1U) return 2;
  memcpy(copy,original,sizeof(copy));
  copy[1]|=2; /* Same CPU-owned MEM-bit simulation as BarAndBridges(). */
  GU_CAPS caps={0};
  BOOLEAN pass=!(original[1]&5U) && GuCheckConfig(copy,0,1,0,0,&caps);
  printf("{\"passed\":%s,\"original_command\":%u,\"memory_bit_added_to_cpu_copy_only\":true,"
         "\"pm_offset\":%u,\"pcie_offset\":%u,\"pcie_version\":%u,\"msi_offset\":%u,\"msix_offset\":%u,"
         "\"pci_or_mmio_hardware_accessed\":false}\n",pass ? "true":"false",(unsigned)(original[1]&0xffff),
         (unsigned)caps.pm,(unsigned)caps.pcie,(unsigned)caps.pcie_version,(unsigned)caps.msi,(unsigned)caps.msix);
  return pass ? 0:1;
}

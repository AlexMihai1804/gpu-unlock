/* SPDX-License-Identifier: GPL-2.0-only */
#include <stdio.h>
#include <stdlib.h>
#include "vbios_610.h"

int main(int argc,char **argv) {
  if (argc!=2) return 2;
  FILE *f=fopen(argv[1],"rb");
  if (!f) return 2;
  if (fseek(f,0,SEEK_END)) { fclose(f); return 2; }
  long size=ftell(f);
  if (size<=0 || size>1048576 || fseek(f,0,SEEK_SET)) { fclose(f); return 2; }
  unsigned char *rom=malloc((size_t)size);
  if (!rom) { fclose(f); return 2; }
  size_t n=fread(rom,1,(size_t)size,f); fclose(f);
  struct gpu_unlock_fwsec fw;
  int result=n==(size_t)size ? gpu_unlock_vbios_fwsec(rom,n,&fw) : -1;
  free(rom);
  if (result) { fprintf(stderr,"FWSEC parser rejected ROM: %d\n",result); return 1; }
  printf("{\"bytes\":%lu,\"image_off\":%u,\"image_size\":%u,\"imem_size\":%u,\"dmem_size\":%u,"
         "\"engine_mask\":%u,\"ucode_id\":%u,\"signature_count\":%u,\"signature_versions\":%u}\n",
         (unsigned long)n,fw.image_off,fw.image_size,fw.imem_size,fw.dmem_size,fw.engine_mask,
         fw.ucode_id,fw.sig_count,fw.sig_versions);
  return fw.engine_mask!=0x400 || fw.ucode_id!=9;
}

# Licențe și proveniență

Adaptorul local `uefi/`, instrumentele și testele derivate sunt GPL-2.0-only. Codul de tranzacție și transport este utilizat din checkout-ul fixat craftingmod/rtx30-unlock; originea sa este Zagitta/gpu-unlock și proiectele atribuite de upstream. Patchul local este generat în `build/generated/unlock_610_ss0.c`: păstrează SS1 și schimbă verificările aferente, fără rescrierea întregului nucleu.

Se păstrează `vendor/rtx30-unlock/LICENSE`, `THIRD_PARTY_NOTICES.md` și întregul director `LICENSES/`. Testul de tranzacție local este o adaptare a `src/unlock/tests/test_efi_transaction.c`, cu ROM sintetic, păstrarea SS1 și interzicerea scrierii lui. Testele PCI și SHA păstrează proveniența și condițiile upstream.

EDK2 MdePkg headers sunt BSD-2-Clause-Patent, la revizia indicată în notificările upstream; aplicațiile nu leagă biblioteci EDK2 precompilate. shim are licențele proprii din `vendor/shim/`; pachetele binare Debian se păstrează în cache, cu metadate și hashuri. Compilatorul LLVM/MinGW are propriile licențe în arhiva portabilă.

Firmware-ul NVIDIA și datele extrase rămân sub licența NVIDIA. `build/firmware/NVIDIA-LICENSE` și manifestul original trebuie păstrate. Pregătirea locală a fișierelor nu autorizează redistribuirea lor sub GPL. ROM-ul original al laptopului nu trebuie publicat ca și cum ar fi codul proiectului.

Reviziile și SHA-256 ale intrărilor sunt în `config/sources.lock.json` și în manifestul firmware-ului. Pachetele USB locale includ licențele corespunzătoare; niciun ROM sintetic de test nu este inclus în ele.

Laboratorul virtual folosește separat QEMU/OVMF din arhiva Windows fixată, virt-firmware și pyfatfs/fs, cu licențele furnizate în arhivă sau în metadatele pachetelor Python. Arhiva sursă locală nu redistribuie aceste dependențe, discuri VM sau copia loaderului Microsoft. QEMU este extras portabil; instalatorul nu este executat.

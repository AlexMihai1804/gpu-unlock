> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# B3: ultima repetare autorizată

**Etapă înlocuită de cererea utilizatorului pentru pornire automată internă, fără USB. B3 nu a fost executat; nu mai urma pașii de mai jos.** Vezi [varianta automată pregătită](AUTOMATIC-INTERNAL-PROPOSAL.md). Textul de mai jos păstrează istoricul acordului anterior.

B2 și controlul normal A3 au trecut. Acordul „aprob” din `results/repro-v3-authorization.json` permite B3 fără o confirmare suplimentară. Mai rămâne **o singură încercare fizică**, pe același executabil v3, urmată de controlul normal final A4. Nu este necesară o nouă înrolare MOK.

Stick: SanDisk Ultra, serial `USB_SERIAL_REQUIRES_LOCAL_REVIEW`, eticheta **M6501PROBE**, FAT32. Raportul pregătirii: `results/repro-v3-B3-preflight.json`.

- SHA-256 executabil: `f716f8827c38a63b353fd28ad505bb2e7713991fb152df6b34a250c89bd08336`.
- Hash MOK: `5dca60a7602255a01ff4f7771aacac62100afda4138f9235d0476f9b48f68642`.
- Următorul director de log așteptat: `RTX-UNLOCK/RUN08/`.

## Pașii de făcut acum

1. Salvează lucrul, conectează alimentatorul și lasă USB introdus. Păstrează profilul ASUS și monitoarele ca la măsurările precedente.
2. **Win+R** → `shutdown /s /t 0` → Enter. După oprire, ține **Esc** apăsat și pornește laptopul. Alege **UEFI: SanDisk** din meniul temporar.
3. La **Press U for this one attempt**, apasă **U o singură dată**, în 30 de secunde.
4. Așteaptă pornirea Windows. Lasă USB conectat și anunță revenirea la desktop. **Nu reporni și nu intra în sleep** înainte de analiza logului și benchmarkului B3 din acest boot. Nu trebuie fotografiat textul care dispare.

Dacă apare din nou Security Violation/MokManager, nu înrola alte fișiere și nu modifica Secure Boot sau cheile. Dacă revine în meniul de boot fără STOP/blocaj, alege Windows Boot Manager și anunță rezultatul; nu relansa USB.

Dacă apare **STOP** sau un ecran negru persistent fără progres, oprește complet laptopul; dacă nu răspunde, ține Power apăsat până se oprește. Scoate USB și pornește Windows normal. Nu repeta unlock în același ciclu de alimentare. Orice eșec oprește planul până la analiza dovezilor.

Tranzacția folosește firmware GPU în RAM, DMA, scrierea SS0 și un FLR. Succesele anterioare nu garantează această încercare; un blocaj poate necesita oprire completă. Nu sunt autorizate flash BIOS/VBIOS, chei noi, recompilarea candidatului sau reporniri automate. După B3 reușit și analizat urmează separat instrucțiunile de boot normal A4, fără încă o lansare USB.

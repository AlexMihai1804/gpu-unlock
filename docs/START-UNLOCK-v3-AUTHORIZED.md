> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Candidat v3 autorizat: o singură încercare

**Încercarea a fost executată și a trecut în RUN06. Nu relansa procedura.** Acordul pentru o încercare este consumat. Vezi [rezultatul și benchmarkul](UNLOCK-RESULT-v3.md), apoi [controlul de revenire la boot normal](NORMAL-RETURN-AFTER-UNLOCK.md). Pașii de mai jos rămân evidența procedurii aprobate.

Acordul utilizatorului: «aprob. spune-mi ce am de facut». Sunt autorizate copierea candidatului exact, înrolarea hashului său MOK și **o singură încercare fizică**. Nu sunt autorizate flash BIOS/VBIOS, înlocuirea cheilor platformei sau reporniri automate.

Stickul SanDisk Ultra **F:**, eticheta **M6501PROBE**, conține acum candidatul v3. Cele 20 de fișiere au fost recitite și verificate; ROM-ul și cele șase loguri au rămas identice. Backup CAPTURE: `results/unlock-deployment-20261025-211730/USB-CAPTURE-BACKUP/`. Raport: `results/unlock-deployment-20261025-211730/deployment.json`. Nu s-a executat încă unlock fizic.

- SHA-256 executabil: `f716f8827c38a63b353fd28ad505bb2e7713991fb152df6b34a250c89bd08336`.
- Hash PE/Authenticode pentru MOK: `5dca60a7602255a01ff4f7771aacac62100afda4138f9235d0476f9b48f68642`.

1. Salvează lucrul, conectează alimentatorul și lasă stickul introdus. Păstrează profilul ASUS și monitoarele ca la benchmarkul inițial.
2. Win+R → `shutdown /s /t 0` → Enter. După oprire, ține Esc apăsat și pornește laptopul; alege **UEFI: SanDisk** din meniul temporar.
3. Dacă apare `Verification failed (0x1A) Security Violation`, apasă Enter pe OK și eliberează tasta. La numărătoarea **Press any key to perform MOK management**, apasă imediat Space o dată.
4. Alege **Enroll hash from disk → M6501PROBE → EFI → BOOT → grubx64.efi**. Confirmă numai acest fișier/hash. Alege Continue și Yes la confirmarea înrolării, apoi Reboot. Nu selecta BOOTX64.EFI sau mmx64.efi și nu modifica Secure Boot/cheile BIOS.
5. La repornire, intră din nou cu Esc în meniul temporar și alege USB. Când aplicația cere **Press U for this one attempt**, apasă U o dată, în 30 de secunde. Esc sau expirarea celor 30 de secunde anulează înainte de activarea MEMORY. Înrolarea MOK deja făcută rămâne persistentă.
6. Așteaptă. La succes trebuie să pornească Windows automat. Lasă stickul conectat și anunță revenirea la desktop. **Nu reporni și nu intra în sleep înainte de verificarea logului și benchmark.** Nu este necesară fotografia textului care dispare repede.

**Dacă revine în boot menu, nu repeta încercarea.** Dacă nu apare STOP/blocaj, poți alege Windows Boot Manager și păstra stickul pentru analiză. Dacă apare STOP sau un ecran negru persistent fără progres, fă oprire fizică completă, scoate USB și încearcă pornirea normală Windows. Dacă nu răspunde, ține Power apăsat până se oprește complet. Nu relansa unlock în același ciclu de alimentare. Analizăm logul înaintea oricărei încercări noi.

Încercarea execută firmware GPU în RAM, DMA și un FLR; aceste operații nu sunt încă validate pe hardware-ul acestui laptop. Nu face flash de firmware. Explicațiile, criteriile de succes și limitele sunt în [UNLOCK-CANDIDATE-v3.md](UNLOCK-CANDIDATE-v3.md). Copierea pe USB și acceptarea MOK nu demonstrează accelerarea; sunt necesare logul tranzacției și benchmarkul din același boot Windows.

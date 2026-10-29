> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# B2: a doua măsurare cu unlock, autorizată

**B2 a fost executat și a trecut în RUN07. Nu relansa pașii USB de mai jos. Urmează controlul normal A3 din [rezultatul B2](UNLOCK-B2-RESULT-v3.md).** Procedura de mai jos rămâne evidența etapei autorizate.

Acordul „aprob” pentru planul B2 → A3 → B3 → A4 este consemnat în `results/repro-v3-authorization.json`. Sunt autorizate cel mult două încercări suplimentare, pe același executabil v3. Următoarea etapă este numai B2; B3 urmează după verificarea B2 și a controlului normal A3.

Stickul SanDisk Ultra, serial `USB_SERIAL_REQUIRES_LOCAL_REVIEW`, etichetă **M6501PROBE**, este pregătit. Cele 20 de fișiere au fost verificate, iar cele șapte loguri existente și ROM-ul au rămas identice. Raport: `results/repro-v3-B2-preflight.json`. Nu s-a executat o tranzacție B2 în timpul acestei verificări.

Executabilul este același ca la B1:

- SHA-256 fișier: `f716f8827c38a63b353fd28ad505bb2e7713991fb152df6b34a250c89bd08336`.
- Hash MOK: `5dca60a7602255a01ff4f7771aacac62100afda4138f9235d0476f9b48f68642`.

## Pașii de făcut acum

1. Salvează lucrul, conectează alimentatorul și lasă USB introdus. Păstrează profilul ASUS și monitoarele ca la măsurările precedente.
2. Apasă **Win+R**, introdu `shutdown /s /t 0` și apasă Enter. După oprire, ține **Esc** apăsat și pornește laptopul. Alege **UEFI: SanDisk** din meniul temporar.
3. Când apare **Press U for this one attempt**, apasă **U o singură dată**, în intervalul de 30 de secunde. Hashul este deja înrolat; nu este necesară o înrolare nouă.
4. Așteaptă pornirea Windows. Lasă USB conectat și anunță revenirea la desktop. **Nu reporni și nu intra în sleep înainte de analiza logului și benchmarkului din acest boot.** Nu trebuie fotografiat textul care dispare.

Dacă apare din nou `Security Violation` sau MokManager, nu înrola alte fișiere și nu modifica cheile ori Secure Boot. Revino la Windows pentru verificare. Dacă aplicația revine în meniul de boot fără STOP sau blocaj, alege Windows Boot Manager și păstrează USB pentru analiză; nu relansa USB.

Dacă apare **STOP** sau un ecran negru persistent fără progres, oprește complet laptopul; dacă nu răspunde, ține Power apăsat până se oprește. Scoate USB și pornește Windows normal. Nu repeta încercarea în același ciclu de alimentare. Orice eșec oprește avansarea planului până la analiza dovezilor.

## Ce verificăm după revenire

Directorul nou așteptat pentru log este `RTX-UNLOCK/RUN07/`. Arhivăm separat tentativa nouă și inventariem istoricul păstrat. Verificăm tranzacția, restaurarea resurselor, Secure Boot, cheile platformei, Windows Boot Manager, starea driverului și rezultatele numerice ale aceluiași benchmark GEMM. UAC poate apărea pentru colectarea stării UEFI, numai prin citire.

După B2 reușit urmează controlul normal A3. B3 și A4 rămân în acordul deja dat, dar nu sunt executate înaintea verificării etapelor precedente. Nu sunt autorizate reporniri automate, recompilarea candidatului, înrolări MOK noi, flash BIOS/VBIOS sau înlocuirea cheilor platformei.

Prima încercare a trecut, dar aceasta nu garantează următoarele încercări. Tranzacția folosește firmware GPU în RAM, DMA, scrierea SS0 și un FLR; un blocaj poate necesita oprire completă. Rezultatele măsurate sunt în [UNLOCK-RESULT-v3.md](UNLOCK-RESULT-v3.md) și [NORMAL-RETURN-RESULT-v3.md](NORMAL-RETURN-RESULT-v3.md).

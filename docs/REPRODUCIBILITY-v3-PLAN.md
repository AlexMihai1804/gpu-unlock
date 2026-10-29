> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Plan de repetabilitate v3 — două încercări suplimentare, neautorizate încă

Prima secvență A1 → B1 → A2 a trecut: FP16/BF16 au accelerat în B1 și au revenit la referință în A2. În prezent Windows este în boot normal. Acordul pentru încercarea B1 a fost consumat. Acest plan cere acord nou pentru **cel mult două tranzacții fizice**, B2 și B3; nu se aplică automat.

## Candidatul concret

Același executabil v3 de pe USB, fără recompilare:

- SHA-256 fișier: `f716f8827c38a63b353fd28ad505bb2e7713991fb152df6b34a250c89bd08336`.
- Hash MOK: `5dca60a7602255a01ff4f7771aacac62100afda4138f9235d0476f9b48f68642`.
- Chip, ROM, fuse și SS1: aceleași verificări din [propunerea v3](UNLOCK-CANDIDATE-v3.md).

Nu este planificată o cheie nouă sau o înrolare MOK suplimentară. Dacă imaginea este din nou refuzată, verificăm fișierele și logurile; nu resetăm chei și nu dezactivăm Secure Boot. Riscurile sunt cele ale primei tranzacții: firmware GPU în RAM, DMA, SS0-only și un FLR; poate apărea blocaj/STOP care cere oprire completă. Succesul B1 nu garantează succesul încercărilor următoare.

## Ordinea după acord

1. **B2:** oprire completă, USB din meniul temporar ASUS, o apăsare U. Windows trebuie să pornească în același boot. Arhivăm numai noua tentativă ca dovezi de încercare, inventariem separat istoricul, verificăm tranzacția și rulăm GEMM identic. Nu se repornește până la analiza rezultatului.
2. **A3:** oprire completă, USB scos după oprire, boot normal, reconectare la desktop. Verificăm logurile și benchmarkul de control.
3. **B3:** numai după B2/A3 reușite, aceeași procedură USB/U, o singură tranzacție și benchmark din același boot Windows.
4. **A4:** oprire completă și boot normal fără USB, cu verificarea finală a revenirii la referință.

Sunt necesare patru porniri manuale. Agentul nu închide forțat lucrul și nu repornește automat laptopul. Alimentarea, profilul ASUS, monitoarele, driverul și bibliotecile trebuie păstrate comparabile; fiecare tentativă și fiecare benchmark primesc fișiere noi.

Orice STOP, eroare de curățare, problemă de driver sau verificare numerică eșuată oprește planul înaintea altui unlock. O tentativă eșuată nu se repetă în același ciclu de alimentare și consumă o încercare dacă tranzacția a început. Logurile rămân păstrate; nu se aplică o corecție de cod pe hardware fără revizie și acord pentru un executabil diferit.

## Rezultatul urmărit

După B2/B3 reușite avem trei booturi experimentale măsurate și controale normale între ele. Cerem tranzacții curate, Secure Boot activ, corectitudine numerică, câștig FP16/BF16 repetat și controale FP32/TF32 aproximativ stabile. Telemetria și starea driverului sunt incluse în evaluare. Aceasta extinde dovada de repetabilitate; aplicațiile reale, idle/sleep/resume și stabilitatea de durată rămân etape separate.

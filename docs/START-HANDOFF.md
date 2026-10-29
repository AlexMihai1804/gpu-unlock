> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# HANDOFF — test autorizat, fără unlock

Această procedură HANDOFF a fost executată cu succes și rămâne ca referință. **Stickul conține acum CAPTURE**, autorizat ulterior; pentru următorul boot folosește [START-CAPTURE.md](START-CAPTURE.md). Eticheta SanDiskului F: rămâne M6501PROBE. Unlock rămâne neautorizat.

Ce schimbăm și ce risc există

Pe USB a fost înlocuită aplicația și au fost actualizate fișierele descriptive. Nu s-a reformatat stickul; cele patru loguri PROBE sunt păstrate și copiate separat în folderul raportului de deployment. Fișierele shim/MokManager au rămas identice. A doua modificare intenționată este înscrierea noului hash în MOK, persistentă până la eliminarea exactă a acelei intrări.

HANDOFF verifică Secure Boot, modelul, identitatea GPU și GOP-ul AMD, apoi încarcă și pornește Windows Boot Manager existent de pe partiția cu GUID-ul reverificat. Nu modifică GPU-ul, nu încarcă firmware GPU și nu execută FLR. Nu scrie pe ESP Windows sau în BCD. Driverul este încărcat normal de Windows. Shim poate actualiza propriile variabile de stare/SBAT și măsurătorile de boot; aceasta face parte din ruta aprobată.

Intervenția este mai mică decât în etapa de unlock, dar nu se garantează risc zero: ruta poate fi refuzată, poate reveni la firmware sau poate rămâne la un ecran de eroare. Compatibilitatea completă cu pornirea Windows pe ASUS este chiar obiectul acestui test. În caz de eșec se păstrează fotografia/logul și se revine la Windows Boot Manager normal, fără USB. Nu se modifică Secure Boot sau cheile platformei pentru a forța trecerea testului.

Pașii manuali

1. Salvează lucrul, lasă alimentatorul și stickul conectate și închide Windows normal.
2. Cu laptopul oprit ține Esc, apasă Power și păstrează Esc până apare meniul. Alege intrarea UEFI SanDisk.
3. Pentru noua aplicație neînrolată este de așteptat refuzul inițial. La «Security Violation» apasă Enter pe OK, eliberează Enter, iar la «Press any key to perform MOK management» apasă o singură dată **Space**, înainte să expire secundele.
4. Alege «Enroll hash from disk» → **M6501PROBE** → `EFI` → `BOOT` → **`grubx64.efi`**. Autorizezi noul HANDOFF; hashul PROBE deja înscris nu se șterge. Dacă ecranul, volumul sau fișierul nu corespund, trimite fotografie înainte de altă selecție.
5. Hashul PE/Authenticode SHA-256, dacă este afișat, trebuie să fie cel de mai jos. Confirmă înrolarea exactă deja autorizată, apoi alege Reboot dacă este oferit.
6. Selectează din nou același USB prin Esc. HANDOFF ar trebui să pornească Windows automat. Dacă apare o eroare, fotografiaz-o; nu este nevoie să prinzi textul care apare foarte scurt la verificări.
7. După revenirea în Windows păstrează stickul conectat și scrie «am revenit în Windows». Agentul verifică noul log RUNxx pentru `WINDOWS_PRELOAD status=0 unique_GUID_match=1` și `HANDOFF-ONLY status=0 no_GPU_writes=1 no_firmware_load=1`, apoi starea Secure Boot/MOK și rezultatul din Windows. Un log de preîncărcare singur nu demonstrează că Windows a terminat pornirea.

Hashul **PE/Authenticode pentru MOK**:

```text
578950703436fdda4130666bf45f168e419d5d9932babdc81ac67281bbe24c5f
```

SHA-256 al fișierului întreg, pentru verificarea copierii, este diferit:

```text
c646f027c42795505b6f3b618e3f5586920054fe2c94b57ac288f1aab238c83b
```

Raportul pregătirii este în `results/handoff-deployment-20261025-191611/deployment.json`. Scriptul folosit este `scripts/Deploy-AuthorizedHandoff.ps1`; verifică exact discul/serialul/partiția USB și GUID-ul ESP Windows înainte de copiere. Nu execută formatare sau înrolare MOK. Nu se reexecută automat după schimbarea stadiului stickului.

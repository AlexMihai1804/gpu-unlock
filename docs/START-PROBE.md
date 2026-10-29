> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Primul test pe ASUS — PROBE

Utilizatorul a aprobat pornirea USB și, dacă este necesar, înrolarea hashului exact al PROBE în MOK. Acordul nu include HANDOFF, CAPTURE sau UNLOCK. Stick verificat: SanDisk Ultra, etichetă M6501PROBE, FAT32. Windows îl vede ca F:; în preboot litera F: poate să nu existe.

Prima acțiune manuală

1. Salvează documentele deschise. Lasă alimentatorul și stickul conectate. Ține instrucțiunile la îndemână pe telefon sau pe hârtie.
2. Din Windows alege Start → Alimentare → Închidere. Așteaptă oprirea.
3. Cu laptopul oprit, ține apăsat **Esc**, apasă o dată butonul Power și păstrează Esc apăsat până apare meniul de boot. Aceasta este metoda ASUS pentru meniul temporar: [instrucțiuni ASUS](https://www.asus.com/support/faq/1013017/).
4. Alege intrarea USB care conține **SanDisk**, de preferat cu **UEFI** sau **Partition 1**, și apasă Enter. Denumirea exactă poate varia. Dacă există mai multe intrări ambigue sau stickul lipsește, fotografiază meniul înainte de alte acțiuni.
5. Fotografiază primul ecran afișat după alegerea stickului și trimite fotografia în conversație. Poate fi refuzul inițial al aplicației neînrolate, MokManager sau o eroare de firmware. Fotografia permite identificarea exactă a pasului următor; nu cere o aprobare nouă pentru PROBE deja autorizat.

Secure Boot rămâne activ. Nu se folosesc opțiunile Clear/Delete/Reset keys, Reset MOK sau Change Secure Boot state pentru acest test. Acordul este pentru adăugarea hashului unui singur executabil.

Repere pentru înrolare, după identificarea ecranului

Mesajul shim «Verification failed: (0x1A) Security Violation» poate apărea deoarece PROBE nu este încă autorizat. Nu dovedește că firmware-ul a refuzat shim; o fotografie diferențiază cele două cazuri. După confirmarea mesajului, MokManager poate afișa un countdown: se apasă o tastă pentru meniu. Denumirile observate în sursa versiunii pregătite sunt «Perform MOK management» și «Enroll hash from disk».

În «Enroll hash from disk» se selectează **stickul USB**, apoi `EFI` → `BOOT` → **`grubx64.efi`**. Acesta este PROBE, nu GRUB. Nu se alege partiția internă Windows și nu se înscrie BOOTX64.EFI sau mmx64.efi. Navigarea se face cu săgeți și Enter. Dacă identitatea volumului, fișierul sau dialogul sunt neclare, se trimite fotografie înainte de confirmare.

Hashul PE/Authenticode SHA-256 pentru MOK, dacă este afișat, trebuie să fie:

```text
7ea0fcecbecd80da16abca6258aee855b48c4c954602bb810d56b71e0cf498ea
```

SHA-256 al fișierului întreg, folosit pentru verificarea copierii, este diferit:

```text
8f099671f487eca54c7584d913ba29b133f40cc6d86cb1c7e325344d2f509070
```

După înrolarea hashului exact se folosește Reboot dacă este oferit, apoi se alege din nou același USB prin Esc. Dacă apar opțiuni sau hashuri diferite, se analizează fotografia; nu se schimbă alte politici pentru a continua.

După execuția PROBE

PROBE scrie logul pe USB în `RTX-UNLOCK/RUNxx/UNLOCK.TXT` și se încheie. **Nu pornește singur Windows**; aceasta este funcția variantei HANDOFF, care nu se află pe acest stick. Ieșirea poate reveni la firmware sau poate fi prezentată de shim ca eroare de încărcare dacă aplicația a refuzat o verificare. Logul și fotografia stabilesc rezultatul; un mesaj de eroare nu trebuie interpretat automat drept defect Windows.

Pentru revenire se alege Windows Boot Manager din meniul de boot. Dacă a rămas un ecran UEFI fără opțiune de ieșire, se fotografiază; se poate opri laptopul, apoi porni fără USB. Nu se întrerupe alimentarea în timpul confirmării unei înrolări MOK. La revenirea în Windows se păstrează/reconectează stickul și se scrie în conversație «am revenit». Agentul citește și analizează logurile, fără a presupune că testul a reușit.

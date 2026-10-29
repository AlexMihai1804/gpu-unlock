> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# CAPTURE autorizat — pașii manuali

**Etapă executată cu succes în RUN05. Nu o repeta acum.** ROM-ul complet și restaurarea PCI sunt confirmate; vezi [CAPTURE-RESULT.md](CAPTURE-RESULT.md). Pașii de mai jos rămân ca referință. Nu autorizează UNLOCK.

Au fost aprobate copierea CAPTURE pe USB, înrolarea hashului său exact în MOK și activarea temporară PCI MEMORY pentru citirea ROM-ului/registrelor. Nu a fost aprobat unlock. Aplicația a fost copiată fără reformatare; cinci loguri PROBE/HANDOFF și o copie a imaginii HANDOFF sunt păstrate în `results/capture-deployment-20261025-195944/USB-HANDOFF-BACKUP/`. Toate cele 13 fișiere ale pachetului au fost recitite și verificate.

Stick: **SanDisk Ultra**, eticheta **M6501PROBE**, F: în Windows. Aplicația `EFI/BOOT/grubx64.efi` este acum CAPTURE.

1. Salvează lucrul, lasă alimentatorul și stickul conectate. Pentru oprire completă apasă Win+R, introdu `shutdown /s /t 0`, apoi Enter. Agentul nu execută automat oprirea.
2. Cu laptopul oprit, ține Esc, apasă Power și păstrează Esc până apare meniul. Alege UEFI SanDisk.
3. Înrolează noul hash ca în etapele anterioare: Enter pe OK la refuzul inițial, eliberează tasta, apoi **Space o singură dată** la numărătoarea «Press any key to perform MOK management». Alege «Enroll hash from disk» → **M6501PROBE** → **EFI** → **BOOT** → **grubx64.efi**. Confirmă numai fișierul exact CAPTURE. Secure Boot rămâne activ; intrările MOK existente se păstrează.
4. După înrolare alege Reboot dacă este oferit, apoi selectează din nou același USB prin Esc.
5. Dacă apare **«Press P for this one attempt»**, apasă o singură dată **P** în cele 30 de secunde. Aceasta permite o singură încercare de captură. Esc/timeout anulează. Dacă aplicația revine direct în meniul de boot fără această solicitare, nu repeta încercarea pentru fotografie: un control preliminar poate să fi refuzat continuarea, iar logul explică motivul.
6. Așteaptă terminarea. La revenirea în meniul de boot, alege Windows Boot Manager. CAPTURE nu pornește singur Windows. Lasă stickul conectat și spune în conversație că ai revenit, chiar dacă textul a dispărut prea repede pentru fotografie.

**Dacă apare mesajul STOP**, fotografiază-l și fă oprire completă; nu relansa CAPTURE în același ciclu de alimentare. Mesajul poate indica o restaurare PCI neconfirmată. Dacă după înrolarea corectă reapare MokManager, nu reseta MOK sau Secure Boot: revino în Windows pentru analiza logului.

Hash PE/Authenticode SHA-256 pentru MOK:

```text
7d073c9d54198ff2c18e9d27ad5531ce91bd0232a4c720f08351959356753f4a
```

SHA-256 al fișierului întreg:

```text
2fc636dbc15b351a9e3139e4811a01e953b0d8bf99176e606774bdc248486022
```

Ce se verifică după revenire

Agentul copiază logurile noi și eventualul `RTX-UNLOCK/PROMxx.ROM` în workspace, verifică dimensiunea exactă de 1.048.576 bytes și SHA-256, apoi analizează COLD, LAYOUT_REG, BOOTER_FUSE, FWSEC/FWSEC_FUSE și **MEM_RESTORE confirmed=1**. Lipsa ROM-ului sau un status de eroare se investighează; nu se trece automat la unlock. Profilul de unlock rămâne blocat până la revizuirea dovezilor și acord distinct.

Scriptul de deployment este `scripts/Deploy-AuthorizedCapture.ps1`; scrie numai fișiere pe USB și rapoarte locale, nu execută boot, înrolare sau acces PCI/MMIO. Detaliile intervenției și limitele sunt în [CAPTURE-PLAN.md](CAPTURE-PLAN.md).

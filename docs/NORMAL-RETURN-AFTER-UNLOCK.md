> Arhivă a laboratorului original. Datele, aprobările și stările de boot descrise aici sunt istorice. Unele fișiere brute menționate sunt păstrate doar local. Pentru utilizarea copiei publice, începe cu [ghidul actual](INSTALL.md).

# Control după unlock: boot normal fără USB

**Control executat și trecut în A2. Nu repeta acum acești pași.** FP16/BF16 au revenit la referință, iar Secure Boot/trustul/Windows Boot Manager au trecut verificările. Vezi [NORMAL-RETURN-RESULT-v3.md](NORMAL-RETURN-RESULT-v3.md). Procedura de mai jos rămâne ca referință.

Primul unlock v3 și benchmarkul au trecut. Această etapă verifică pornirea normală și performanța după oprire completă, fără să reexecute tranzacția GPU. Nu cere schimbări BIOS, chei sau drivere. Nu se repornește automat și nu se închid forțat aplicațiile.

1. Salvează lucrul și păstrează alimentatorul conectat, același profil ASUS și aceleași monitoare.
2. Win+R → `shutdown /s /t 0` → Enter.
3. **După oprirea completă**, scoate USB-ul. Pornește laptopul normal, fără Esc și fără USB.
4. Ajuns la desktop, reconectează USB-ul și anunță în conversație că Windows a pornit fără el. Nu relansa aplicația UEFI.

După revenire, agentul arhivează logurile păstrate, verifică faptul că nu a apărut o nouă tentativă, colectează starea bootului/driverului/Secure Boot și rulează același benchmark cu un nume nou. Se compară cu referința și cu B1. Nu se deduce automat starea selectorilor doar din faptul că USB-ul a fost scos; performanța de după oprire trebuie măsurată.

Acest control nu elimină hashurile MOK înrolate. Nu se resetează întreaga MokList sau bazele PK/KEK/db/dbx. O nouă încercare de unlock necesită acord distinct, deoarece acordul inițial a acoperit una singură, deja executată.

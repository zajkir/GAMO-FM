# GAMO FM Desktop v9 — Installer + Online Updater

## Čo je nové
- normálna Windows desktop aplikácia (pywebview), nie Chrome
- Windows installer cez Inno Setup
- automatická kontrola novej verzie pri štarte
- aktualizácia sa sťahuje iba cez HTTPS
- pred spustením sa kontroluje SHA-256 súboru
- výpadok update servera nikdy nezablokuje štart GAMO FM
- databáza používateľa zostáva v `%LOCALAPPDATA%\GAMO_FM\data`

## Vytvorenie Setup.exe na Windows
Dvojklik na `build_release_windows.bat`.
Výsledok: `dist_installer\GAMO_FM_Setup_9.0.0.exe`.

## Online aktualizácie
Updater používa `update.json` z vetvy `main`. Pri vydaní tagu `vX.Y.Z` GitHub Actions zostaví Windows installer, vytvorí GitHub Release, vypočíta SHA-256 a aktualizuje manifest.

## GitHub build
Workflow je v `.github/workflows/build-windows.yml`.

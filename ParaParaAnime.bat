@echo off & cd /d "%~dp0" & if not exist ".venv\Scripts\pythonw.exe" (echo ERROR: .venv\Scripts\pythonw.exe was not found. & pause) else (start "" ".venv\Scripts\pythonw.exe" "parapara_anime.py")

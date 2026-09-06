@echo off
setlocal
set "PYTHONPATH=%~dp0"
"%~dp0.venv\Scripts\python.exe" -X utf8 -m sessionchat.client %*

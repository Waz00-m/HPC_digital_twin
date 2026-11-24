@echo off
cd /d "%~dp0"
if not exist node_modules\mqtt (
  echo Run npm.cmd ci in this folder first.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:4318 in your browser after the server starts.
node server.mjs
pause

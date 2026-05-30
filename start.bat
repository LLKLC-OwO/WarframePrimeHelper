@echo off
cd /d "%~dp0"
py -3 -m pip install customtkinter Pillow keyboard rapidocr-onnxruntime requests --quiet
py -3 -m pip install pygame --only-binary=:all: --quiet 2>nul
py -3 wf9_vertical_optimized.py
pause

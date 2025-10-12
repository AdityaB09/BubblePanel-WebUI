@echo off
set BP_PYTHON=python
set BP_SCRIPT=smoke_test.py
set BP_REPO_ROOT=C:\Users\adity\Downloads\BubblePanel-main
uvicorn main:app --host 127.0.0.1 --port 8080 --reload
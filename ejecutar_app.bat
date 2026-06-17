@echo off
cd /d %~dp0
IF NOT EXIST .venv (
    python -m venv .venv
)
call .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
pause

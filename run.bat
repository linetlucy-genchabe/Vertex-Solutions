@echo off
REM Double-click to run the Vertex Solutions store locally
cd /d "%~dp0"
if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate
pip install -q -r requirements.txt
python manage.py migrate
set OWNER_EMAIL=owner@vertex.co.ke
set OWNER_PASSWORD=demo12345
python manage.py setup_shop --demo
echo.
echo Shop:      http://127.0.0.1:8000
echo Dashboard: http://127.0.0.1:8000/dashboard/  (owner@vertex.co.ke / demo12345)
echo.
start "" http://127.0.0.1:8000
python manage.py runserver

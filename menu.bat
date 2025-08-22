@echo off
cd /d C:\Users\YourName\Projects\my_django_project
echo 1. Start venv
echo 2. Run Server
echo 3. Make Migrations and Migrate
echo 4. Open Admin
echo 5. Compile Packages
echo 6. Stop venv

set /p choice="Choose option: "
if "%choice%"=="1" venv\scripts\activate
if "%choice%"=="2" python manage.py runserver
if "%choice%"=="3" (
    python manage.py makemigrations
    python manage.py migrate
)
if "%choice%"=="4" start http://127.0.0.1:8000/admin
if "%choice%"=="5" pip freeze > requirements.txt
if "%choice%"=="6" venv\scripts\deactivate



@echo off
cd /d %USERPROFILE%\Documents\GitHub\MOEN-IMS

call env\Scripts\activate

cd IMS\Inventory_management_system

python manage.py runserver

cmd /k

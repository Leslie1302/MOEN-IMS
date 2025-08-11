@echo off
cd C:\Users\Leslie\Documents\GitHub\MOEN-IMS

call env\Scripts\activate

cd IMS\Inventory_management_system

python manage.py runserver

cmd /k

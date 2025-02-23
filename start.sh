#!/bin/bash
cd IMS/Inventory_management_system
gunicorn Inventory_management_system.wsgi

# Inventory_management_system/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('Inventory.urls')),  # Includes your Inventory/urls.py
]

# Serve media files during development
if settings.DEBUG:
    # This will serve static files from STATIC_URL
    urlpatterns += staticfiles_urlpatterns()
    # This will serve media files from MEDIA_URL
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # In production, these should be served by the web server (e.g., Nginx, Apache)
    pass
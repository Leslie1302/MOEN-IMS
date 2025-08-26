# Inventory_management_system/urls.py
import os
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import HttpResponse
from django.urls import path, include

def dcv_fileauth_view(request):
    """
    Serve DigiCert DCV file content for domain validation at
    /.well-known/pki-validation/fileauth.txt

    Set the content via env var DCV_FILEAUTH_CONTENT to avoid committing secrets.
    """
    content = os.getenv('DCV_FILEAUTH_CONTENT', '').strip()
    if not content:
        return HttpResponse('DCV content not configured', status=404, content_type='text/plain')
    return HttpResponse(content + "\n", content_type='text/plain')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('.well-known/pki-validation/fileauth.txt', dcv_fileauth_view),
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
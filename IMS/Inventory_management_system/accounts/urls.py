from django.urls import path
from . import views

urlpatterns = [
    path("login/",    views.ms_login,    name="ms_login"),
    path("callback/", views.ms_callback, name="ms_callback"),
    path("logout/",   views.ms_logout,   name="ms_logout"),
]

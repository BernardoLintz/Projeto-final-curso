from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from app import views  

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('app.urls')), 
    path("__reload__/", include("django_browser_reload.urls")),
    
    # Rotas de Autenticação
    path('login/', auth_views.LoginView.as_view(template_name='app/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # Agora o 'views.cadastro' vai funcionar porque aponta para app/views.py
    path('cadastro/', views.cadastro, name='cadastro'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
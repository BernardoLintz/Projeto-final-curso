from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Home e Busca
    path('', views.lista_eventos, name='lista_eventos'),
    
    # Autenticação
    path('login/', auth_views.LoginView.as_view(template_name='app/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='lista_eventos'), name='logout'),
    path('cadastro/', views.cadastro, name='cadastro'),
    
    # Eventos e Produção
    path('criar-evento/', views.criar_evento, name='criar_evento'),
    path('meus-eventos/', views.meus_eventos, name='meus_eventos'),
    path('evento/<int:evento_id>/', views.detalhe_evento, name='detalhe_evento'),
    path('meus-ingressos/', views.meus_ingressos, name='meus_ingressos'),
    
    # Pagamento e Carrinho
    path('evento/<int:evento_id>/inscrever/', views.realizar_inscricao, name='realizar_inscricao'),
    path('sucesso_pagamento/<int:evento_id>/', views.sucesso_pagamento, name='sucesso_pagamento'),
    path('sucesso/<int:inscricao_id>/', views.pagina_sucesso, name='pagina_sucesso'),
    path('carrinho/adicionar/<int:evento_id>/', views.adicionar_ao_carrinho, name='adicionar_ao_carrinho'),
    path('carrinho/', views.ver_carrinho, name='ver_carrinho'),
    path('carrinho/checkout/', views.checkout_carrinho, name='checkout_carrinho'),
    path('sucesso_carrinho/', views.sucesso_carrinho, name='sucesso_carrinho'),

    # BI / Dashboard
    path('dashboard-bi/', views.dashboard_bi, name='dashboard_bi'),
]
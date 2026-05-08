from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_eventos, name='lista_eventos'),
    path('evento/<int:evento_id>/', views.detalhe_evento, name='detalhe_evento'),
    path('evento/<int:evento_id>/inscrever/', views.realizar_inscricao, name='realizar_inscricao'),
    path('sucesso/<int:inscricao_id>/', views.pagina_sucesso, name='pagina_sucesso'),
    path('meus-ingressos/', views.meus_ingressos, name='meus_ingressos'),
    path('meus-ingressos/', views.meus_ingressos, name='meus_ingressos'), 
    path('sucesso_pagamento/<int:evento_id>/', views.sucesso_pagamento, name='sucesso_pagamento'),
    path('carrinho/adicionar/<int:evento_id>/', views.adicionar_ao_carrinho, name='adicionar_ao_carrinho'),
    path('carrinho/', views.ver_carrinho, name='ver_carrinho'),
    path('carrinho/checkout/', views.checkout_carrinho, name='checkout_carrinho'),
    path('dashboard-bi/', views.dashboard_bi, name='dashboard_bi'),
     
]


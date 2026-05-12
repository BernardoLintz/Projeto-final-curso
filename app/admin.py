from django.contrib import admin
# Adicionado TicketType no import abaixo:
from .models import (
    Empresa, Espaco, Categoria, Evento, 
    EventoData, Inscricao, Perfil, TicketType
)

class TicketTypeInline(admin.TabularInline):
    model = TicketType
    extra = 1

class EventoDataInline(admin.TabularInline):
    model = EventoData
    extra = 1

@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'empresa', 'tipo', 'vagas_restantes', 'ativo')
    list_filter = ('tipo', 'categoria', 'empresa', 'ativo')
    search_fields = ('nome', 'descricao')
    # Agora você cria Ingressos E Datas na mesma tela do Evento!
    inlines = [TicketTypeInline, EventoDataInline] 

admin.site.register(Empresa)
admin.site.register(Espaco)
admin.site.register(Categoria)
admin.site.register(Inscricao)
admin.site.register(Perfil)
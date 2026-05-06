from django.contrib import admin
from .models import Empresa, Espaco, Categoria, Evento, EventoData, Inscricao, Perfil

@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'empresa', 'tipo', 'valor_ingresso', 'vagas_exibicao')
    list_filter = ('tipo', 'categoria', 'empresa')
    search_fields = ('nome', 'descricao')

    def vagas_exibicao(self, obj):
        return obj.vagas_restantes
    vagas_exibicao.short_description = "Vagas Restantes"

admin.site.register(Empresa)
admin.site.register(Espaco)
admin.site.register(Categoria)
admin.site.register(Inscricao)
admin.site.register(Perfil)
from django.db import models
from django.contrib.auth.models import User

class Empresa(models.Model):
    nome = models.CharField(max_length=100)
    cnpj = models.CharField(max_length=18, unique=True)
    site = models.URLField(blank=True)

    def __str__(self):
        return self.nome

class Espaco(models.Model):
    nome = models.CharField(max_length=100)
    endereco = models.CharField(max_length=255)
    lotacao_maxima = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.nome} ({self.lotacao_maxima} pessoas)"

class Categoria(models.Model):
    nome = models.CharField(max_length=50)

    def __str__(self):
        return self.nome

class Evento(models.Model):
    # Relacionamentos (Chaves Estrangeiras)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    espaco = models.ForeignKey(Espaco, on_delete=models.SET_NULL, null=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    
    # Dados do Evento
    nome = models.CharField(max_length=200)
    descricao = models.TextField()
    valor_ingresso = models.DecimalField(max_digits=10, decimal_places=2)
    vagas_disponiveis = models.PositiveIntegerField()
    imagem = models.ImageField(upload_to='eventos/', blank=True, null=True) # Para Aula 20
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return self.nome
    
class EventoData(models.Model):
    # Relacionamento: Um evento pode ter várias datas (1:N)
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name='datas')
    data_inicio = models.DateTimeField()
    data_fim = models.DateTimeField(null=True, blank=True)

class Meta:
    verbose_name = "Data do Evento"
    verbose_name_plural = "Datas do Evento"
    ordering = ['data_inicio']

    def __str__(self):
        return f"{self.evento.nome} em {self.data_inicio.strftime('%d/%m/%Y %H:%M')}"

class Inscricao(models.Model):
    # Relaciona o Usuário Logado ao Evento (Segurança e Lógica)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE)
    data_inscricao = models.DateTimeField(auto_now_add=True)
    codigo_confirmacao = models.CharField(max_length=20, unique=True)

    class Meta:
        verbose_name_plural = "Inscrições"

    def __str__(self):
        return f"{self.usuario.username} - {self.evento.nome}"
<<<<<<< HEAD
from django.db import models
from django.contrib.auth.models import User
import uuid

# 1. Primeiro as Tabelas de Apoio (Para o Evento poder usá-las)
class Empresa(models.Model):
    nome = models.CharField(max_length=100)
    cnpj = models.CharField(max_length=18, unique=True)
    site = models.URLField(blank=True)
    colaboradores = models.ManyToManyField(User, related_name='empresas_gerenciadas')

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

# 2. O Evento e seus Lotes
class Evento(models.Model):
    TIPO_CHOICES = (
        ('PAGO', 'Pago'),
        ('GRATUITO', 'Gratuito'),
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='eventos')
    espaco = models.ForeignKey(Espaco, on_delete=models.SET_NULL, null=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    nome = models.CharField(max_length=200)
    descricao = models.TextField()
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='GRATUITO')
    imagem = models.ImageField(upload_to='eventos/', blank=True, null=True)
    ativo = models.BooleanField(default=True)

    @property
    def vagas_restantes(self):
        if not self.espaco:
            return 0
        inscritos = self.inscricoes.filter(status='CONFIRMADO').count()
        return self.espaco.lotacao_maxima - inscritos

    def __str__(self):
        return self.nome

class TicketType(models.Model):
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name='tipos_ingressos')
    nome = models.CharField(max_length=100)
    preco = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    quantidade_total = models.PositiveIntegerField(help_text="Total de ingressos deste lote")
    quantidade_vendida = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nome} - {self.evento.nome} (R$ {self.preco})"

    @property
    def disponivel(self):
        return self.ativo and self.quantidade_vendida < self.quantidade_total

# 3. Transações e BI
class Inscricao(models.Model):
    STATUS_CHOICES = (
        ('PENDENTE', 'Pendente'),
        ('CONFIRMADO', 'Confirmado'),
        ('CANCELADO', 'Cancelado'),
    )
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='minhas_inscricoes')
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name='inscricoes')
    ticket_type = models.ForeignKey(TicketType, on_delete=models.PROTECT, related_name='vendas', null=True)
    data_inscricao = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDENTE')
    stripe_checkout_id = models.CharField(max_length=255, blank=True, null=True)
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)
    codigo_ticket = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    checkin_realizado = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Inscrições"

    def __str__(self):
        lote = self.ticket_type.nome if self.ticket_type else 'N/A'
        return f"{self.usuario.username} - {self.evento.nome} [{lote}]"

class LogCarrinho(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE)
    data_adicao = models.DateTimeField(auto_now_add=True)
    finalizado = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Logs de Carrinhos"

class Perfil(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    telefone = models.CharField(max_length=20, blank=True)
    cpf = models.CharField(max_length=14, unique=True, blank=True, null=True)

class EventoData(models.Model):
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name='datas')
    data_inicio = models.DateTimeField()
    data_fim = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Data do Evento"
        verbose_name_plural = "Datas do Evento"
        ordering = ['data_inicio']
=======
from django.db import models
from django.contrib.auth.models import User
import uuid

class LogCarrinho(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    evento = models.ForeignKey('Evento', on_delete=models.CASCADE)
    data_adicao = models.DateTimeField(auto_now_add=True)
    finalizado = models.BooleanField(default=False) # Vira True após o pagamento

    def __str__(self):
        status = "Finalizado" if self.finalizado else "Abandonado"
        return f"{self.usuario.username} - {self.evento.nome} ({status})"

    class Meta:
        verbose_name = "Log de Carrinho"
        verbose_name_plural = "Logs de Carrinhos"

# --- BI PREPARAÇÃO: Modelo de Perfil ---
class Perfil(models.Model):
    """Permite coletar dados para o BI sem alterar o User padrão do Django"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    telefone = models.CharField(max_length=20, blank=True)
    cpf = models.CharField(max_length=14, unique=True, blank=True, null=True)
    # Adicione campos como 'idade' ou 'interesses' no futuro para o BI
    
    def __str__(self):
        return f"Perfil de {self.user.username}"

class Empresa(models.Model):
    nome = models.CharField(max_length=100)
    cnpj = models.CharField(max_length=18, unique=True)
    site = models.URLField(blank=True)
    # Relacionamento para gestão: quais usuários podem editar eventos desta empresa
    colaboradores = models.ManyToManyField(User, related_name='empresas_gerenciadas')

    def __str__(self):
        return self.nome

class Espaco(models.Model):
    nome = models.CharField(max_length=100)
    endereco = models.CharField(max_length=255)
    lotacao_maxima = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.nome} ({self.lotacao_maxima} pessoas)"

class Categoria(models.Model):
    nome = models.CharField(max_length=50) # ex: Workshop, Show, Palestra

    def __str__(self):
        return self.nome

class Evento(models.Model):
    TIPO_CHOICES = (
        ('PAGO', 'Pago'),
        ('GRATUITO', 'Gratuito'),
    )

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='eventos')
    espaco = models.ForeignKey(Espaco, on_delete=models.SET_NULL, null=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    
    nome = models.CharField(max_length=200)
    descricao = models.TextField()
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='GRATUITO')
    valor_ingresso = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    imagem = models.ImageField(upload_to='eventos/', blank=True, null=True)
    ativo = models.BooleanField(default=True)

    # DICA DE OURO: Vagas restantes calculadas dinamicamente
    @property
    def vagas_restantes(self):
        if not self.espaco:
            return 0
        inscritos = self.inscricoes.filter(status='CONFIRMADO').count()
        return self.espaco.lotacao_maxima - inscritos

    def __str__(self):
        return self.nome

class EventoData(models.Model):
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name='datas')
    data_inicio = models.DateTimeField()
    data_fim = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Data do Evento"
        verbose_name_plural = "Datas do Evento"
        ordering = ['data_inicio']

class Inscricao(models.Model):
    STATUS_CHOICES = (
        ('PENDENTE', 'Pendente (Aguardando Pagamento)'),
        ('CONFIRMADO', 'Confirmado'),
        ('CANCELADO', 'Cancelado'),
    )

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='minhas_inscricoes')
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name='inscricoes')
    data_inscricao = models.DateTimeField(auto_now_add=True)
    
    # Controle Financeiro e QR Code
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDENTE')
    stripe_checkout_id = models.CharField(max_length=255, blank=True, null=True)
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)
    codigo_ticket = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        verbose_name_plural = "Inscrições"

    def __str__(self):
        return f"{self.usuario.username} - {self.evento.nome} ({self.status})"
>>>>>>> 6afa30f854d8f90322e9240233b553943522aacd

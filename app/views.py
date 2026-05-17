import stripe
import qrcode
from io import BytesIO
from django.core.files import File
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Count, Sum
from django.contrib.admin.views.decorators import staff_member_required

#Novidades abaixo
from django.http import HttpResponse
from django.template.loader import render_to_string
import tempfile
from datetime import datetime, timedelta
from xhtml2pdf import pisa
from django.utils import timezone
from .models import AssinaturaComprada 
#=======================================

# IMPORTANTE: Verifique se LogCarrinho está no seu models.py e importe aqui
from .models import Evento, Inscricao, Perfil, LogCarrinho, TicketType # Adicione TicketType aqui

stripe.api_key = settings.STRIPE_SECRET_KEY

from django.db.models import Q # Importe o Q para buscas complexas

# --- ATUALIZAÇÃO DA LISTA DE EVENTOS (Com Busca do Passo 2) ---
def lista_eventos(request):
    query = request.GET.get('q')
    categoria_slug = request.GET.get('categoria')
    
    eventos = Evento.objects.filter(ativo=True).select_related('categoria', 'espaco')
    
    # Lógica de Busca (Nome, Categoria ou Endereço/Região)
    if query:
        eventos = eventos.filter(
            Q(nome__icontains=query) | 
            Q(categoria__nome__icontains=query) |
            Q(espaco__endereco__icontains=query) |
            Q(espaco__nome__icontains=query)
        )
    
    # Filtro por Categoria (para o carrossel de categorias que virá depois)
    if categoria_slug:
        eventos = eventos.filter(categoria__nome__iexact=categoria_slug)

    return render(request, 'app/lista_eventos.html', {'eventos': eventos, 'query': query})

# --- NOVAS VIEWS PROTEGIDAS (Passo 1) ---

@login_required
def criar_evento(request):
    # Por enquanto, apenas renderiza, mas já está protegida
    # No futuro, aqui entrará o formulário de criação
    return render(request, 'app/criar_evento.html')

@login_required
def meus_eventos(request):
    """Eventos que o usuário (produtor) criou através de sua empresa"""
    # Filtra eventos onde o usuário é colaborador da empresa dona do evento
    eventos_produzidos = Evento.objects.filter(empresa__colaboradores=request.user)
    return render(request, 'app/meus_eventos.html', {'eventos': eventos_produzidos})

# --- FUNÇÕES AUXILIARES ---

def gerar_qr_code_inscricao(inscricao):
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(f"Ticket: {inscricao.codigo_ticket}")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    nome_arquivo = f'qr_{inscricao.codigo_ticket}.png'
    
    inscricao.qr_code.save(nome_arquivo, File(buffer), save=False)
    inscricao.save()

# --- VIEWS DE DASHBOARD (BI) ---

@staff_member_required
def dashboard_bi(request):
    total_inscritos = Inscricao.objects.count()
    receita_total = Inscricao.objects.filter(status='CONFIRMADO').aggregate(Sum('ticket_type__preco'))['ticket_type__preco__sum'] or 0
    logs_abandonados = LogCarrinho.objects.filter(finalizado=False).count()
    
    taxa_conversao = 0
    if (total_inscritos + logs_abandonados) > 0:
        taxa_conversao = (total_inscritos / (total_inscritos + logs_abandonados)) * 100

    eventos_mais_procurados = Evento.objects.annotate(
        num_logs=Count('logcarrinho'),
        num_vendas=Count('inscricao')
    ).order_by('-num_logs')[:5]

    context = {
        'total_inscritos': total_inscritos,
        'receita_total': receita_total,
        'logs_abandonados': logs_abandonados,
        'taxa_conversao': round(taxa_conversao, 1),
        'eventos_mais_procurados': eventos_mais_procurados,
    }
    return render(request, 'app/dashboard.html', context)

# --- VIEWS DE INSCRIÇÃO E PAGAMENTO ---

@login_required
def realizar_inscricao(request, evento_id):
    evento = get_object_or_404(Evento, id=evento_id)
    
    if request.method == "POST":
        # 1. Pegar o ID do lote selecionado no template
        ticket_type_id = request.POST.get('ticket_type_id')
        lote = get_object_or_404(TicketType, id=ticket_type_id, evento=evento)

        # 2. Verificar se o lote específico tem vagas
        if not lote.disponivel:
            messages.error(request, f"O lote {lote.nome} já esgotou!")
            return redirect('detalhe_evento', evento_id=evento.id)

        # 3. Fluxo de Pagamento (PAGO)
        if lote.preco > 0:
            try:
                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=[{
                        'price_data': {
                            'currency': 'brl',
                            'unit_amount': int(lote.preco * 100), # Preço do Lote
                            'product_data': {
                                'name': f"{evento.nome} - {lote.nome}", # Nome detalhado
                            },
                        },
                        'quantity': 1,
                    }],
                    mode='payment',
                    # Passamos o ID do lote na URL de sucesso para saber o que o cara comprou
                    success_url=request.build_absolute_uri(f'/sucesso_pagamento/{evento.id}/?lote_id={lote.id}'),
                    cancel_url=request.build_absolute_uri(f'/evento/{evento.id}/'),
                )
                return redirect(checkout_session.url, code=303)
            except Exception as e:
                messages.error(request, "Erro ao processar pagamento.")
                return redirect('detalhe_evento', evento_id=evento.id)
        
        # 4. Fluxo Gratuito
        else:
            inscricao = Inscricao.objects.create(
                usuario=request.user, 
                evento=evento, 
                ticket_type=lote, # Salva o lote selecionado
                status='CONFIRMADO'
            )
            # Incrementa contador de vendas do lote
            lote.quantidade_vendida += 1
            lote.save()
            
            gerar_qr_code_inscricao(inscricao)
            messages.success(request, "Inscrição gratuita confirmada!")
            return redirect('pagina_sucesso', inscricao_id=inscricao.id)

    return redirect('detalhe_evento', evento_id=evento.id)
@login_required
def sucesso_pagamento(request, evento_id):
    evento = get_object_or_404(Evento, id=evento_id)
    lote_id = request.GET.get('lote_id')
    lote = get_object_or_404(TicketType, id=lote_id)

    # Cria a inscrição vinculada ao lote correto
    inscricao = Inscricao.objects.create(
        usuario=request.user, 
        evento=evento, 
        ticket_type=lote, 
        status='CONFIRMADO' # Se o Stripe redirecionou para cá, está pago
    )
    
    # Atualiza estoque do lote
    lote.quantidade_vendida += 1
    lote.save()

    gerar_qr_code_inscricao(inscricao)
    
    # BI: Finaliza o log
    LogCarrinho.objects.filter(usuario=request.user, evento_id=evento_id, finalizado=False).update(finalizado=True)
    
    if 'carrinho' in request.session:
        del request.session['carrinho']
    
    messages.success(request, "Pagamento aprovado!")
    return redirect('pagina_sucesso', inscricao_id=inscricao.id)

# --- VIEWS DE CARRINHO ---

@login_required
def adicionar_ao_carrinho(request, evento_id):
    evento = get_object_or_404(Evento, id=evento_id)
    # Pegamos o lote que vem do formulário (o mesmo que usamos na compra direta)
    ticket_type_id = request.POST.get('ticket_type_id') 
    lote = get_object_or_404(TicketType, id=ticket_type_id, evento=evento)

    carrinho = request.session.get('carrinho', {})
    
    # A chave do carrinho agora precisa ser o ID do Lote para evitar confusão
    carrinho[str(ticket_type_id)] = {
        'evento_nome': evento.nome,
        'lote_nome': lote.nome,
        'preco': float(lote.preco),
        'evento_id': evento.id,
        'imagem': evento.imagem.url if evento.imagem else None
    }
    request.session['carrinho'] = carrinho
    
    LogCarrinho.objects.get_or_create(usuario=request.user, evento=evento, finalizado=False)
    
    messages.success(request, f"{lote.nome} de {evento.nome} adicionado!")
    return redirect('detalhe_evento', evento_id=evento.id)
def ver_carrinho(request):
    carrinho = request.session.get('carrinho', {})
    total = sum(item['preco'] for item in carrinho.values())
    return render(request, 'app/carrinho.html', {'carrinho': carrinho, 'total': total})

@login_required
def checkout_carrinho(request):
    carrinho = request.session.get('carrinho', {})
    if not carrinho: return redirect('lista_eventos')

    line_items = []
    for item_id, item in carrinho.items():
        line_items.append({
            'price_data': {
                'currency': 'brl',
                'unit_amount': int(item['preco'] * 100),
                'product_data': {'name': f"{item['evento_nome']} - {item['lote_nome']}"},
            },
            'quantity': 1,
        })

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=request.build_absolute_uri('/sucesso_carrinho/'),
            cancel_url=request.build_absolute_uri('/carrinho/'),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return render(request, 'app/carrinho.html', {'error': str(e)})

@login_required
def sucesso_carrinho(request):
    carrinho = request.session.get('carrinho', {})
    for lote_id, item in carrinho.items():
        evento = get_object_or_404(Evento, id=item['evento_id'])
        lote = get_object_or_404(TicketType, id=int(lote_id))
        
        # Cria a inscrição vinculada ao lote
        inscricao = Inscricao.objects.create(
            usuario=request.user, 
            evento=evento, 
            ticket_type=lote, 
            status='CONFIRMADO'
        )
        
        # Atualiza estoque do lote
        lote.quantidade_vendida += 1
        lote.save()
        
        gerar_qr_code_inscricao(inscricao)
        LogCarrinho.objects.filter(usuario=request.user, evento_id=evento.id, finalizado=False).update(finalizado=True)

    del request.session['carrinho']
    messages.success(request, "Compra do carrinho realizada!")
    return redirect('meus_ingressos')
# --- OUTRAS VIEWS ---

def lista_eventos(request):
    eventos = Evento.objects.filter(ativo=True).select_related('categoria', 'espaco')
    return render(request, 'app/lista_eventos.html', {'eventos': eventos})

def detalhe_evento(request, evento_id):
    evento = get_object_or_404(Evento, id=evento_id)
    return render(request, 'app/detalhe_evento.html', {'evento': evento, 'esgotado': evento.vagas_restantes <= 0})

@login_required
def pagina_sucesso(request, inscricao_id):
    inscricao = get_object_or_404(Inscricao, id=inscricao_id, usuario=request.user)
    return render(request, 'app/sucesso.html', {'inscricao': inscricao})

@login_required
def meus_ingressos(request):
    ingressos = Inscricao.objects.filter(usuario=request.user).select_related('evento')
    return render(request, 'app/meus_ingressos.html', {'ingressos': ingressos})

def cadastro(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            Perfil.objects.create(user=user)
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'app/cadastro.html', {'form': form})

@login_required
def verificar_assinatura(request):
    # Procura o perfil do utilizador logado
    perfil = request.user.perfil
    
    if perfil.is_colaborador:
        # Se for assinante, vai para a página de criação
        return redirect('publicar_evento')
    else:
        # Se não for, envia mensagem e vai para a venda
        messages.info(request, "Torna-te um colaborador para publicares os teus próprios eventos!")
        return redirect('pagina_assinatura')

def pagina_assinatura(request):
    # Aqui vamos renderizar a página de vendas (estilo Sympla)
    return render(request, 'app/pagina_assinatura.html')


# =================================================================
# CUIDADO PRA NÃO APAGAR DAQUI PRA BAIXO . TUDO ISSO VAI ENTRAR :)
# =================================================================

# 1. View Auxiliar: Download do Boleto em PDF dinâmico com dados da URL
@login_required
def baixar_boleto(request):
    plano_slug = request.GET.get('plano', 'anual')
    
    precos = {'mensal': 59.90, 'trimestral': 79.90, 'anual': 399.00}
    valor_num = precos.get(plano_slug.lower(), 399.00)
    
    context = {
        'plano': plano_slug.upper(),
        'valor': f"{valor_num:.2f}".replace('.', ','),
        'data_emissao': datetime.now().strftime('%d/%m/%Y'),
        'vencimento': "Em 10 dias",
        'cedente_nome': "SOLUCOES TECH LTDA",
        'agencia': "0001",
        'conta': "1234567-8",
        'banco': "033 - SANTANDER",
        'codigo_barras': "03399.01234 56789.012345 67890.123456 1 95430000039900",
        
        'cliente': {
            'nome_empresa': request.GET.get('nome_empresa', 'Não Informado'),
            'cnpj': request.GET.get('cnpj', 'Não Informado'),
            'nome_representante': request.GET.get('nome_representante', 'Não Informado'),
            'cpf': request.GET.get('cpf', 'Não Informado'),
            'cidade': request.GET.get('cidade', ''),
            'estado': request.GET.get('estado', ''),
        }
    }
    
    html_string = render_to_string('app/baixar_boleto.html', context)
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="boleto_{plano_slug}.pdf"'
    
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    from xhtml2pdf import pisa
    pisa.CreatePDF(html_string, dest=response)
    
    return response


@login_required
def checkout_assinatura(request):
    plano_slug = request.GET.get('plano') or request.POST.get('plano') or 'anual'
    
    precos = {
        'mensal': {'nome': 'Mensal', 'valor': 59.90, 'periodo': 'mês'},
        'trimestral': {'nome': 'Trimestral', 'valor': 79.90 , 'periodo': 'trimestre'},
        'anual': {'nome': 'Anual', 'valor': 399.00 , 'periodo': 'ano'}
    }
    plano_info = precos.get(plano_slug.lower(), precos['anual'])

    if request.method == "POST" and 'finalizar' in request.POST:
        perfil = request.user.perfil
        
        # 1. Atualiza e salva os dados cadastrais da empresa no Perfil
        perfil.nome_empresa = request.POST.get('nome_empresa')
        perfil.cnpj = request.POST.get('cnpj')
        perfil.cidade = request.POST.get('cidade')
        perfil.estado = request.POST.get('estado')
        perfil.email_empresarial = request.POST.get('email_empresarial')
        perfil.whatsapp = request.POST.get('whatsapp')
        perfil.nome_representante = request.POST.get('nome_representante')
        perfil.cpf = request.POST.get('cpf_representante')
        perfil.is_colaborador = True
        perfil.save()
        
        metodo = request.POST.get('metodo')
        
        # 2. Calcula o tempo de vigência da assinatura
        data_base = timezone.now()
        if plano_slug.lower() == 'mensal':
            vencimento = data_base + timedelta(days=30)
        elif plano_slug.lower() == 'trimestral':
            vencimento = data_base + timedelta(days=90)
        else:
            vencimento = data_base + timedelta(days=365)
            
        # 3. CRIAÇÃO OBRIGATÓRIA DO REGISTRO NA TABELA NOVA (O que gera os cards na tela)
        AssinaturaComprada.objects.create(
            usuario=request.user,
            tipo_plano=plano_slug.lower(),
            metodo_pagamento=metodo,
            data_vencimento=vencimento,
            ativa=(metodo != 'boleto')
        )
        
        if metodo == 'boleto':
            messages.info(request, "Assinatura registrada! Use o simulador abaixo para confirmar o pagamento do boleto.")
            return redirect('minha_assinatura') # Corrigido: Manda para a tela de gerenciamento

        messages.success(request, f"Assinatura {plano_info['nome']} ativada com sucesso!")
        return redirect('minha_assinatura')

    return render(request, 'app/checkout_assinatura.html', {
        'plano': plano_info['nome'],
        'plano_slug': plano_slug,
        'plano_info': plano_info
    })

@login_required
def minha_assinatura_view(request):
    # Esta linha vai ao banco de dados e busca todas as compras do usuário logado
    assinaturas = AssinaturaComprada.objects.filter(usuario=request.user).order_by('-data_compra')
    
    beneficios = [
        "Criação ilimitada de eventos",
        "Acesso completo ao painel de BI / Dashboard",
        "Gestão avançada de espaços e lotação",
        "Suporte corporativo prioritário 24/7",
        "Emissão de ingressos com QR Code personalizado"
    ]
            
    return render(request, 'app/minha_assinatura.html', {
        'assinaturas': assinaturas,  # Certifique-se de que o HTML recebe exatamente a lista de objetos
        'beneficios': beneficios,
    })

# =====================================================================
# 4. View de Validação: Confere Nome/CPF e ativa a assinatura específica
# =====================================================================
@login_required
def confirmar_boleto(request):
    if request.method == "POST":
        nome_digitado = request.POST.get('nome_verificar', '').strip()
        cpf_digitado = request.POST.get('cpf_verificar', '').strip()
        
        perfil = request.user.perfil
        
        # Limpa pontuações de ambos os lados para fazer uma comparação 100% segura
        cpf_digitado_limpo = cpf_digitado.replace('.', '').replace('-', '')
        cpf_banco_limpo = perfil.cpf.replace('.', '').replace('-', '') if perfil.cpf else ''
        
        if perfil.nome_representante.lower() == nome_digitado.lower() and cpf_banco_limpo == cpf_digitado_limpo:
            
            # Localiza a assinatura de boleto mais recente deste usuário que esteja inativa (False)
            assinatura_pendente = AssinaturaComprada.objects.filter(
                usuario=request.user, 
                metodo_pagamento='boleto', 
                ativa=False
            ).last()
            
            if status_pendente := assinatura_pendente:
                status_pendente.ativa = True
                status_pendente.save()
                messages.success(request, f"Simulação aceita! Seu boleto da Assinatura {status_pendente.get_tipo_plano_display()} foi compensado e o acesso foi liberado.")
                return redirect('minha_assinatura')
            else:
                messages.info(request, "Nenhuma assinatura pendente de boleto aguardando liberação.")
                return redirect('minha_assinatura')
        else:
            messages.error(request, "Dados incorretos! O Nome do Representante ou o CPF informados não conferem.")
            return redirect('minha_assinatura')
            
    return redirect('minha_assinatura')

@login_required
def confirmar_pagamento(request):
    perfil = request.user.perfil
    perfil.assinatura_paga = True
    perfil.save()
    messages.success(request, "Pagamento confirmado! Acesso liberado.")
    return redirect('criar_evento')

@login_required
def cancelar_assinatura(request, assinatura_id):
    if request.method == "POST":
        # Busca a assinatura garantindo que ela pertence ao usuário logado
        assinatura = get_object_or_404(AssinaturaComprada, id=assinatura_id, usuario=request.user)
        
        # Opcional: Se quiser remover o status de colaborador do perfil ao cancelar
        perfil = request.user.perfil
        perfil.is_colaborador = False
        perfil.save()
        
        # Deleta o registro do banco de dados (fazendo o card sumir da lista)
        assinatura.delete()
        
        messages.success(request, "Assinatura cancelada e removida com sucesso.")
        return redirect('minha_assinatura')
        
    return redirect('minha_assinatura')
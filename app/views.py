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
                'unit_amount': int(round(float(item['preco']) * 100)),
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

@login_required
def remover_do_carrinho(request, lote_id):
    carrinho = request.session.get('carrinho', {})
    lote_id_str = str(lote_id)
    
    if lote_id_str in carrinho:
        del carrinho[lote_id_str]
        request.session['carrinho'] = carrinho
        messages.success(request, "Item removido do carrinho.")
    
    return redirect('ver_carrinho')
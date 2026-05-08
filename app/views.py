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
from .models import Evento, Inscricao, Perfil, LogCarrinho 

stripe.api_key = settings.STRIPE_SECRET_KEY

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
    receita_total = Inscricao.objects.filter(status='PAGO').aggregate(Sum('evento__valor_ingresso'))['evento__valor_ingresso__sum'] or 0
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
        if evento.vagas_restantes <= 0:
            messages.error(request, "Vagas esgotadas!")
            return redirect('detalhe_evento', evento_id=evento.id)

        if evento.tipo == 'PAGO':
            try:
                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=[{
                        'price_data': {
                            'currency': 'brl',
                            'unit_amount': int(evento.valor_ingresso * 100),
                            'product_data': {'name': evento.nome},
                        },
                        'quantity': 1,
                    }],
                    mode='payment',
                    success_url=request.build_absolute_uri(f'/sucesso_pagamento/{evento.id}/'),
                    cancel_url=request.build_absolute_uri(f'/evento/{evento.id}/'),
                )
                return redirect(checkout_session.url, code=303)
            except Exception as e:
                messages.error(request, "Erro ao processar pagamento.")
                return redirect('detalhe_evento', evento_id=evento.id)
        else:
            inscricao = Inscricao.objects.create(usuario=request.user, evento=evento, status='CONFIRMADO')
            gerar_qr_code_inscricao(inscricao)
            messages.success(request, "Inscrição gratuita confirmada!")
            return redirect('pagina_sucesso', inscricao_id=inscricao.id)

    return redirect('detalhe_evento', evento_id=evento.id)

@login_required
def sucesso_pagamento(request, evento_id):
    evento = get_object_or_404(Evento, id=evento_id)
    inscricao = Inscricao.objects.create(usuario=request.user, evento=evento, status='PAGO')
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
    carrinho = request.session.get('carrinho', {})
    carrinho[str(evento_id)] = {
        'nome': evento.nome,
        'preco': float(evento.valor_ingresso),
        'imagem': evento.imagem.url if evento.imagem else None
    }
    request.session['carrinho'] = carrinho

    # BI: Registra intenção
    LogCarrinho.objects.get_or_create(usuario=request.user, evento=evento, finalizado=False)
    
    messages.success(request, f"{evento.nome} no carrinho!")
    return redirect('lista_eventos')

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
                'product_data': {'name': item['nome']},
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
    for ev_id, item in carrinho.items():
        evento = get_object_or_404(Evento, id=int(ev_id))
        inscricao = Inscricao.objects.create(usuario=request.user, evento=evento, status='PAGO')
        gerar_qr_code_inscricao(inscricao)
        LogCarrinho.objects.filter(usuario=request.user, evento_id=evento.id, finalizado=False).update(finalizado=True)

    del request.session['carrinho']
    messages.success(request, "Compra realizada com sucesso!")
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
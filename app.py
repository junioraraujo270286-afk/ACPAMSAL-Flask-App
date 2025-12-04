import sys
import os # Importação necessária para ler a variável de ambiente do Heroku
# Adiciona o diretório atual ao sys.path para garantir que 'database' seja encontrado
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from functools import wraps
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, or_

# Importar modelos do nosso arquivo database.py
from database import init_db, db, Usuario, Associado, Pagamento, Despesa, Configuracao

# ----------------------------------------------------
# 1. CONFIGURAÇÃO DA APLICAÇÃO
# ----------------------------------------------------

app = Flask(__name__)
# MUDE ESTA CHAVE SECRETA EM PRODUÇÃO!
app.secret_key = 'chave_secreta_muito_forte_e_unica_acpamsal_12345'

# LÓGICA DE CONEXÃO AO BANCO DE DADOS (SQLite para dev / PostgreSQL para Heroku)
if 'DATABASE_URL' in os.environ:
    # Heroku PostgreSQL (usa a variável de ambiente, ajustando o esquema para SQLAlchemy)
    # A SQLAlchemy moderna precisa que "postgres://" seja "postgresql://"
    uri = os.environ.get('DATABASE_URL')
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
else:
    # SQLite local (para desenvolvimento)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///acpamsal.db'
    
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializa o banco de dados e cria as tabelas
init_db(app)

# ----------------------------------------------------
# 2. DECORADORES DE SEGURANÇA
# ----------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Você precisa fazer login para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_type') != 'admin':
            flash('Acesso negado. Apenas administradores.', 'danger')
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Adiciona datetime ao contexto para uso nos templates (como no cadastro)
@app.context_processor
def inject_now():
    return {'datetime': datetime, 'now': datetime.now()}

# ----------------------------------------------------
# 3. FUNÇÕES DE LÓGICA FINANCEIRA
# ----------------------------------------------------

def get_mensalidade_base():
    config = Configuracao.query.filter_by(chave='mensalidade_base').first()
    try:
        return float(config.valor) 
    except (ValueError, AttributeError):
        return 10.00 # Valor de fallback

def get_data_inicio_cobranca():
    config = Configuracao.query.filter_by(chave='data_inicio_cobranca').first()
    try:
        return datetime.strptime(config.valor, '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        return datetime.now().date() 

def get_meses_devidos(associado_id):
    mensalidade_base = get_mensalidade_base()
    
    assoc = Associado.query.get(associado_id)
    if not assoc:
        return [], 0.00
    
    data_inicio_cobranca = get_data_inicio_cobranca().replace(day=1)

    ultimo_pagamento = Pagamento.query.filter_by(associado_id=associado_id).order_by(Pagamento.mes_referencia.desc()).first()
    
    if ultimo_pagamento:
        start_date = ultimo_pagamento.mes_referencia + relativedelta(months=1)
    else:
        start_date = data_inicio_cobranca

    if start_date < data_inicio_cobranca:
        start_date = data_inicio_cobranca

    hoje = datetime.now().date().replace(day=1)
    
    meses_devidos = []

    if start_date > hoje:
        return [], 0.00

    current = start_date
    while current <= hoje:
        pagamento_existe = Pagamento.query.filter(
            Pagamento.associado_id == associado_id,
            # Em PostgreSQL (Heroku), func.strftime pode dar erro. 
            # É mais seguro usar comparações diretas de date/datetime ou extrair o ano/mês
            # MANTENDO O PADRÃO SQLITE/POSTGRES GENÉRICO ABAIXO.
            Pagamento.mes_referencia == current
        ).first()

        if not pagamento_existe:
            meses_devidos.append(current)

        current += relativedelta(months=1)

    divida_total = len(meses_devidos) * mensalidade_base
    return meses_devidos, divida_total

def get_status_financeiro_detalhado(associado_id):
    """Retorna o status financeiro do associado com base no número de meses devidos."""
    meses_devidos, _ = get_meses_devidos(associado_id)
    
    num_meses_devidos = len(meses_devidos)
    
    if num_meses_devidos == 0:
        return 'Ativo (em dias)', 'success'
    elif num_meses_devidos <= 2:
        return f'Atrasado ({num_meses_devidos} meses em atraso)', 'warning'
    elif num_meses_devidos == 3:
        return 'Inativo (3 meses em atraso)', 'info'
    elif num_meses_devidos >= 4:
        return 'Desligado (mais de 4 meses em atraso)', 'danger'
    else:
        return 'Desconhecido', 'secondary'

def get_dash_metrics():
    """Busca todas as métricas necessárias para o Painel Administrativo, garantindo que valores nulos sejam tratados como 0.00."""
    mensalidade_base = get_mensalidade_base()
    
    total_associados = Associado.query.count()
    
    total_despesas = float(db.session.query(func.sum(Despesa.valor)).scalar() or 0.00)
    
    total_divida_estimada = 0.00
    for assoc in Associado.query.all():
        _, divida = get_meses_devidos(assoc.id)
        total_divida_estimada += divida
        
    total_receita = float(db.session.query(func.sum(Pagamento.valor_pago)).scalar() or 0.00)
    
    saldo_aproximado = total_receita - total_despesas

    return {
        'total_associados': total_associados,
        'total_divida': total_divida_estimada,
        'total_despesas': total_despesas,
        'total_receita': total_receita,
        'saldo_aproximado': saldo_aproximado,
        'mensalidade_base': mensalidade_base
    }

# ----------------------------------------------------
# 4. ROTAS DE AUTENTICAÇÃO E DASHBOARD
# ----------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Rota para login de administradores."""
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        usuario = Usuario.query.filter_by(email=email).first()
        
        if usuario and usuario.tipo == 'admin' and check_password_hash(usuario.senha, senha):
            session['logged_in'] = True
            session['user_id'] = usuario.id
            session['user_type'] = 'admin'
            flash(f'Bem-vindo(a), {usuario.nome}!', 'success')
            return redirect(url_for('admin_dashboard'))
        
        flash('Credenciais inválidas. Tente novamente.', 'danger')
        return redirect(url_for('login'))
        
    return render_template('login.html', instituicao='ACPAMSAL')

@app.route('/login_publico', methods=['POST'])
def login_publico():
    """Login para usuários de consulta pública."""
    nome_usuario = request.form.get('usuario')
    senha_publica = request.form.get('senha')
    
    usuario = Usuario.query.filter_by(nome=nome_usuario, tipo='publico').first()
    
    if usuario and usuario.senha == senha_publica: 
        session['logged_in'] = True
        session['user_id'] = usuario.id
        session['user_type'] = 'publico'
        flash(f'Bem-vindo(a), {usuario.nome}. Consulta liberada.', 'info')
        return redirect(url_for('dashboard_publico'))
    
    flash('Consulta pública inválida. Verifique usuário e senha.', 'warning')
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def admin_dashboard():
    if session.get('user_type') == 'publico':
        return redirect(url_for('dashboard_publico'))
        
    metrics = get_dash_metrics()
    return render_template('admin_dashboard.html', **metrics)

@app.route('/dashboard_publico')
@login_required
def dashboard_publico():
    if session.get('user_type') == 'admin':
        return redirect(url_for('admin_dashboard'))
        
    config = Configuracao.query.all()
    config_dict = {c.chave: c.valor for c in config}
    
    return render_template('dashboard_publico.html', config=config_dict, resultado_busca=None)

@app.route('/consulta_associado', methods=['POST'])
@login_required
def consulta_associado():
    """Rota para buscar associado por múltiplos critérios no painel público."""
    
    termo = request.form.get('termo_busca', '').strip()
    config = Configuracao.query.all()
    config_dict = {c.chave: c.valor for c in config}
    
    resultado = {
        'encontrado': False,
        'mensagem': 'Nenhum associado encontrado com o termo fornecido.'
    }
    
    if termo:
        assoc = Associado.query.filter(
            or_(
                Associado.matricula.ilike(f'%{termo}%'),
                Associado.nome.ilike(f'%{termo}%'),
                Associado.placa.ilike(f'%{termo}%'),
                Associado.rg.ilike(f'%{termo}%'),
                Associado.cpf.ilike(f'%{termo}%')
            )
        ).first()

        if assoc:
            status_financeiro_completo, _ = get_status_financeiro_detalhado(assoc.id)
            
            if 'Ativo' in status_financeiro_completo:
                status_final = 'ASSOCIADO ATIVO (EM DIAS)'
                cor_status = 'success'
            elif 'Desligado' in status_financeiro_completo or 'Inativo' in status_financeiro_completo:
                status_final = 'ASSOCIADO INATIVO/DESLIGADO'
                cor_status = 'danger'
            else:
                status_final = 'ASSOCIADO ATIVO (EM ATRASO)'
                cor_status = 'warning'
                
            resultado = {
                'encontrado': True,
                'nome': assoc.nome,
                'matricula': assoc.matricula,
                'placa': assoc.placa,
                'status_associacao': status_final,
                'cor_status': cor_status
            }
        
    return render_template('dashboard_publico.html', config=config_dict, resultado_busca=resultado)

# ----------------------------------------------------
# 5. ROTAS DE GERENCIAMENTO DE ASSOCIADOS (CRUD)
# ----------------------------------------------------

@app.route('/associados')
@login_required
@admin_required
def listar_associados():
    associados_raw = Associado.query.all()
    
    associados = []
    for assoc in associados_raw:
        meses_devidos, divida_total = get_meses_devidos(assoc.id)
        
        status_financeiro, status_class = get_status_financeiro_detalhado(assoc.id)
        
        divida_formatada = f"R$ {'{:,.2f}'.format(divida_total).replace('.', 'X').replace(',', '.').replace('X', ',')}"
        
        associados.append({
            'id': assoc.id,
            'matricula': assoc.matricula,
            'nome': assoc.nome,
            'placa': assoc.placa,
            'status': status_financeiro,
            'status_class': status_class,
            'divida': divida_formatada,
            'total_devido': len(meses_devidos)
        })
        
    return render_template('associados.html', associados=associados)

@app.route('/associados/cadastrar', methods=['GET', 'POST'])
@login_required
@admin_required
def cadastrar_associado():
    if request.method == 'POST':
        try:
            novo_assoc = Associado(
                matricula=request.form['matricula'],
                nome=request.form['nome'],
                cpf=request.form['cpf'],
                rg=request.form['rg'],
                bairro=request.form['bairro'],
                rua=request.form['rua'],
                numero=request.form['numero'],
                placa=request.form['placa'],
                cor=request.form['cor'],
                ano=request.form['ano'],
                renavam=request.form['renavam']
            )
            db.session.add(novo_assoc)
            db.session.commit()
            flash(f'Associado "{novo_assoc.nome}" cadastrado com sucesso!', 'success')
            return redirect(url_for('listar_associados'))
        except IntegrityError:
            db.session.rollback()
            flash('Erro: Matrícula, CPF ou Placa já existem no sistema.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao cadastrar: {e}', 'danger')
            
    return render_template('cadastro_associado.html')

@app.route('/associados/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_associado(id):
    associado = Associado.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            associado.nome = request.form['nome']
            associado.cpf = request.form['cpf']
            associado.rg = request.form['rg']
            associado.bairro = request.form['bairro']
            associado.rua = request.form['rua']
            associado.numero = request.form['numero']
            associado.placa = request.form['placa']
            associado.cor = request.form['cor']
            associado.ano = request.form['ano']
            associado.renavam = request.form['renavam']
            
            db.session.commit()
            flash(f'Dados de "{associado.nome}" atualizados com sucesso!', 'success')
            return redirect(url_for('listar_associados'))
        except IntegrityError:
            db.session.rollback()
            flash('Erro: CPF ou Placa já existem em outro registro.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao editar: {e}', 'danger')

    return render_template('editar_associado.html', associado=associado)

@app.route('/associados/remover/<int:id>', methods=['POST'])
@login_required
@admin_required
def remover_associado(id):
    associado = Associado.query.get_or_404(id)
    try:
        nome_removido = associado.nome
        db.session.delete(associado)
        db.session.commit()
        flash(f'Associado "{nome_removido}" e todo seu histórico removidos com sucesso.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao remover associado: {e}', 'danger')
        
    return redirect(url_for('listar_associados'))

# ----------------------------------------------------
# 6. ROTAS DE GERENCIAMENTO DE MENSALIDADES E DESPESAS
# ----------------------------------------------------

@app.route('/mensalidades')
@login_required
@admin_required
def gerenciar_mensalidades_web():
    associados_raw = Associado.query.all()
    mensalidade_base = get_mensalidade_base()
    
    associados = []
    total_devido = 0
    for assoc in associados_raw:
        meses_devidos, divida_total = get_meses_devidos(assoc.id)
        
        status_financeiro, status_class = get_status_financeiro_detalhado(assoc.id)
        
        total_devido += len(meses_devidos)
        
        divida_formatada = f"R$ {'{:,.2f}'.format(divida_total).replace('.', 'X').replace(',', '.').replace('X', ',')}"
        
        associados.append({
            'id': assoc.id,
            'matricula': assoc.matricula,
            'nome': assoc.nome,
            'status': status_financeiro,
            'status_class': status_class,
            'divida': divida_formatada,
            'total_devido': len(meses_devidos),
            'meses_devidos': meses_devidos
        })
        
    return render_template('mensalidades.html', associados=associados, total_devido=total_devido, mensalidade_base=mensalidade_base)

@app.route('/pagamento/<int:associado_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def registrar_pagamento(associado_id):
    associado = Associado.query.get_or_404(associado_id)
    mensalidade_base = get_mensalidade_base()
    
    if request.method == 'POST':
        mes_ano_str = request.form.get('mes_ano')
        acao = request.form.get('acao')
        
        try:
            mes_referencia = datetime.strptime(mes_ano_str, '%Y-%m').date().replace(day=1)
            
            if acao == 'registrar':
                pagamento_existente = Pagamento.query.filter(
                    Pagamento.associado_id == associado_id,
                    Pagamento.mes_referencia == mes_referencia
                ).first()
                
                if pagamento_existente:
                    flash(f'Pagamento para {mes_referencia.strftime("%B/%Y")} já estava registrado.', 'warning')
                else:
                    novo_pagamento = Pagamento(
                        associado_id=associado_id,
                        mes_referencia=mes_referencia,
                        valor_pago=mensalidade_base 
                    )
                    db.session.add(novo_pagamento)
                    db.session.commit()
                    flash(f'Pagamento de {mes_referencia.strftime("%B/%Y")} registrado para {associado.nome}.', 'success')
                    
            elif acao == 'remover':
                pagamento_remover = Pagamento.query.filter(
                    Pagamento.associado_id == associado_id,
                    Pagamento.mes_referencia == mes_referencia
                ).first()
                
                if pagamento_remover:
                    db.session.delete(pagamento_remover)
                    db.session.commit()
                    flash(f'Pagamento de {mes_referencia.strftime("%B/%Y")} removido com sucesso.', 'info')
                else:
                    flash(f'Nenhum pagamento encontrado para {mes_referencia.strftime("%B/%Y")}.', 'warning')
                    
        except ValueError:
            flash('Formato de mês inválido. Use AAAA-MM.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro na operação: {e}', 'danger')
            
        return redirect(url_for('registrar_pagamento', associado_id=associado_id))

    meses_devidos_lista, _ = get_meses_devidos(associado_id)
    
    historico_pagamentos = Pagamento.query.filter_by(associado_id=associado_id).order_by(Pagamento.mes_referencia.desc()).all()
    
    return render_template(
        'registrar_pagamento.html', 
        associado=associado, 
        associado_id=associado_id, 
        mensalidade_base=mensalidade_base,
        meses_devidos_lista=meses_devidos_lista,
        historico_pagamentos=historico_pagamentos
    )


@app.route('/despesas', methods=['GET', 'POST'])
@login_required
@admin_required
def gerenciar_despesas_web():
    if request.method == 'POST':
        try:
            valor = float(request.form['valor'])
            data_str = request.form['data']
            
            nova_despesa = Despesa(
                descricao=request.form['descricao'],
                valor=valor,
                data=datetime.strptime(data_str, '%Y-%m-%d').date(),
                categoria=request.form.get('categoria', 'Geral')
            )
            db.session.add(nova_despesa)
            db.session.commit()
            flash(f'Despesa "{nova_despesa.descricao}" registrada com sucesso.', 'success')
            return redirect(url_for('gerenciar_despesas_web'))
        except ValueError:
            flash('Valor ou Data inválidos.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao registrar despesa: {e}', 'danger')

    despesas = Despesa.query.order_by(Despesa.data.desc()).all()
    total_despesa = db.session.query(func.sum(Despesa.valor)).scalar() or 0.00
    
    return render_template('despesas.html', despesas=despesas, total_despesa=total_despesa)

@app.route('/despesas/remover/<int:despesa_id>', methods=['POST'])
@login_required
@admin_required
def remover_despesa(despesa_id):
    despesa = Despesa.query.get_or_404(despesa_id)
    try:
        descricao = despesa.descricao
        db.session.delete(despesa)
        db.session.commit()
        flash(f'Despesa "{descricao}" removida com sucesso.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao remover despesa: {e}', 'danger')
        
    return redirect(url_for('gerenciar_despesas_web'))

@app.route('/relatorios')
@login_required
@admin_required
def relatorios_web():
    metrics = get_dash_metrics()
    saldo = metrics['total_receita'] - metrics['total_despesas']
    
    return render_template(
        'relatorios.html', 
        total_receita=metrics['total_receita'],
        total_despesas=metrics['total_despesas'],
        total_divida=metrics['total_divida'],
        saldo=saldo
    )

# ----------------------------------------------------
# 7. ROTA DE GERENCIAMENTO DE USUÁRIOS PÚBLICOS
# ----------------------------------------------------

@app.route('/admin/usuarios/criar', methods=['GET', 'POST'])
@login_required
@admin_required
def criar_usuario_consulta_publica():
    """Formulário e lógica para criar usuários de consulta pública."""
    
    if request.method == 'POST':
        nome = request.form['nome']
        senha = request.form['senha']
        
        email_gerado = f'{nome.lower().replace(" ", "")}@publico.com'
        
        if Usuario.query.filter_by(nome=nome, tipo='publico').first() or Usuario.query.filter_by(email=email_gerado).first():
            flash('Erro: Já existe um usuário de consulta pública com este nome ou o e-mail gerado.', 'danger')
            return redirect(url_for('criar_usuario_consulta_publica'))

        try:
            novo_publico = Usuario(
                email=email_gerado,
                nome=nome,
                senha=senha, 
                tipo='publico'
            )
            db.session.add(novo_publico)
            db.session.commit()
            flash(f'Usuário de Consulta Pública "{nome}" criado com sucesso! Senha: {senha}', 'success')
            return redirect(url_for('criar_usuario_consulta_publica'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar usuário: {e}', 'danger')
            
    usuarios_publicos = Usuario.query.filter_by(tipo='publico').all()
    
    return render_template('criar_usuario_publico.html', usuarios=usuarios_publicos)
    
@app.route('/admin/usuarios/remover/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def remover_usuario_publico(user_id):
    usuario = Usuario.query.get_or_404(user_id)
    if usuario.tipo != 'publico':
        flash('Apenas usuários de consulta pública podem ser removidos por esta rota.', 'danger')
        return redirect(url_for('criar_usuario_consulta_publica'))
        
    try:
        nome_removido = usuario.nome
        db.session.delete(usuario)
        db.session.commit()
        flash(f'Usuário de consulta pública "{nome_removido}" removido com sucesso.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao remover usuário: {e}', 'danger')
        
    return redirect(url_for('criar_usuario_consulta_publica'))

# ----------------------------------------------------
# 8. INICIALIZAÇÃO E ADMIN DEFAULT
# ----------------------------------------------------

if __name__ == '__main__':
    with app.app_context():
        
        # CRIAÇÃO DO USUÁRIO ADMINISTRADOR PADRÃO (CREDENCIAIS SOLICITADAS)
        if not Usuario.query.filter_by(email='acpamsal@gmail.com').first():
            hashed_password = generate_password_hash('230808Deus#') 
            
            novo_admin = Usuario(
                email='acpamsal@gmail.com',
                nome='Admin Principal',
                senha=hashed_password, 
                tipo='admin'
            )
            db.session.add(novo_admin)
            db.session.commit()
            
            print("----------------------------------------------------")
            print("🚀 SETUP CONCLUÍDO!")
            print("ADMIN CRIADO: acpamsal@gmail.com | SENHA: 230808Deus#")
            print("----------------------------------------------------")
            
    app.run(debug=True)

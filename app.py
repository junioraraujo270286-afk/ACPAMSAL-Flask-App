import os
import base64
from flask import Flask, request, render_template, jsonify, session, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dateutil.relativedelta import relativedelta
from functools import wraps

# --- Configuração do App e do Banco de Dados ---

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "acpamsal_seguro_2025_chave")

# Configuração do banco: SQLite local ou PostgreSQL (Railway)
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")
else:
    DATABASE_URL = "sqlite:///acpamsal.db"

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

MENSALIDADE_BASE = 10.0 

# --- MODELOS (Classes de Banco de Dados) ---

class Associado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    matricula = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    rua = db.Column(db.String(100))
    numero = db.Column(db.String(10))
    bairro = db.Column(db.String(50))
    rg = db.Column(db.String(20))
    cpf = db.Column(db.String(14), unique=True)
    email_assoc = db.Column(db.String(100), unique=True) 
    placa = db.Column(db.String(10))
    cor = db.Column(db.String(30))
    ano = db.Column(db.Integer)
    renavam = db.Column(db.String(20))
    data_cadastro = db.Column(db.String(19), default=lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S')) 
    foto_base64 = db.Column(db.Text) 

class Mensalidade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey('associado.id'), nullable=False)
    mes_ano = db.Column(db.String(7), nullable=False) 
    valor = db.Column(db.Float, default=MENSALIDADE_BASE)

    __table_args__ = (db.UniqueConstraint('associado_id', 'mes_ano', name='_associado_mes_ano_uc'),)

class Despesa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data = db.Column(db.String(10), nullable=False) 

class UsuarioPublico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    senha = db.Column(db.String(100), nullable=False)
    
class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    logo_url = db.Column(db.Text)  
    nome_assoc = db.Column(db.String(255), default="Associação dos Condutores Profissionais Autônomos Motofrestistas, Motociclistas, Mototaxistas e Motoboys do Município de Salinópolis-Pa - ACPAMSAL")
    endereco = db.Column(db.Text, default="Rua Pedro de Alcântara Barros nº 20, bairro São Tomé - Cep 68.721-000 - Salinópolis-Pa")
    telefone = db.Column(db.String(20), default="(91) 98212-2175")
    email = db.Column(db.String(100), default="acpamsal@gmail.com")
    mensalidade_valor = db.Column(db.Float, default=MENSALIDADE_BASE) 
    cnpj = db.Column(db.String(18), default="39.242.691/0001-75") 
    login_bg_url = db.Column(db.Text) 

# --- Configuração do Contexto do Template ---
@app.context_processor
def inject_global_vars():
    cfg = Configuracao.query.first()
    if not cfg:
        cfg = Configuracao()
    
    # Rodapé Padrão e Dados de Contato
    footer_info = {
        'endereco_completo': cfg.endereco,
        'contato': f"Whatsapp {cfg.telefone} / E-mail: {cfg.email}",
        'social': "Visite Nossas Ações Sociais e seja uma Patrocinador bio.site/JuniorAraujo"
    }

    return dict(datetime=datetime, config=cfg, footer_info=footer_info)

# --- UTILS (Funções Auxiliares e Decorators) ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_type') != 'admin':
            flash('Acesso restrito. Faça login como administrador.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def associado_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_type') != 'associado' or not session.get('logged_in'):
            flash('Acesso restrito. Faça login como associado.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def public_access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Acesso restrito. Faça login para usar a consulta pública.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def data_inicial_mensalidades():
    """Retorna '2025-11' como data inicial padrão para cobranças."""
    return "2025-11"

def calcular_status_e_divida(associado):
    """Calcula o status e a dívida de um associado com base nas mensalidades pagas."""
    
    DATA_INICIO_COBRANCA = data_inicial_mensalidades() 
    data_fim_referencia = datetime.now().replace(day=1)
    
    try:
        # Usa a data de cadastro ou a data inicial de cobrança, o que for maior.
        data_cadastro = datetime.strptime(associado.data_cadastro, '%Y-%m-%d %H:%M:%S').replace(day=1)
    except Exception:
        data_cadastro = datetime.strptime(DATA_INICIO_COBRANCA, '%Y-%m').replace(day=1)

    data_inicio_cobranca = max(data_cadastro, datetime.strptime(DATA_INICIO_COBRANCA, '%Y-%m').replace(day=1))
    
    mensalidades_pagas = [m.mes_ano for m in Mensalidade.query.filter_by(associado_id=associado.id).all()]
    
    meses_devidos = []
    meses_em_atraso_real = 0
    current_date = data_inicio_cobranca
    
    while current_date <= data_fim_referencia:
        ano_mes_str = current_date.strftime('%Y-%m')
        
        if ano_mes_str not in mensalidades_pagas:
            meses_devidos.append(current_date)
            
            # Conta apenas os meses ANTERIORES ao mês atual como atraso real
            if current_date < data_fim_referencia:
                meses_em_atraso_real += 1
            
        current_date += relativedelta(months=1)
        
    cfg = Configuracao.query.first()
    valor_mensalidade = cfg.mensalidade_valor if cfg else MENSALIDADE_BASE
    
    valor_divida = len(meses_devidos) * valor_mensalidade

    if meses_em_atraso_real == 0:
        status = "Ativo (Em Dia)"
    elif 1 <= meses_em_atraso_real <= 2:
        status = f"Inativo (Débito: {meses_em_atraso_real} M.)"
    else:
        status = f"Desligado (3+ Meses: {meses_em_atraso_real} M.)"
        
    return status, len(meses_devidos), valor_divida, meses_devidos

def handle_foto_upload(form_file):
    """Processa o upload de arquivo e retorna a string Base64."""
    if form_file and form_file.filename:
        file_bytes = form_file.read()
        base64_encoded_data = base64.b64encode(file_bytes)
        base64_string = base64_encoded_data.decode('utf-8')
        mime_type = "image/jpeg" 
        if form_file.filename.endswith(".png"):
            mime_type = "image/png"
            
        return f"data:{mime_type};base64,{base64_string}"
    return None

# --- ROTAS DE AUTENTICAÇÃO E DASHBOARD ---

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario'] 
        senha = request.form['senha']    

        # 1. Login Admin
        if usuario == 'acpamsal@gmail.com' and senha == '230808Deus#':
            session['logged_in'] = True
            session['user_type'] = 'admin'
            return redirect(url_for('dashboard'))
        
        # 2. Login de Associado (Usuário: Email, Senha: Matrícula)
        associado_user = Associado.query.filter_by(email_assoc=usuario).first()
        if associado_user and associado_user.matricula.lower() == senha.lower():
            session['logged_in'] = True
            session['user_type'] = 'associado'
            session['associado_id'] = associado_user.id
            flash(f'Bem-vindo(a), {associado_user.nome.split()[0]}!', 'success')
            return redirect(url_for('perfil_associado'))

        # 3. Login Público (consulta)
        user_pub = UsuarioPublico.query.filter_by(usuario=usuario, senha=senha).first()
        if user_pub:
            session['logged_in'] = True
            session['user_type'] = 'public'
            return redirect(url_for('consulta_publica')) 
        
        flash('Credenciais inválidas', 'error')
        
    cfg = Configuracao.query.first()
    nome = cfg.nome_assoc if cfg else "ACPAMSAL"
    return render_template('login.html', instituicao=nome, config=cfg) 

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
        
    user_type = session['user_type']
    
    if user_type == 'admin':
        total_associados = Associado.query.count()
        total_despesas = db.session.query(db.func.sum(Despesa.valor)).scalar() or 0.0
        
        total_divida = 0.0
        associados = Associado.query.all()
        for assoc in associados:
            _, _, divida, _ = calcular_status_e_divida(assoc)
            total_divida += divida
            
        total_mensalidades = db.session.query(db.func.sum(Mensalidade.valor)).scalar() or 0.0
        saldo = total_mensalidades - total_despesas
        
        return render_template('admin_dashboard.html', 
                               user_type=user_type, 
                               total_associados=total_associados,
                               total_despesas=total_despesas,
                               total_divida=total_divida,
                               total_mensalidades=total_mensalidades,
                               saldo=saldo)
    
    if user_type == 'public':
        return redirect(url_for('consulta_publica'))
    
    if user_type == 'associado':
        return redirect(url_for('perfil_associado'))
        
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ROTAS DO ASSOCIADO ---

@app.route('/associado/perfil', methods=['GET', 'POST'])
@associado_required
def perfil_associado():
    associado_id = session.get('associado_id')
    associado = Associado.query.get_or_404(associado_id)
    
    status, meses_devidos_count, divida, meses_devidos_lista = calcular_status_e_divida(associado)
    
    if request.method == 'POST':
        try:
            nova_foto = request.files.get('foto')
            
            if nova_foto and nova_foto.filename:
                associado.foto_base64 = handle_foto_upload(nova_foto)
                flash("Foto atualizada com sucesso!", 'success')
            elif 'remover_foto' in request.form:
                associado.foto_base64 = None
                flash("Foto removida com sucesso.", 'success')
            
            db.session.commit()
            return redirect(url_for('perfil_associado'))
            
        except Exception as e:
            flash(f"Erro ao atualizar foto: {e}", 'error')

    contexto = {
        'associado': associado,
        'status': status,
        'divida': divida,
        'meses_devidos_count': meses_devidos_count,
        'meses_devidos_lista': meses_devidos_lista
    }
    return render_template('perfil_associado.html', **contexto)


# --- ROTAS DE CONSULTA PÚBLICA ---

@app.route('/consulta', methods=['GET', 'POST'])
@public_access_required
def consulta_publica():
    associado = None
    termo_busca = None
    
    if request.method == 'POST':
        termo_busca = request.form.get('busca').strip().upper() 
        
        search = f"%{termo_busca}%"
        
        associado = Associado.query.filter(
            (Associado.nome.ilike(search)) |
            (Associado.rg.ilike(search)) |
            (Associado.cpf.ilike(search)) |
            (Associado.placa.ilike(search)) |
            (Associado.matricula.ilike(termo_busca)) 
        ).first()

        if associado:
            status, _, _, _ = calcular_status_e_divida(associado)
            
            public_data = {
                'nome': associado.nome,
                'matricula': associado.matricula,
                'placa': associado.placa,
                'status': status,
                'foto_base64': associado.foto_base64
                # data_cadastro excluída
            }
            flash("Associado encontrado!", 'success')
            return render_template('consulta_publica.html', associado=public_data, termo_busca=termo_busca)
        else:
            flash("Associado não encontrado.", 'error')

    return render_template('consulta_publica.html', associado=associado, termo_busca=termo_busca)


# --- ROTAS DE GERENCIAMENTO DE ASSOCIADOS (ADMIN) ---

@app.route('/admin/associados')
@login_required
def gerenciar_associados_web():
    associados_db = Associado.query.all()
    associados_com_status = []
    
    for assoc in associados_db:
        status, _, divida, _ = calcular_status_e_divida(assoc)
        
        associados_com_status.append({
            'id': assoc.id,
            'matricula': assoc.matricula,
            'nome': assoc.nome,
            'email_assoc': assoc.email_assoc,
            'placa': assoc.placa,
            'status': status,
            'divida': f"R$ {divida:.2f}"
        })
        
    return render_template('associados.html', associados=associados_com_status)

@app.route('/admin/associados/cadastrar', methods=['GET', 'POST'])
@login_required
def cadastrar_associado():
    if request.method == 'POST':
        try:
            matricula = request.form['matricula'].upper().strip()
            email_assoc = request.form['email_assoc'].lower().strip()
            
            if Associado.query.filter_by(matricula=matricula).first():
                flash(f"Matrícula {matricula} já existe!", 'error')
                return render_template('cadastro_associado.html', data=request.form)
                
            if Associado.query.filter_by(email_assoc=email_assoc).first():
                flash(f"E-mail {email_assoc} já está sendo usado para login!", 'error')
                return render_template('cadastro_associado.html', data=request.form)

            foto_data = handle_foto_upload(request.files.get('foto'))
            
            novo = Associado(
                matricula=matricula,
                nome=request.form['nome'],
                rua=request.form['rua'],
                numero=request.form['numero'],
                bairro=request.form['bairro'],
                rg=request.form['rg'],
                cpf=request.form['cpf'],
                email_assoc=email_assoc, 
                placa=request.form['placa'].upper(),
                cor=request.form['cor'],
                ano=request.form['ano'],
                renavam=request.form['renavam'],
                foto_base64=foto_data
            )
            db.session.add(novo)
            db.session.commit()
            flash("Associado cadastrado com sucesso! Lembre-o que a senha inicial é a MATRÍCULA.", 'success')
            return redirect(url_for('gerenciar_associados_web'))
        except Exception as e:
            flash(f"Erro ao cadastrar: {e}", 'error')
            return render_template('cadastro_associado.html', data=request.form) 

    return render_template('cadastro_associado.html', data={})

@app.route('/admin/associados/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_associado(id):
    associado = Associado.query.get_or_404(id)

    if request.method == 'POST':
        try:
            nova_foto = request.files.get('foto')
            if nova_foto and nova_foto.filename:
                associado.foto_base64 = handle_foto_upload(nova_foto)
            elif 'remover_foto' in request.form:
                associado.foto_base64 = None
                
            associado.nome = request.form['nome']
            associado.rua = request.form['rua']
            associado.numero = request.form['numero']
            associado.bairro = request.form['bairro']
            associado.rg = request.form['rg']
            associado.cpf = request.form['cpf']
            associado.email_assoc = request.form['email_assoc'].lower().strip() 
            associado.placa = request.form['placa'].upper()
            associado.cor = request.form['cor']
            associado.ano = request.form['ano']
            associado.renavam = request.form['renavam']
            
            db.session.commit()
            flash("Associado atualizado com sucesso!", 'success')
            return redirect(url_for('gerenciar_associados_web'))
        except Exception as e:
            flash(f"Erro ao editar: {e}", 'error')
    
    return render_template('editar_associado.html', associado=associado)

@app.route('/admin/associados/remover/<int:id>', methods=['POST'])
@login_required
def remover_associado(id):
    associado = Associado.query.get_or_404(id)
    try:
        Mensalidade.query.filter_by(associado_id=id).delete()
        db.session.delete(associado)
        db.session.commit()
        flash(f"Associado {associado.nome} (Mat.: {associado.matricula}) e seus pagamentos foram removidos.", 'success')
    except Exception as e:
        flash(f"Erro ao remover associado: {e}", 'error')
        
    return redirect(url_for('gerenciar_associados_web'))


# --- ROTAS DE GESTÃO DE USUÁRIOS PÚBLICOS (ADMIN) ---

@app.route('/admin/usuarios-publicos', methods=['GET'])
@login_required
def gerenciar_usuarios_publicos():
    usuarios = UsuarioPublico.query.all()
    return render_template('gerenciar_usuarios_publicos.html', usuarios=usuarios)

@app.route('/admin/usuarios-publicos/cadastrar', methods=['GET', 'POST'])
@login_required
def cadastrar_usuario_publico():
    if request.method == 'POST':
        usuario = request.form['usuario']
        senha = request.form['senha']
        
        if UsuarioPublico.query.filter_by(usuario=usuario).first():
            flash('Usuário já existe. Escolha outro nome.', 'error')
            return redirect(url_for('cadastrar_usuario_publico'))
            
        novo_usuario = UsuarioPublico(usuario=usuario, senha=senha)
        db.session.add(novo_usuario)
        db.session.commit()
        flash(f'Usuário público "{usuario}" criado com sucesso.', 'success')
        return redirect(url_for('gerenciar_usuarios_publicos'))
        
    return render_template('cadastro_usuario_publico.html')

@app.route('/admin/usuarios-publicos/remover/<int:id>', methods=['POST'])
@login_required
def remover_usuario_publico(id):
    usuario = UsuarioPublico.query.get_or_404(id)
    try:
        db.session.delete(usuario)
        db.session.commit()
        flash(f'Usuário "{usuario.usuario}" removido.', 'success')
    except Exception as e:
        flash(f'Erro ao remover usuário: {e}', 'error')
    
    return redirect(url_for('gerenciar_usuarios_publicos'))


# --- ROTAS FINANCEIRAS (ADMIN) ---

@app.route('/admin/mensalidades', methods=['GET', 'POST'])
@login_required
def gerenciar_mensalidades_web():
    if request.method == 'POST':
        associado_id = request.form.get('associado_id')
        mes_ano = request.form.get('mes_ano')
        acao = request.form.get('acao') 
        
        if not associado_id or not mes_ano or not acao:
            flash("Dados de pagamento incompletos.", 'error')
            return redirect(url_for('gerenciar_mensalidades_web'))

        assoc_id_int = int(associado_id)
        
        cfg = Configuracao.query.first()
        valor = cfg.mensalidade_valor if cfg else MENSALIDADE_BASE

        if acao == 'registrar':
            existe = Mensalidade.query.filter_by(associado_id=assoc_id_int, mes_ano=mes_ano).first()
            if not existe:
                nova_mensalidade = Mensalidade(associado_id=assoc_id_int, mes_ano=mes_ano, valor=valor)
                db.session.add(nova_mensalidade)
                db.session.commit()
                flash(f"Pagamento de {mes_ano} registrado.", 'success')
            else:
                 flash(f"Pagamento de {mes_ano} já está registrado.", 'warning')

        elif acao == 'remover':
            mensalidade = Mensalidade.query.filter_by(associado_id=assoc_id_int, mes_ano=mes_ano).first()
            if mensalidade:
                db.session.delete(mensalidade)
                db.session.commit()
                flash(f"Pagamento de {mes_ano} removido.", 'success')
            else:
                flash("Pagamento não encontrado.", 'error')
        
        return redirect(url_for('gerenciar_mensalidades_web'))

    # Rota GET
    associados_db = Associado.query.all()
    associados_financeiro = []
    
    for assoc in associados_db:
        status, total_devido, divida, meses_devidos_lista = calcular_status_e_divida(assoc)
        meses_devidos_str = [m.strftime('%Y-%m') for m in meses_devidos_lista]
        
        associados_financeiro.append({
            'id': assoc.id,
            'matricula': assoc.matricula,
            'nome': assoc.nome,
            'status': status,
            'divida': f"R$ {divida:.2f}",
            'total_devido': total_devido,
            'meses_devidos': meses_devidos_str
        })
        
    cfg = Configuracao.query.first()
    mensalidade_base = cfg.mensalidade_valor if cfg else MENSALIDADE_BASE
    
    # Prepara a lista de meses desde o início da cobrança até o mês atual
    DATA_INICIO_COBRANCA = data_inicial_mensalidades()
    meses_disponiveis = []
    current_date = datetime.strptime(DATA_INICIO_COBRANCA, '%Y-%m').replace(day=1)
    data_fim_referencia = datetime.now().replace(day=1)
    while current_date <= data_fim_referencia:
        meses_disponiveis.append(current_date.strftime('%Y-%m'))
        current_date += relativedelta(months=1)
        
    return render_template('mensalidades.html', 
                           associados=associados_financeiro, 
                           mensalidade_base=mensalidade_base,
                           meses_disponiveis=meses_disponiveis)

@app.route('/admin/despesas', methods=['GET', 'POST'])
@login_required
def gerenciar_despesas_web():
    if request.method == 'POST':
        try:
            descricao = request.form['descricao'].strip()
            valor = float(request.form['valor'])
            data = request.form['data']
            
            nova_despesa = Despesa(descricao=descricao, valor=valor, data=data)
            db.session.add(nova_despesa)
            db.session.commit()
            flash("Despesa registrada com sucesso!", 'success')
        except Exception as e:
            flash(f"Erro ao registrar despesa: {e}", 'error')
        
        return redirect(url_for('gerenciar_despesas_web'))

    despesas = Despesa.query.order_by(Despesa.data.desc()).all()
    total_despesa = db.session.query(db.func.sum(Despesa.valor)).scalar() or 0.0
    
    return render_template('despesas.html', despesas=despesas, total_despesa=total_despesa, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/admin/despesas/remover/<int:id>', methods=['POST'])
@login_required
def remover_despesa_web(id):
    despesa = Despesa.query.get(id)
    if despesa:
        db.session.delete(despesa)
        db.session.commit()
        flash("Despesa removida com sucesso.", 'success')
    else:
        flash("Despesa não encontrada.", 'error')
        
    return redirect(url_for('gerenciar_despesas_web'))


# --- ROTAS DE RELATÓRIO (ADMIN) ---

@app.route('/admin/relatorios')
@login_required
def relatorios_web():
    associados = Associado.query.order_by(Associado.nome).all()
    
    relatorio = []
    total_divida_geral = 0
    total_pago_geral = db.session.query(db.func.sum(Mensalidade.valor)).scalar() or 0.0
    
    for assoc in associados:
        status, meses_devidos_count, divida, _ = calcular_status_e_divida(assoc)
        total_divida_geral += divida
        
        relatorio.append({
            'matricula': assoc.matricula,
            'nome': assoc.nome,
            'placa': assoc.placa,
            'status': status,
            'divida': divida,
            'meses_devidos': meses_devidos_count,
            'pagamentos_feitos': Mensalidade.query.filter_by(associado_id=assoc.id).count()
        })
        
    return render_template('relatorios.html', 
                           relatorio=relatorio,
                           total_divida_geral=total_divida_geral,
                           total_pago_geral=total_pago_geral,
                           data_geracao=datetime.now().strftime('%d/%m/%Y %H:%M'))


# --- ROTAS DE CONFIGURAÇÃO (ADMIN) ---

@app.route('/admin/config', methods=['GET', 'POST'])
@login_required
def config_web():
    cfg = Configuracao.query.first()
    if not cfg:
        cfg = Configuracao()
        db.session.add(cfg)
        db.session.commit()
        
    if request.method == 'POST':
        try:
            # Lida com o upload da logo
            nova_logo = request.files.get('logo_upload')
            if nova_logo and nova_logo.filename:
                cfg.logo_url = handle_foto_upload(nova_logo)
            elif 'remover_logo' in request.form:
                 cfg.logo_url = None
                 
            # Lida com o upload da imagem de fundo do login
            nova_login_bg = request.files.get('login_bg_upload')
            if nova_login_bg and nova_login_bg.filename:
                cfg.login_bg_url = handle_foto_upload(nova_login_bg)
            elif 'remover_login_bg' in request.form:
                 cfg.login_bg_url = None

            # Salva os dados de texto
            cfg.nome_assoc = request.form['nome_assoc']
            cfg.endereco = request.form['endereco']
            cfg.telefone = request.form['telefone']
            cfg.email = request.form['email']
            cfg.mensalidade_valor = float(request.form['mensalidade_valor'])
            cfg.cnpj = request.form['cnpj']
            
            db.session.commit()
            flash("Configurações atualizadas com sucesso!", 'success')
        
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao salvar configurações: {e}", 'error')

        return redirect(url_for('config_web'))

    return render_template('config.html', config=cfg)

# --- EXECUÇÃO ---

with app.app_context():

if __name__ == '__main__':
    app.run(debug=True)

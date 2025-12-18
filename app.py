import os, uuid
from flask import Flask, render_template, redirect, url_for, session, request, flash, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
from io import BytesIO
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Image as RLImage
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "acpamsal_gestao_2026_top_secret"

# --- CONFIGURAÇÃO DE AMBIENTE ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Uso de SQLite (Importante: No Render Free, os dados resetam a cada deploy/restart)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'acpamsal_gestao.db')
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static/uploads')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Garante que a pasta de uploads exista
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

# --- MODELOS DE DADOS ACPAMSAL ---
class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_associacao = db.Column(db.String(500), default="Associação dos Condutores Profissionais Autônomos Motofretistas, Motociclistas, Mototaxistas e Motoboys do Município de Salinópolis - ACPAMSAL")
    cnpj = db.Column(db.String(25), default="39.242.691/0001-75")
    email_assoc = db.Column(db.String(100), default="acpamsal@gmail.com")
    telefone_assoc = db.Column(db.String(20), default="(91) 98212-2175")
    endereco_assoc = db.Column(db.String(255), default="Rua Pedro de Alcântara Barros Nº 20, Bairro São Tomé, CEP 68.721-000 - Salinópolis-PA")
    logo_path = db.Column(db.String(255))

class Associado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    foto = db.Column(db.String(255))
    matricula = db.Column(db.String(50), unique=True)
    nome = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    placa = db.Column(db.String(10))
    ponto_nome = db.Column(db.String(100))
    status = db.Column(db.String(20), default="ATIVO") # ATIVO ou DESLIGADO
    mensalidades = db.relationship('Mensalidade', backref='socio', lazy=True, cascade="all, delete-orphan")

class Mensalidade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    socio_id = db.Column(db.Integer, db.ForeignKey('associado.id'))
    mes_ref = db.Column(db.String(10))
    valor = db.Column(db.Float)
    pago = db.Column(db.Boolean, default=False)

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))
    tipo = db.Column(db.String(20)) # admin ou consulta

# --- INJEÇÃO DE GLOBAIS ---
@app.context_processor
def inject_globals():
    conf = Configuracao.query.first()
    return dict(config=conf)

# --- LÓGICA DE NEGÓCIO: BLOQUEIO POR INADIMPLÊNCIA ---
def atualizar_status_socios():
    """Desliga automaticamente sócios com 3 ou mais mensalidades em atraso."""
    socios = Associado.query.all()
    for s in socios:
        pendentes = Mensalidade.query.filter_by(socio_id=s.id, pago=False).count()
        s.status = "DESLIGADO" if pendentes >= 3 else "ATIVO"
    db.session.commit()

# --- ROTAS DE ACESSO ---
@app.route('/')
def index():
    return render_template('index.html') # Consulta Pública de Blitz

@app.route('/login_admin', methods=['GET', 'POST'])
def login_admin():
    if request.method == 'POST':
        # Credenciais conforme sua instrução
        if request.form['user'] == "acpamsal@gmail.com" and request.form['pass'] == "230808Deus#":
            session['admin'] = True
            flash("Autenticação Administrativa Concluída.")
            return redirect(url_for('admin_dashboard'))
        flash("Falha na autenticação.")
    return render_template('login_admin.html')

@app.route('/login_socio', methods=['GET', 'POST'])
def login_socio():
    if request.method == 'POST':
        socio = Associado.query.filter_by(email=request.form['email'], matricula=request.form['senha']).first()
        if socio:
            session['socio_id'] = socio.id
            return redirect(url_for('perfil_socio'))
        flash("Dados de acesso inválidos.")
    return render_template('login_socio.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- CONSULTA PÚBLICA (FISCALIZAÇÃO EM BLITZ) ---
@app.route('/consulta_publica', methods=['POST'])
def consulta_publica():
    atualizar_status_socios()
    t = request.form.get('busca', '').upper()
    # Apenas sócios ATIVOS aparecem como regulares na consulta pública
    res = Associado.query.filter(
        (Associado.status == "ATIVO"),
        (Associado.matricula == t) | (Associado.nome.like(f"%{t}%")) | (Associado.placa == t)
    ).all()
    return render_template('index.html', resultados=res, busca_realizada=True)

# --- ÁREA ADMINISTRATIVA ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'): return redirect(url_for('login_admin'))
    return render_template('admin_associados.html', associados=Associado.query.all())

@app.route('/admin/cadastrar', methods=['GET', 'POST'])
def admin_cadastrar():
    if not session.get('admin'): return redirect(url_for('login_admin'))
    if request.method == 'POST':
        foto = request.files.get('foto')
        filename = secure_filename(f"{uuid.uuid4().hex}.jpg") if foto else None
        if foto: 
            foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        novo = Associado(
            foto=filename, 
            matricula=request.form['matricula'], 
            nome=request.form['nome'].upper(),
            email=request.form['email'], 
            placa=request.form['placa'].upper(),
            ponto_nome=request.form['ponto']
        )
        db.session.add(novo)
        db.session.commit()
        flash("Sócio cadastrado com sucesso!")
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_cadastrar.html')

@app.route('/admin/mensalidades', methods=['GET', 'POST'])
def admin_mensalidades():
    if not session.get('admin'): return redirect(url_for('login_admin'))
    if request.method == 'POST':
        mes, valor = request.form['mes'], float(request.form['valor'])
        for s in Associado.query.all():
            if not Mensalidade.query.filter_by(socio_id=s.id, mes_ref=mes).first():
                db.session.add(Mensalidade(socio_id=s.id, mes_ref=mes, valor=valor))
        db.session.commit()
        atualizar_status_socios()
        flash(f"Mensalidades de {mes} geradas para todos.")
    return render_template('admin_mensalidades.html', mensalidades=Mensalidade.query.all())

@app.route('/admin/baixar_pagamento/<int:id>')
def baixar_pagamento(id):
    if not session.get('admin'): return redirect(url_for('login_admin'))
    m = Mensalidade.query.get_or_404(id)
    m.pago = True
    db.session.commit()
    atualizar_status_socios()
    flash(f"Pagamento confirmado para {m.socio.nome}.")
    return redirect(url_for('admin_mensalidades'))

@app.route('/admin/config', methods=['GET', 'POST'])
def admin_config():
    if not session.get('admin'): return redirect(url_for('login_admin'))
    conf = Configuracao.query.first()
    if request.method == 'POST':
        conf.nome_associacao = request.form['nome_entidade']
        conf.cnpj = request.form['cnpj']
        conf.email_assoc = request.form['email']
        conf.telefone_assoc = request.form['telefone']
        conf.endereco_assoc = request.form['endereco']
        logo = request.files.get('logo')
        if logo:
            fn = secure_filename(logo.filename)
            logo.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            conf.logo_path = fn
        db.session.commit()
        flash("Configurações da Associação Atualizadas.")
    return render_template('admin_config.html', config=conf)

# --- ÁREA DO SÓCIO ---
@app.route('/perfil')
def perfil_socio():
    s_id = session.get('socio_id')
    if not s_id: return redirect(url_for('login_socio'))
    return render_template('perfil_socio.html', socio=Associado.query.get(s_id))

# --- DOCUMENTAÇÃO PDF (CRACHÁ E RELATÓRIO) ---
@app.route('/gerar_cracha/<int:id>')
def gerar_cracha(id):
    socio = Associado.query.get_or_404(id)
    conf = Configuracao.query.first()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(54*mm, 86*mm))
    
    # Fundo e Borda Estilo Cartão
    c.setFillColor(colors.HexColor("#1a1a1a")); c.rect(0, 0, 54*mm, 86*mm, fill=1)
    c.setFillColor(colors.white); c.rect(2*mm, 2*mm, 50*mm, 82*mm, fill=1)
    
    if socio.foto:
        img_p = os.path.join(app.config['UPLOAD_FOLDER'], socio.foto)
        if os.path.exists(img_p):
            c.saveState()
            path = c.beginPath(); path.circle(27*mm, 60*mm, 15*mm)
            c.clipPath(path, stroke=1)
            c.drawImage(img_p, 12*mm, 45*mm, 30*mm, 30*mm)
            c.restoreState()

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9); c.drawCentredString(27*mm, 40*mm, socio.nome[:20].upper())
    c.setFont("Helvetica-Bold", 7); c.drawCentredString(27*mm, 35*mm, f"MATRÍCULA: {socio.matricula}")
    c.setFont("Helvetica", 7); c.drawCentredString(27*mm, 31*mm, f"PLACA: {socio.placa}")
    
    # Rodapé Institucional
    c.setFillColor(colors.HexColor("#D4AF37")); c.rect(2*mm, 2*mm, 50*mm, 12*mm, fill=1)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 4)
    c.drawCentredString(27*mm, 10*mm, "IDENTIFICAÇÃO DE ASSOCIADO")
    c.setFont("Helvetica", 3); c.drawCentredString(27*mm, 7*mm, conf.nome_associacao[:60])
    
    c.showPage(); c.save(); buffer.seek(0)
    return make_response(buffer.getvalue(), 200, {'Content-Type': 'application/pdf'})

@app.route('/admin/relatorio/pdf')
def gerar_relatorio_pdf():
    conf = Configuracao.query.first()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    
    estilo_titulo = ParagraphStyle('T', alignment=1, fontSize=12, leading=14, fontName='Helvetica-Bold', spaceAfter=10)
    estilo_normal = ParagraphStyle('N', alignment=0, fontSize=9, fontName='Helvetica')
    
    elements = []
    if conf.logo_path:
        logo_path = os.path.join(app.config['UPLOAD_FOLDER'], conf.logo_path)
        if os.path.exists(logo_path):
            logo_img = RLImage(logo_path, 30*mm, 30*mm)
            logo_img.hAlign = 'CENTER'; elements.append(logo_img); elements.append(Spacer(1, 10))
    
    elements.append(Paragraph(conf.nome_associacao, estilo_titulo))
    elements.append(Paragraph(f"CNPJ: {conf.cnpj}", estilo_titulo))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<b>LISTAGEM OFICIAL DE ASSOCIADOS</b>", estilo_titulo))
    elements.append(Spacer(1, 10))
    
    for s in Associado.query.all():
        elements.append(Paragraph(f"MAT: {s.matricula} | NOME: {s.nome} | PLACA: {s.placa} | STATUS: <b>{s.status}</b>", estilo_normal))
        elements.append(Spacer(1, 5))
        
    doc.build(elements); buffer.seek(0)
    return make_response(buffer.getvalue(), 200, {'Content-Type': 'application/pdf'})

# --- SERVIR ARQUIVOS ---
@app.route('/static/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- INICIALIZAÇÃO PARA DEPLOY ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Configuracao.query.first():
            db.session.add(Configuracao())
            db.session.commit()
            
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

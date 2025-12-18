import os
import uuid
from flask import Flask, render_template, redirect, url_for, session, request, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from io import BytesIO

# Bibliotecas para PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

app = Flask(__name__)
app.secret_key = "acpamsal_2026_oficial_seguro"

# --- CONEXÃO INTELIGENTE ---
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///acpamsal_gestao.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/uploads')

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

# --- MODELOS ---
class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_completo = db.Column(db.String(255), default="ACPAMSAL - SALINÓPOLIS")
    cnpj = db.Column(db.String(20), default="39.242.691/0001-75")
    logo_path = db.Column(db.String(255))
    endereco = db.Column(db.String(255))
    whatsapp = db.Column(db.String(20))
    email_contato = db.Column(db.String(100))

class Associado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    foto = db.Column(db.String(255))
    matricula = db.Column(db.String(50), unique=True)
    nome = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    placa = db.Column(db.String(10))
    ponto_nome = db.Column(db.String(100))
    status = db.Column(db.String(20), default="ATIVO")

# --- GERENCIAMENTO DE CONFIGURAÇÃO E LOGO ---
@app.route('/admin/config', methods=['GET', 'POST'])
def admin_config():
    if not session.get('admin'): return redirect(url_for('login_admin'))
    config = Configuracao.query.first() or Configuracao()
    if request.method == 'POST':
        logo = request.files.get('logo')
        if logo:
            filename = "logo_principal.png"
            logo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            config.logo_path = filename
        config.nome_completo = request.form['nome'].upper()
        config.cnpj = request.form['cnpj']
        config.endereco = request.form['endereco']
        config.whatsapp = request.form['whatsapp']
        config.email_contato = request.form['email']
        if not config.id: db.session.add(config)
        db.session.commit()
        flash("Configurações salvas!")
    return render_template('admin_config.html', config=config)

# --- RELATÓRIO PDF COM LOGO E DADOS ---
@app.route('/admin/relatorio/pdf')
def gerar_relatorio_pdf():
    if not session.get('admin'): return redirect(url_for('login_admin'))
    config = Configuracao.query.first() or Configuracao()
    socios = Associado.query.all()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4

    # Desenha Logo no Topo
    if config.logo_path:
        path = os.path.join(app.config['UPLOAD_FOLDER'], config.logo_path)
        if os.path.exists(path):
            c.drawImage(path, (largura/2)-20*mm, altura-35*mm, width=40*mm, preserveAspectRatio=True)

    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(largura/2, altura-45*mm, config.nome_completo)
    c.setFont("Helvetica", 8)
    c.drawString(20*mm, altura-55*mm, f"Relatório de Associados - Total: {len(socios)}")
    
    # Cabeçalho da Tabela
    y = altura-65*mm
    c.line(20*mm, y+2, largura-20*mm, y+2)
    c.drawString(20*mm, y, "MATRÍCULA")
    c.drawString(50*mm, y, "NOME")
    c.drawString(140*mm, y, "STATUS")
    
    y -= 5*mm
    for s in socios:
        c.drawString(20*mm, y, s.matricula)
        c.drawString(50*mm, y, s.nome[:40])
        c.drawString(140*mm, y, s.status)
        y -= 5*mm
    
    # Rodapé
    c.line(20*mm, 20*mm, largura-20*mm, 20*mm)
    c.drawCentredString(largura/2, 15*mm, f"CNPJ: {config.cnpj} | {config.endereco} | {config.whatsapp}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return make_response(buffer.getvalue(), 200, {'Content-Type': 'application/pdf'})

# --- ROTAS DE GESTÃO (CADASTRO/EDIÇÃO/EXCLUSÃO) ---
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
        if foto: foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        novo = Associado(foto=filename, matricula=request.form['matricula'], 
                         nome=request.form['nome'].upper(), email=request.form['email'], 
                         placa=request.form['placa'].upper(), ponto_nome=request.form['ponto'])
        db.session.add(novo)
        db.session.commit()
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_cadastrar.html')

@app.route('/admin/editar/<int:id>', methods=['GET', 'POST'])
def admin_editar(id):
    if not session.get('admin'): return redirect(url_for('login_admin'))
    socio = Associado.query.get_or_404(id)
    if request.method == 'POST':
        foto = request.files.get('foto')
        if foto:
            filename = secure_filename(f"{uuid.uuid4().hex}.jpg")
            foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            socio.foto = filename
        socio.nome, socio.email = request.form['nome'].upper(), request.form['email']
        socio.matricula, socio.placa = request.form['matricula'], request.form['placa'].upper()
        socio.ponto_nome, socio.status = request.form['ponto'], request.form['status']
        db.session.commit()
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_editar.html', socio=socio)

@app.route('/admin/remover/<int:id>')
def admin_remover(id):
    if not session.get('admin'): return redirect(url_for('login_admin'))
    socio = Associado.query.get_or_404(id)
    db.session.delete(socio)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

# --- ROTAS DE LOGIN E AUXILIARES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/login_admin', methods=['GET', 'POST'])
def login_admin():
    if request.method == 'POST':
        if request.form['user'] == "acpamsal@gmail.com" and request.form['pass'] == "230808Deus#":
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
    return render_template('login_admin.html')

@app.route('/login_socio', methods=['GET', 'POST'])
def login_socio():
    if request.method == 'POST':
        socio = Associado.query.filter_by(email=request.form['email'], matricula=request.form['senha']).first()
        if socio:
            session['socio_id'] = socio.id
            return redirect(url_for('perfil_socio'))
    return render_template('login_socio.html')

@app.route('/perfil', methods=['GET', 'POST'])
def perfil_socio():
    s_id = session.get('socio_id')
    if not s_id: return redirect(url_for('login_socio'))
    socio = Associado.query.get(s_id)
    if request.method == 'POST':
        foto = request.files.get('foto')
        if foto:
            filename = secure_filename(f"{uuid.uuid4().hex}.jpg")
            foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            socio.foto = filename
            db.session.commit()
    return render_template('perfil_socio.html', socio=socio)

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('index'))

@app.route('/admin/mensalidades')
def admin_mensalidades(): return "Módulo Financeiro em Breve"

@app.route('/admin/usuarios')
def admin_usuarios(): return "Gestão de Operadores em Breve"

@app.route('/consulta_publica', methods=['POST'])
def consulta_publica():
    termo = request.form.get('busca', '').upper()
    resultados = Associado.query.filter((Associado.nome.like(f"%{termo}%")) | (Associado.matricula == termo)).all()
    return render_template('index.html', resultados=resultados, busca_realizada=True)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)

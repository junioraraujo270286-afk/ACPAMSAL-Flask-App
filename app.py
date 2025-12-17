import os
import uuid
from flask import Flask, request, render_template, jsonify, session, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dateutil.relativedelta import relativedelta
from functools import wraps
from werkzeug.utils import secure_filename

# --- CONFIGURAÇÃO INICIAL ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "acpamsal_2025_premium_key")

# Banco de Dados (Postgres no Render / SQLite local)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///acpamsal.db").replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuração de Uploads (Render Disk)
UPLOAD_PATH = os.environ.get("UPLOAD_PATH", os.path.join(os.getcwd(), "uploads"))
app.config['UPLOAD_FOLDER'] = UPLOAD_PATH
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

if not os.path.exists(UPLOAD_PATH):
    os.makedirs(UPLOAD_PATH)

db = SQLAlchemy(app)

# --- MODELOS ---
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
    foto_perfil = db.Column(db.String(255))
    documentos = db.relationship('Documento', backref='associado', cascade="all, delete-orphan", lazy=True)

class Documento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey('associado.id'), nullable=False)
    caminho = db.Column(db.String(255), nullable=False)
    tipo_doc = db.Column(db.String(50), nullable=False)
    data_upload = db.Column(db.DateTime, default=datetime.utcnow)

class Mensalidade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey('associado.id'), nullable=False)
    mes_ano = db.Column(db.String(7), nullable=False)
    valor = db.Column(db.Float, default=10.0)

class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_assoc = db.Column(db.String(255), default="ACPAMSAL")
    cnpj = db.Column(db.String(18), default="39.242.691/0001-75")
    mensalidade_valor = db.Column(db.Float, default=10.0)
    logo_url = db.Column(db.String(255))

# --- UTILS ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_type') != 'admin':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def handle_upload(form_file):
    if form_file and form_file.filename:
        ext = form_file.filename.rsplit('.', 1)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            filename = f"{uuid.uuid4().hex}.{ext}"
            form_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return filename
    return None

# --- ROTAS ---
@app.route('/uploads/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, s = request.form['usuario'], request.form['senha']
        if u == 'acpamsal@gmail.com' and s == '230808Deus#':
            session.update({'logged_in': True, 'user_type': 'admin'})
            return redirect(url_for('dashboard'))
        # Adicionar lógica de login de associado aqui se necessário
    return render_template('login.html', config=Configuracao.query.first())

@app.route('/dashboard')
@login_required
def dashboard():
    total_assoc = Associado.query.count()
    return render_template('admin_dashboard.html', total_associados=total_assoc)

@app.route('/admin/associados')
@login_required
def gerenciar_associados_web():
    associados = Associado.query.all()
    return render_template('associados.html', associados=associados)

@app.route('/admin/associados/cadastrar', methods=['GET', 'POST'])
@login_required
def cadastrar_associado():
    if request.method == 'POST':
        foto = handle_upload(request.files.get('foto'))
        novo = Associado(
            matricula=request.form['matricula'].upper(),
            nome=request.form['nome'],
            email_assoc=request.form['email_assoc'].lower(),
            cpf=request.form['cpf'],
            placa=request.form['placa'].upper(),
            foto_perfil=foto
        )
        db.session.add(novo)
        db.session.commit()
        flash("Cadastrado com sucesso!", "success")
        return redirect(url_for('gerenciar_associados_web'))
    return render_template('cadastro_associado.html')

@app.route('/admin/config', methods=['GET', 'POST'])
@login_required
def config_web():
    cfg = Configuracao.query.first() or Configuracao()
    if request.method == 'POST':
        cfg.nome_assoc = request.form['nome_assoc']
        db.session.add(cfg)
        db.session.commit()
        flash("Configurações salvas!", "success")
    return render_template('config.html', config=cfg)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

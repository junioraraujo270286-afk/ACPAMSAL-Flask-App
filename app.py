import os
import uuid
from flask import Flask, request, render_template, jsonify, session, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dateutil.relativedelta import relativedelta
from functools import wraps
from werkzeug.utils import secure_filename

# --- Configuração do App e do Banco de Dados ---

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "acpamsal_seguro_2025_chave")

# Configuração do banco: PostgreSQL (Render) ou SQLite local
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///acpamsal.db").replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Configuração de Uploads (Render Disk) ---
UPLOAD_FOLDER = os.environ.get("UPLOAD_PATH", "/var/data/uploads")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

# --- Constantes e Regras ACPAMSAL ---
MENSALIDADE_BASE = 10.0
# Tarifas MOB ACPAMSAL conforme instrução:
# Bandeira 1 (06:00-23:59): R$ 8,00 | Bandeira 2 (00:00-05:59): R$ 10,00 (até 2km)
# Desconto de 10% para PIX CNPJ 39.242.691/0001-75

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
    foto_perfil = db.Column(db.String(255)) # Nome do arquivo no disco
    
    documentos = db.relationship('Documento', backref='associado', cascade="all, delete-orphan", lazy=True)

class Documento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey('associado.id'), nullable=False)
    caminho = db.Column(db.String(255), nullable=False)
    tipo_doc = db.Column(db.String(50), nullable=False) # Ex: 'RG', 'CNH', 'CRLV'
    data_upload = db.Column(db.DateTime, default=datetime.utcnow)

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
    nome_assoc = db.Column(db.String(255), default="ACPAMSAL - Associação dos Condutores de Salinópolis")
    endereco = db.Column(db.Text, default="Rua Pedro de Alcântara Barros Nº 20, Bairro São Tomé - CEP 68.721-000 - Salinópolis-PA")
    telefone = db.Column(db.String(20), default="(91) 98212-2175")
    email = db.Column(db.String(100), default="acpamsal@gmail.com")
    mensalidade_valor = db.Column(db.Float, default=MENSALIDADE_BASE)
    cnpj = db.Column(db.String(18), default="39.242.691/0001-75")
    login_bg_url = db.Column(db.Text)

# --- UTILS ---

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def handle_upload(form_file):
    if form_file and form_file.filename and allowed_file(form_file.filename):
        ext = form_file.filename.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        form_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return filename
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_type') != 'admin':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROTAS DE ARQUIVOS ---

@app.route('/uploads/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- ROTAS PRINCIPAIS (Login/Dash) ---

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
        
        assoc = Associado.query.filter_by(email_assoc=u).first()
        if assoc and assoc.matricula.lower() == s.lower():
            session.update({'logged_in': True, 'user_type': 'associado', 'associado_id': assoc.id})
            return redirect(url_for('perfil_associado'))
            
        flash('Credenciais inválidas', 'error')
    return render_template('login.html', config=Configuracao.query.first())

@app.route('/dashboard')
@login_required
def dashboard():
    total_assoc = Associado.query.count()
    return render_template('admin_dashboard.html', total_associados=total_assoc)

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

@app.route('/admin/associados/documentos/<int:id>', methods=['GET', 'POST'])
@login_required
def gerenciar_documentos(id):
    assoc = Associado.query.get_or_404(id)
    if request.method == 'POST':
        file = request.files.get('arquivo')
        tipo = request.form.get('tipo_doc')
        nome_arquivo = handle_upload(file)
        if nome_arquivo:
            novo_doc = Documento(associado_id=id, caminho=nome_arquivo, tipo_doc=tipo)
            db.session.add(novo_doc)
            db.session.commit()
            flash("Documento salvo!", "success")
    return render_template('gerenciar_documentos.html', associado=assoc)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

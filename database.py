from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# ----------------------------------------------------
# 1. CONFIGURAÇÃO DO BANCO DE DADOS
# ----------------------------------------------------

db = SQLAlchemy()

def init_db(app):
    """Inicializa o banco de dados e cria as tabelas se não existirem."""
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///acpamsal.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        _setup_default_configs() # Chama a função de configuração

def _setup_default_configs():
    """Configurações iniciais do sistema (Mensalidade e Data de Início)."""
    
    # 1. Configuração da Mensalidade Base
    mensalidade_config = Configuracao.query.filter_by(chave='mensalidade_base').first()
    if not mensalidade_config:
        # Definindo a mensalidade base conforme solicitado (R$ 10,00)
        default_mensalidade = Configuracao(chave='mensalidade_base', valor='10.00')
        db.session.add(default_mensalidade)
        
    # 2. Configuração da Data de Início da Cobrança
    data_inicio_config = Configuracao.query.filter_by(chave='data_inicio_cobranca').first()
    if not data_inicio_config:
        # Definindo a data de início da cobrança conforme solicitado (05/11/2025)
        default_data_inicio = Configuracao(chave='data_inicio_cobranca', valor='2025-11-05')
        db.session.add(default_data_inicio)
        
    db.session.commit()

# ----------------------------------------------------
# 2. DEFINIÇÃO DOS MODELOS
# ----------------------------------------------------

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    senha = db.Column(db.String(255), nullable=False) # Armazena hash (admin) ou texto simples (publico)
    tipo = db.Column(db.String(20), default='publico') # 'admin' ou 'publico'

class Associado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    matricula = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=True)
    rg = db.Column(db.String(20), nullable=True)
    bairro = db.Column(db.String(100), nullable=True)
    rua = db.Column(db.String(100), nullable=True)
    numero = db.Column(db.String(20), nullable=True)
    placa = db.Column(db.String(10), unique=True, nullable=False)
    cor = db.Column(db.String(50), nullable=True)
    ano = db.Column(db.String(4), nullable=True)
    renavam = db.Column(db.String(20), nullable=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    pagamentos = db.relationship('Pagamento', backref='associado', lazy=True, cascade="all, delete-orphan")

class Pagamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey('associado.id', ondelete='CASCADE'), nullable=False)
    mes_referencia = db.Column(db.Date, nullable=False) # Armazena o 1º dia do mês
    valor_pago = db.Column(db.Float, nullable=False)
    data_registro = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Chave única para evitar pagamentos duplicados para o mesmo associado no mesmo mês
    __table_args__ = (db.UniqueConstraint('associado_id', 'mes_referencia', name='_associado_mes_uc'),)

class Despesa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data = db.Column(db.Date, default=datetime.utcnow)
    categoria = db.Column(db.String(50), default='Geral')

class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(50), unique=True, nullable=False)
    valor = db.Column(db.String(255), nullable=False)

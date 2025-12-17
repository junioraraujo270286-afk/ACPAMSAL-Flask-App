from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

# 1. Define o objeto 'db' globalmente.
db = SQLAlchemy()

# 2. Função para inicializar o db com o aplicativo Flask
def init_db(app):
    """Inicializa o objeto SQLAlchemy com o app Flask e cria as tabelas."""
    db.init_app(app)
    # Abre o contexto da aplicação para garantir que o SQLAlchemy possa criar as tabelas
    with app.app_context():

# ----------------------------------------------------------------------
# Definição dos Modelos (Classes)
# ----------------------------------------------------------------------

# Modelo para Usuários/Administradores
class Usuario(db.Model):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(128), nullable=False) # Armazenar hash da senha
    ativo = db.Column(db.Boolean, default=True)

# Modelo para Associados
class Associado(db.Model):
    __tablename__ = 'associado'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=True)
    telefone = db.Column(db.String(20), nullable=True)
    data_adesao = db.Column(db.Date, default=func.current_date())
    ativo = db.Column(db.Boolean, default=True)
    
    # Relacionamento com Pagamentos
    pagamentos = db.relationship('Pagamento', backref='associado', lazy=True)

# Modelo para Pagamentos (Mensalidades ou Outros)
class Pagamento(db.Model):
    __tablename__ = 'pagamento'
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey('associado.id'), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data_pagamento = db.Column(db.Date, default=func.current_date())
    referencia_mes = db.Column(db.String(7), nullable=False) # Ex: YYYY-MM
    tipo = db.Column(db.String(50), default='Mensalidade') # Ex: Mensalidade, Taxa, Doação

# Modelo para Despesas
class Despesa(db.Model):
    __tablename__ = 'despesa'
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(255), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data_despesa = db.Column(db.Date, default=func.current_date())
    categoria = db.Column(db.String(100), nullable=True) # Ex: Aluguel, Material, Serviço

# Modelo para Configurações Gerais
class Configuracao(db.Model):
    __tablename__ = 'configuracao'
    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(50), unique=True, nullable=False) # Ex: taxa_mensal
    valor = db.Column(db.String(255), nullable=False) # Ex: 50.00
    ultima_atualizacao = db.Column(db.DateTime, default=func.now(), onupdate=func.now())

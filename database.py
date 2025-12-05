# database.py

from flask_sqlalchemy import SQLAlchemy

# 1. DEFINE o objeto db (não importa!)
db = SQLAlchemy()

# 2. Função para inicializar o db com o aplicativo Flask
def init_db(app):
    db.init_app(app)
    # Garante que as tabelas sejam criadas ao inicializar
    with app.app_context():
        db.create_all()

# 3. Define os Modelos (Classes) usando o objeto db
class Usuario(db.Model):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    # Adicione seus campos aqui...
    nome = db.Column(db.String(100), nullable=False)
    
    # Exemplo de relacionamento 
    # pagamentos = db.relationship('Pagamento', backref='usuario', lazy=True)

class Associado(db.Model):
    __tablename__ = 'associado'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    # ... outros campos

class Pagamento(db.Model):
    __tablename__ = 'pagamento'
    # *Certifique-se de que todos os seus Column() têm um nome.
    # Ex: db.Column(db.Integer, primary_key=True) é a sintaxe correta.
    # Evite deixar a coluna vazia ou sem nome, o que causou o erro anterior.
    id = db.Column(db.Integer, primary_key=True)
    associado_id = db.Column(db.Integer, db.ForeignKey('associado.id'), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data = db.Column(db.Date, nullable=False)
    # ... outros campos

class Despesa(db.Model):
    __tablename__ = 'despesa'
    id = db.Column(db.Integer, primary_key=True)
    # ... outros campos

class Configuracao(db.Model):
    __tablename__ = 'configuracao'
    id = db.Column(db.Integer, primary_key=True)
    # ... outros campos

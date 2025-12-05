import os
import logging
from flask import Flask
# Importa APENAS db e init_db de database.py
from database import init_db, db 
# Importa TODOS os modelos de models.py
from models import (
    create_initial_admin, 
    User, 
    Usuario, 
    Associado, 
    Pagamento, 
    Despesa, 
    Configuracao
) 

# Configuração de Logging para melhor visualização
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ----------------------------------------------------
# 1. Configuração do Flask-SQLAlchemy para Heroku/Local
# ----------------------------------------------------

# URL padrão para o PostgreSQL local (AJUSTE SUAS CREDENCIAIS AQUI)
DATABASE_URL_LOCAL = 'postgresql://junior:230808Deus#@localhost:5432/acpamsal_db' 

# Tenta carregar a URL de conexão da variável de ambiente, senão usa a URL local
database_uri = os.environ.get("DATABASE_URL", DATABASE_URL_LOCAL)

# Correção para o SQLAlchemy lidar com o formato Heroku 'postgres://'
if database_uri.startswith("postgres://"):
    database_uri = database_uri.replace("postgres://", "postgresql://", 1)

# Inicializa o Flask
app = Flask(__name__)

# Configuração da Aplicação
app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False 
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chave_secreta_padrao_para_desenvolvimento') 


# ----------------------------------------------------
# 2. Inicialização do Banco de Dados e Criação de Tabelas
# ----------------------------------------------------

# Inicializa o db COM o objeto app que JÁ TEM a configuração de URI correta
init_db(app) 

# Bloco para criar tabelas e o administrador inicial.
with app.app_context():
    try:
        # Cria todas as tabelas registradas pelos modelos importados
        db.create_all() 
        logger.info("Tabelas do banco de dados verificadas/criadas.")
        
        # Cria o usuário administrador inicial
        create_initial_admin(app)
    except Exception as e:
        # Erro grave na inicialização do banco de dados
        logger.error(f"FATAL: Falha na conexão ou na criação das tabelas. Verifique a URI do banco de dados. Erro: {e}")


# ----------------------------------------------------
# 3. Rotas da Aplicação
# ----------------------------------------------------

@app.route('/')
def home():
    try:
        # Consultas de contagem dentro do contexto da aplicação
        with app.app_context():
            user_count = db.session.execute(db.select(db.func.count(User.id))).scalar_one_or_none() or 0
            associado_count = db.session.execute(db.select(db.func.count(Associado.id))).scalar_one_or_none() or 0
        
        db_status = "Conectado com sucesso ao PostgreSQL!"
        db_color = "green"
    except Exception as e:
        logger.error(f"Erro ao consultar o banco de dados na rota home: {e}")
        user_count = "N/A"
        associado_count = "N/A"
        # Mostra o status de erro para o usuário
        db_status = f"ERRO DE CONEXÃO: {e.__class__.__name__}"
        db_color = "red"

    return f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <title>ACPAMSAL - Status</title>
        <!-- Tailwind CSS (Apenas para demonstração, usei um estilo simples inline) -->
        <style>
            body {{ font-family: 'Inter', sans-serif; text-align: center; padding: 50px; background-color: #f4f4f9; color: #333; }}
            .container {{ 
                background: white; 
                padding: 30px; 
                border-radius: 12px; 
                box-shadow: 0 6px 12px rgba(0,0,0,0.15); 
                display: inline-block; 
                max-width: 90%;
            }}
            h1 {{ color: #0056b3; margin-bottom: 10px; }}
            h2 {{ color: #555; margin-top: 30px; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
            .data {{ margin-top: 20px; text-align: left; display: inline-block; padding: 15px; border: 1px dashed #ccc; border-radius: 8px; }}
            .data p {{ margin: 10px 0; font-size: 1.1em; }}
            .admin-creds strong {{ color: #d9534f; font-weight: bold; }}
            .status {{ font-weight: bold; color: {db_color}; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>ACPAMSAL Aplicação Principal</h1>
            <div class="data">
                <p>Status da Conexão: <span class="status">{db_status}</span></p>
                <p>Total de Usuários (Login): <strong>{user_count}</strong></p>
                <p>Total de Associados: <strong>{associado_count}</strong></p>
            </div>
            <h2>Credenciais do Administrador Inicial</h2>
            <div class="admin-creds">
                <p>Email: <strong>acpamsal@gmail.com</strong></p>
                <p>Senha: <strong>230808Deus#</strong></p>
            </div>
        </div>
    </body>
    </html>
    """

# ----------------------------------------------------
# 4. Execução da Aplicação
# ----------------------------------------------------

if __name__ == '__main__':
    # Execução local
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    # Execução em ambiente de produção (WSGI server como Gunicorn)
    logger.info("Aplicação carregada para WSGI server (Gunicorn/Heroku).")

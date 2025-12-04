import os
import sys

# Garante que os módulos sejam encontrados
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Importa a instância do Flask e do SQLAlchemy
from app import app, db, init_db
from database import Usuario
from werkzeug.security import generate_password_hash

# Função que será executada
def run_setup():
    print("Iniciando setup do banco de dados...")
    # Usa o contexto do aplicativo para interagir com o DB
    with app.app_context():
        # 1. Cria todas as tabelas (se não existirem)
        db.create_all()
        print("Tabelas criadas com sucesso.")

        # 2. Cria o usuário administrador padrão (se não existir)
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
            print("Usuário Admin padrão criado.")
        else:
            print("Usuário Admin já existe.")

    print("Setup concluído! A aplicação está pronta para uso.")

if __name__ == '__main__':
    run_setup()

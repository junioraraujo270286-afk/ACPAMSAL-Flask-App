from app import app, db, Configuracao, Propaganda

def inicializar_sistema():
    with app.app_context():
        # 1. Criar o banco de dados
        db.create_all()
        
        # 2. Verificar se já existe configuração
        if not Configuracao.query.first():
            nova_conf = Configuracao(
                nome_entidade="ASSOCIAÇÃO DOS CONDUTORES PROFISSIONAIS AUTÔNOMOS - ACPAMSAL",
                logomarca="logo_padrao.png"
            )
            db.session.add(nova_conf)
            print("✅ Configuração da ACPAMSAL criada com sucesso!")

        # 3. Adicionar uma propaganda de boas-vindas (opcional)
        if not Propaganda.query.first():
            promo = Propaganda(nome="Bem-vindo à ACPAMSAL", arquivo="default_ad.jpg")
            db.session.add(promo)
            
        db.session.commit()
        print("🚀 Sistema pronto para uso, Júnior!")

if __name__ == "__main__":
    inicializar_sistema()

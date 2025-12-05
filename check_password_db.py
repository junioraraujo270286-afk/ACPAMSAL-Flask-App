from app import app, db, Usuario

# Script de Diagnóstico: Verifica a senha do Admin Principal no Heroku

with app.app_context():
    print("--- INICIANDO DIAGNÓSTICO DE SENHA ---")
    admin = Usuario.query.filter_by(email='acpamsal@gmail.com').first()
    
    if admin:
        senha_correta = '230808Deus#'
        
        # 1. Imprime a senha salva (PostgreSQL) e seu comprimento
        # O uso de repr() garante que espaços em branco sejam visíveis
        print(f"SENHA SALVA NO DB (PostgreSQL): {repr(admin.senha)}")
        print(f"COMPRIMENTO DA SENHA SALVA: {len(admin.senha)}")
        
        # 2. Faz a comparação direta para ver se o Python a considera igual
        comparacao_direta = admin.senha == senha_correta
        print(f"DB.senha é IGUAL a '{senha_correta}'?: {comparacao_direta}")
        
        # 3. Testa a comparação que está no código (com .strip() no input do usuário)
        # Como o valor no DB não tem .strip(), vamos simular o que acontece:
        senha_form_limpa = '230808Deus#'.strip()
        comparacao_logica = admin.senha == senha_form_limpa
        print(f"DB.senha é IGUAL à senha de login LIMPA ('{senha_form_limpa}')?: {comparacao_logica}")
        
        # 4. Verifica se a senha salva contém espaços em branco
        tem_espaco = admin.senha != admin.senha.strip()
        print(f"A senha salva no DB contém espaços nas pontas?: {tem_espaco}")
    else:
        print("❌ Usuário Admin acpamsal@gmail.com NÃO encontrado. O commit falhou anteriormente.")
        
    print("--- FIM DO DIAGNÓSTICO ---")
exit()

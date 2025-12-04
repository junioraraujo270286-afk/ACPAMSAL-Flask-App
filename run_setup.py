from app import app, db, Usuario
with app.app_context():
    admin = Usuario.query.filter_by(email='acpamsal@gmail.com').first()
    if admin:
        db.session.delete(admin)
        db.session.commit()
        print("Usuário Admin DELETADO com sucesso.")
    else:
        print("Usuário Admin não encontrado. Limpeza OK.")
exit()

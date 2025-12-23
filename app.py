import os, uuid, io
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, session, request, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import qrcode

base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.secret_key = "ACPAMSAL_OFICIAL_2025_FINAL_FIXED"

app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, 'static/uploads')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'acpamsal.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

# --- MODELOS ---
class Associado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    matricula = db.Column(db.String(50), unique=True)
    nome = db.Column(db.String(100))
    email = db.Column(db.String(100))
    placa = db.Column(db.String(20))
    modelo = db.Column(db.String(50))
    foto = db.Column(db.String(255), default="default.jpg")

class Familia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    responsavel_nome = db.Column(db.String(100))
    contato = db.Column(db.String(20))
    dependentes = db.Column(db.Text)

class Propaganda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    arquivo = db.Column(db.String(255))
    tipo = db.Column(db.String(10))

class Mensalidade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    socio_id = db.Column(db.Integer, db.ForeignKey('associado.id'))
    mes_referencia = db.Column(db.String(20))
    isento = db.Column(db.Boolean, default=False)
    socio = db.relationship('Associado', backref='mensalidades')

@app.context_processor
def inject_global():
    return dict(propagandas=Propaganda.query.all())

def calcular_atrasos(socio_id):
    meses_ano = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    inicio_cobranca_idx = 7 # AGOSTO
    mes_atual_idx = datetime.now().month - 1
    pagos = [m.mes_referencia for m in Mensalidade.query.filter_by(socio_id=socio_id).all()]
    return [meses_ano[i] for i in range(inicio_cobranca_idx, mes_atual_idx + 1) if meses_ano[i] not in pagos]

# --- ROTAS ---
@app.route('/')
def login(): return render_template('login.html')

@app.route('/auth', methods=['POST'])
def auth():
    u, p = request.form.get('email'), request.form.get('senha')
    if u == "acpamsal@gmail.com" and p == "230808Deus#":
        session['admin'] = True
        return redirect(url_for('admin_associados'))
    s = Associado.query.filter_by(email=u, matricula=p).first()
    if s:
        if len(calcular_atrasos(s.id)) >= 3:
            return "ACESSO SUSPENSO POR INADIMPLÊNCIA."
        session['socio_id'] = s.id
        return redirect(url_for('perfil'))
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/consulta')
def consulta():
    q = request.args.get('q', '').strip()
    s = Associado.query.filter((Associado.placa.ilike(f"%{q}%")) | (Associado.matricula == q) | (Associado.nome.ilike(f"%{q}%"))).first() if q else None
    if s and len(calcular_atrasos(s.id)) >= 3:
        msg = "UNIFORME COM A MATRÍCULA SUSPENSA E AGUARDANDO REMOÇÃO DAS VIAS PÚBLICAS, DE ACORDO COM ASSINATURA DO TERMO DE RESPONSABILIDADE ASSINADO E REGISTRADO EM CARTÓRIO."
        return render_template('consulta.html', suspenso=True, msg=msg, query=q)
    return render_template('consulta.html', s=s, query=q)

@app.route('/perfil')
def perfil():
    s_id = session.get('socio_id') or request.args.get('id')
    s = Associado.query.get(s_id)
    if not s: return redirect(url_for('login'))
    return render_template('perfil.html', s=s, atrasos=calcular_atrasos(s.id))

@app.route('/admin/associados', methods=['GET', 'POST'])
def admin_associados():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method == 'POST':
        f = request.files.get('foto')
        fn = secure_filename(uuid.uuid4().hex + ".jpg") if f else "default.jpg"
        if f: f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
        n = Associado(matricula=request.form.get('matricula'), nome=request.form.get('nome'), 
                      email=request.form.get('email'), placa=request.form.get('placa').upper(), 
                      modelo=request.form.get('modelo'), foto=fn)
        db.session.add(n)
        db.session.commit()
    return render_template('admin_associados.html', socios=Associado.query.all())

@app.route('/admin/familias', methods=['GET', 'POST'])
def admin_familias():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method == 'POST':
        nomes, idades, contatos = request.form.getlist('dep_nome[]'), request.form.getlist('dep_idade[]'), request.form.getlist('dep_contato[]')
        deps = " | ".join([f"{n}({i}a)-{c}" for n, i, c in zip(nomes, idades, contatos) if n])
        nova = Familia(responsavel_nome=request.form.get('responsavel'), contato=request.form.get('contato'), dependentes=deps)
        db.session.add(nova); db.session.commit()
    return render_template('admin_familias.html', familias=Familia.query.all())

@app.route('/admin/financeiro', methods=['GET', 'POST'])
def admin_financeiro():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method == 'POST':
        mid = request.form.get('mensalidade_id')
        if mid:
            m = Mensalidade.query.get(mid)
            m.mes_referencia = request.form.get('mes')
            m.isento = True if request.form.get('isento') else False
        else:
            db.session.add(Mensalidade(socio_id=request.form.get('socio_id'), 
                                     mes_referencia=request.form.get('mes'), 
                                     isento=True if request.form.get('isento') else False))
        db.session.commit()
    return render_template('admin_financeiro.html', socios=Associado.query.all(), mensalidades=Mensalidade.query.all())

@app.route('/admin/financeiro/remover/<int:id>')
def remover_financeiro(id):
    if not session.get('admin'): return redirect(url_for('login'))
    m = Mensalidade.query.get(id)
    if m: db.session.delete(m); db.session.commit()
    return redirect(url_for('admin_financeiro'))

@app.route('/admin/publicidade', methods=['GET', 'POST'])
def admin_publicidade():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method == 'POST':
        f = request.files.get('arquivo')
        if f:
            ext = f.filename.split('.')[-1].lower()
            t = 'vid' if ext in ['mp4', 'mov', 'avi'] else 'img'
            fn = secure_filename(uuid.uuid4().hex + "." + ext)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            db.session.add(Propaganda(nome=request.form.get('nome'), arquivo=fn, tipo=t)); db.session.commit()
    return render_template('admin_publicidade.html', props=Propaganda.query.all())

@app.route('/remover/<string:tipo>/<int:id>')
def remover(tipo, id):
    if not session.get('admin'): return redirect(url_for('login'))
    item = Propaganda.query.get(id) if tipo == 'prop' else Familia.query.get(id) if tipo == 'familia' else Associado.query.get(id)
    if item: db.session.delete(item); db.session.commit()
    return redirect(request.referrer)

@app.route('/gerar_carteirinha/<int:id>')
def gerar_carteirinha(id):
    s = Associado.query.get(id)
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(240, 380))
    c.setFillColorRGB(0.1, 0.1, 0.1); c.rect(0, 0, 240, 380, fill=1)
    c.setFillColorRGB(1, 0.8, 0); c.rect(0, 305, 240, 75, fill=1)
    
    logo_path = os.path.join(app.config['UPLOAD_FOLDER'], 'logo_acpamsal.png')
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 90, 335, width=60, height=40, mask='auto')
    
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(120, 318, "CNPJ 39.242.691/0001-75")
    
    f_p = os.path.join(app.config['UPLOAD_FOLDER'], s.foto)
    if os.path.exists(f_p): c.drawImage(f_p, 70, 195, width=100, height=100)
    
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(120, 175, s.nome.upper())
    c.setFillColorRGB(1, 0.8, 0); c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(120, 150, s.placa)
    
    qr = qrcode.make(f"https://acpamsal.com/consulta?q={s.placa}")
    qrp = os.path.join(app.config['UPLOAD_FOLDER'], f"qr_{s.id}.png")
    qr.save(qrp)
    c.drawImage(qrp, 90, 80, width=60, height=60)
    
    c.setFillColorRGB(1, 0.8, 0); c.rect(0, 0, 240, 65, fill=1)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(120, 48, "RUA PEDRO DE ALCÂNTARA BARROS Nº 20, BAIRRO SÃO TOMÉ")
    c.drawCentredString(120, 38, "SALINÓPOLIS/PA")
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(120, 22, "WHATSAPP (91)98212-2175 / E-MAIL acpamsal@gmail.com")
    
    c.showPage(); c.save(); buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"carteirinha_{s.matricula}.pdf")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

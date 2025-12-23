import os, uuid, io
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, session, request, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import qrcode

base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.secret_key = "ACPAMSAL_OFICIAL_2025_FINAL"

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
    ponto_trabalho = db.Column(db.String(100)); nome = db.Column(db.String(100))
    rua = db.Column(db.String(100)); numero = db.Column(db.String(10)); bairro = db.Column(db.String(50))
    ponto_referencia = db.Column(db.String(100)); rg = db.Column(db.String(20)); cpf = db.Column(db.String(20))
    cnh = db.Column(db.String(10)); email = db.Column(db.String(100)); placa = db.Column(db.String(20))
    modelo = db.Column(db.String(50)); cor = db.Column(db.String(30)); ano = db.Column(db.String(10))
    renavam = db.Column(db.String(20)); foto = db.Column(db.String(255), default="default.jpg")

class Familia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    responsavel_nome = db.Column(db.String(100)); contato = db.Column(db.String(20)); dependentes = db.Column(db.Text)

class Propaganda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100)); arquivo = db.Column(db.String(255)); tipo = db.Column(db.String(10))

class Mensalidade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    socio_id = db.Column(db.Integer, db.ForeignKey('associado.id'))
    mes_referencia = db.Column(db.String(20)); isento = db.Column(db.Boolean, default=False)
    socio = db.relationship('Associado', backref='mensalidades')

@app.context_processor
def inject_global():
    return dict(propagandas=Propaganda.query.all())

def calcular_atrasos(socio_id):
    meses_ano = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_atual_idx = datetime.now().month - 1
    pagos = [m.mes_referencia for m in Mensalidade.query.filter_by(socio_id=socio_id).all()]
    # Cobrança inicia em Agosto (índice 7)
    return [meses_ano[i] for i in range(7, mes_atual_idx + 1) if meses_ano[i] not in pagos]

# --- LOGIN COM BLOQUEIO ---
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
        atrasos = calcular_atrasos(s.id)
        if len(atrasos) >= 3:
            # TEXTO JURÍDICO DE BLOQUEIO
            msg = """
            <div style='color:red; font-family:sans-serif; padding:20px; border:2px solid red;'>
            <h2>ACESSO NEGADO - ASSOCIADO DESLIGADO</h2>
            <p><strong>Termo de Responsabilidade (Art. 221 do Código Civil)</strong><br>
            O Termo é registrado em cartório. Isso dá ao documento "fé pública" e o torna um título executivo extrajudicial.</p>
            <p>Se o associado assinou um termo de responsabilidade afirmando que os uniformes pertencem à associação e devem ser devolvidos em caso de desligamento, ele está obrigado por lei a cumprir o contrato (princípio do Pacta Sunt Servanda).</p>
            <hr>
            <p><strong>3. Código Penal (Apropriação Indébita)</strong><br>
            Art. 168 do Código Penal: Apropriar-se de coisa alheia móvel, de que tem a posse ou a detenção. Pena: reclusão, de um a quatro anos, e multa.</p>
            <a href='/'>Voltar</a>
            </div>
            """
            return msg
        session['socio_id'] = s.id
        return redirect(url_for('perfil'))
    return redirect(url_for('login'))

@app.route('/perfil')
def perfil():
    s_id = session.get('socio_id') or request.args.get('id')
    if not s_id: return redirect(url_for('login'))
    s = Associado.query.get(s_id)
    return render_template('perfil_associado.html', s=s, atrasos=calcular_atrasos(s.id))

# --- CONSULTA COM AVISO DE DESLIGAMENTO ---
@app.route('/consulta')
def consulta():
    q = request.args.get('q', '').strip()
    s = None
    aviso_desligado = False
    if q:
        s = Associado.query.filter((Associado.placa.ilike(f"%{q}%")) | (Associado.matricula == q)).first()
        if s and len(calcular_atrasos(s.id)) >= 3:
            aviso_desligado = True
            s = None # Oculta os dados do associado inadimplente
    return render_template('consulta.html', s=s, query=q, aviso_desligado=aviso_desligado)

@app.route('/alterar_foto', methods=['POST'])
def alterar_foto():
    s_id = session.get('socio_id') or request.form.get('socio_id')
    if not s_id: return redirect(url_for('login'))
    s = Associado.query.get(s_id)
    f = request.files.get('nova_foto')
    if f:
        fn = secure_filename(uuid.uuid4().hex + ".jpg")
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
        s.foto = fn; db.session.commit()
    return redirect(request.referrer)

@app.route('/admin/financeiro', methods=['GET', 'POST'])
def admin_financeiro():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method == 'POST':
        m_id = request.form.get('mensalidade_id')
        if m_id:
            m = Mensalidade.query.get(m_id)
            m.mes_referencia = request.form.get('mes')
            m.isento = True if request.form.get('isento') else False
        else:
            db.session.add(Mensalidade(socio_id=request.form.get('socio_id'), mes_referencia=request.form.get('mes'), isento=True if request.form.get('isento') else False))
        db.session.commit()
    return render_template('admin_financeiro.html', socios=Associado.query.all(), mensalidades=Mensalidade.query.all())

@app.route('/admin/associados', methods=['GET', 'POST'])
def admin_associados():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method == 'POST':
        f = request.files.get('foto')
        fn = secure_filename(uuid.uuid4().hex + ".jpg") if f else "default.jpg"
        if f: f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
        novo = Associado(matricula=request.form.get('matricula'), ponto_trabalho=request.form.get('ponto_trabalho'), nome=request.form.get('nome'), rua=request.form.get('rua'), numero=request.form.get('numero'), bairro=request.form.get('bairro'), ponto_referencia=request.form.get('ponto_referencia'), rg=request.form.get('rg'), cpf=request.form.get('cpf'), cnh=request.form.get('cnh'), email=request.form.get('email'), placa=request.form.get('placa').upper(), modelo=request.form.get('modelo'), cor=request.form.get('cor'), ano=request.form.get('ano'), renavam=request.form.get('renavam'), foto=fn)
        db.session.add(novo); db.session.commit()
    return render_template('admin_associados.html', socios=Associado.query.all())

@app.route('/admin/familias', methods=['GET', 'POST'])
def admin_familias():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method == 'POST':
        nomes, idades, contatos = request.form.getlist('dep_nome[]'), request.form.getlist('dep_idade[]'), request.form.getlist('dep_contato[]')
        deps = " | ".join([f"{n}({i}a)-{c}" for n, i, c in zip(nomes, idades, contatos) if n])
        db.session.add(Familia(responsavel_nome=request.form.get('responsavel'), contato=request.form.get('contato'), dependentes=deps)); db.session.commit()
    return render_template('admin_familias.html', familias=Familia.query.all())

@app.route('/admin/publicidade', methods=['GET', 'POST'])
def admin_publicidade():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method == 'POST':
        f = request.files.get('arquivo')
        if f:
            ext = f.filename.split('.')[-1].lower(); tipo = 'vid' if ext in ['mp4', 'mov', 'avi'] else 'img'; fn = secure_filename(uuid.uuid4().hex + "." + ext)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            db.session.add(Propaganda(nome=request.form.get('nome'), arquivo=fn, tipo=tipo)); db.session.commit()
    return render_template('admin_publicidade.html', props=Propaganda.query.all())

@app.route('/remover/<string:tipo>/<int:id>')
def remover(tipo, id):
    if not session.get('admin'): return redirect(url_for('login'))
    item = Propaganda.query.get(id) if tipo == 'prop' else Familia.query.get(id) if tipo == 'familia' else Mensalidade.query.get(id) if tipo == 'mensalidade' else Associado.query.get(id)
    if item: db.session.delete(item); db.session.commit()
    return redirect(request.referrer)

@app.route('/gerar_carteirinha/<int:id>')
def gerar_carteirinha(id):
    s = Associado.query.get(id)
    buffer = io.BytesIO(); c = canvas.Canvas(buffer, pagesize=(240, 380))
    c.setFillColor(colors.black); c.rect(0, 0, 240, 380, fill=1); c.setStrokeColor(colors.gold); c.rect(5, 5, 230, 370, stroke=1)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 11); c.drawCentredString(120, 300, "ACPAMSAL")
    c.setFont("Helvetica", 7); c.drawCentredString(120, 290, "CNPJ 39.242.691/0001-75")
    foto_path = os.path.join(app.config['UPLOAD_FOLDER'], s.foto)
    if os.path.exists(foto_path): c.drawImage(foto_path, 75, 185, width=90, height=95)
    c.setFillColor(colors.gold); c.setFont("Helvetica-Bold", 12); c.drawCentredString(120, 165, s.nome.upper()[:22])
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 10); c.drawCentredString(120, 150, f"MATRÍCULA: {s.matricula}")
    c.setFont("Helvetica", 5.5); c.drawCentredString(120, 35, "RUA PEDRO DE ALCÂNTARA BARROS Nº 20, BAIRRO SÃO TOMÉ - SALINÓPOLIS/PA")
    c.setFont("Helvetica-Bold", 6); c.drawCentredString(120, 25, "WHATSAPP (91)98212-2175 / E-MAIL acpamsal@gmail.com")
    c.showPage(); c.save(); buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"carteirinha_{s.matricula}.pdf")

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

with app.app_context(): db.create_all()
if __name__ == '__main__': app.run(debug=True)

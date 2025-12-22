import os, uuid
from datetime import datetime, date
from flask import Flask, render_template, redirect, url_for, session, request, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import pdfkit

app = Flask(__name__)
app.secret_key = "acpamsal_oficial_2026_final"

# --- CONFIGURAÇÕES DE DIRETÓRIO ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'acpamsal.db')
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static/uploads')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# --- MODELOS DE DADOS ---
class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    logo = db.Column(db.String(255), default='logo.png')
    fundo_img = db.Column(db.String(255), default='')
    nome_entidade = db.Column(db.String(500), default="ASSOCIAÇÃO DOS CONDUTORES PROFISSIONAIS AUTÔNOMOS MOTOFRETISTAS, MOTOCICLISTAS, MOTOTAXISTAS E MOTOBOYS DO MUNICÍPIO DE SALINÓPOLIS - ACPAMSAL")
    endereco = db.Column(db.String(255), default="Rua Pedro de Alcântara Barros Nº 20, Bairro São Tomé - CEP 68.721-000 - Salinópolis-PA")
    contatos = db.Column(db.String(255), default="WhatsApp: (91) 98212-2175 | acpamsal@gmail.com")

class Associado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    foto = db.Column(db.String(255), default='default.jpg')
    nome = db.Column(db.String(100), nullable=False)
    matricula = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True)
    rg = db.Column(db.String(20)); contato = db.Column(db.String(20)); ponto = db.Column(db.String(100))
    moto_placa = db.Column(db.String(20)); moto_marca = db.Column(db.String(50)); moto_modelo = db.Column(db.String(50)); moto_cor = db.Column(db.String(30))
    pagamentos = db.relationship('Pagamento', backref='associado', lazy=True, cascade="all, delete-orphan")

    def esta_apto_consulta(self):
        # Regra: Início em 01/01/2026. Se dever 3 meses ou mais, bloqueia.
        inicio = date(2026, 1, 1)
        hoje = date.today()
        if hoje < inicio: return True
        meses_passados = (hoje.year - inicio.year) * 12 + hoje.month - inicio.month + 1
        return len(self.pagamentos) >= (meses_passados - 2)

class Pagamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    referencia = db.Column(db.String(20))
    data_pag = db.Column(db.DateTime, default=datetime.now)
    associado_id = db.Column(db.Integer, db.ForeignKey('associado.id'))

class Familia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    responsavel = db.Column(db.String(100), nullable=False)
    endereco = db.Column(db.String(200)); bairro = db.Column(db.String(100)); contato = db.Column(db.String(20))
    num_eleitores = db.Column(db.Integer, default=0); observacao = db.Column(db.Text)

# --- CONTEXTO GLOBAL ---
@app.context_processor
def inject_global():
    conf = Configuracao.query.first()
    if not conf:
        conf = Configuracao(logo='logo.png')
        db.session.add(conf); db.session.commit()
    return dict(config_global=conf, now=datetime.now().strftime('%d/%m/%Y %H:%M'))

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, s = request.form.get('email'), request.form.get('senha')
        if u == "acpamsal@gmail.com" and s == "230808Deus#":
            session['admin'] = True; return redirect(url_for('admin_dashboard'))
        socio = Associado.query.filter_by(email=u, matricula=s).first()
        if socio:
            session['socio_id'] = socio.id; return redirect(url_for('perfil_associado'))
        flash("E-mail ou Matrícula incorretos.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

# --- ROTAS PÚBLICAS E PERFIL ---
@app.route('/')
def publico():
    q = request.args.get('q', '').strip()
    socio = None; msg = None
    if q:
        socio = Associado.query.filter((Associado.nome.like(f"%{q}%")) | (Associado.moto_placa == q.upper()) | (Associado.matricula == q)).first()
        if socio and not socio.esta_apto_consulta():
            msg = "UNIFORME COM NOTIFICAÇÃO DE RECOLHIMENTO DE ACORDO COM TERMO DE RESPONSABILIDADE ASSINADA E REGISTRADA EM CARTÓRIO."
            socio = None
    return render_template('publico.html', socio=socio, msg=msg)

@app.route('/perfil', methods=['GET', 'POST'])
def perfil_associado():
    if not session.get('socio_id'): return redirect(url_for('login'))
    s = Associado.query.get(session['socio_id'])
    if request.method == 'POST':
        f = request.files.get('foto')
        if f:
            fn = secure_filename(f"{uuid.uuid4().hex}.jpg")
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            s.foto = fn; db.session.commit(); flash("Foto atualizada!", "success")
    return render_template('perfil_associado.html', socio=s)

@app.route('/perfil/pagar')
def pagar_mensalidade():
    if not session.get('socio_id'): return redirect(url_for('login'))
    pix = {"cnpj": "39.242.691/0001-75", "nome": "ACPAMSAL"}
    return render_template('perfil_pagar.html', pix=pix)

# --- ÁREA ADMINISTRATIVA ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'): return redirect(url_for('login'))
    return render_template('admin_dashboard.html')

@app.route('/admin/associados')
def lista_associados():
    if not session.get('admin'): return redirect(url_for('login'))
    return render_template('admin_associados_lista.html', lista=Associado.query.all())

@app.route('/admin/associado/novo', methods=['GET', 'POST'])
def novo_associado():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method == 'POST':
        f = request.files.get('foto')
        fn = secure_filename(f"{uuid.uuid4().hex}.jpg") if f else "default.jpg"
        if f: f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
        novo = Associado(nome=request.form['nome'].upper(), matricula=request.form['matricula'], email=request.form['email'], rg=request.form['rg'], contato=request.form['contato'], ponto=request.form['ponto'], moto_placa=request.form['placa'].upper(), moto_marca=request.form['marca'], moto_modelo=request.form['modelo'], moto_cor=request.form['cor'], foto=fn)
        db.session.add(novo); db.session.commit(); return redirect(url_for('lista_associados'))
    return render_template('admin_associado_form.html', socio=None)

@app.route('/admin/associado/editar/<int:id>', methods=['GET', 'POST'])
def editar_associado(id):
    if not session.get('admin'): return redirect(url_for('login'))
    s = Associado.query.get_or_404(id)
    if request.method == 'POST':
        s.nome, s.matricula, s.moto_placa = request.form['nome'].upper(), request.form['matricula'], request.form['placa'].upper()
        db.session.commit(); return redirect(url_for('lista_associados'))
    return render_template('admin_associado_form.html', socio=s)

@app.route('/admin/associado/remover/<int:id>')
def remover_associado(id):
    if not session.get('admin'): return redirect(url_for('login'))
    db.session.delete(Associado.query.get_or_404(id)); db.session.commit(); return redirect(url_for('lista_associados'))

@app.route('/admin/mensalidades')
def lista_mensalidades():
    if not session.get('admin'): return redirect(url_for('login'))
    pags = Pagamento.query.order_by(Pagamento.data_pag.desc()).all()
    return render_template('admin_mensalidades_lista.html', pagamentos=pags)

@app.route('/admin/mensalidade/nova', methods=['GET', 'POST'])
def nova_mensalidade():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method == 'POST':
        p = Pagamento(associado_id=request.form.get('socio_id'), referencia=request.form.get('ref'))
        db.session.add(p); db.session.commit(); return redirect(url_for('lista_mensalidades'))
    return render_template('admin_mensalidade_form.html', socios=Associado.query.all())

@app.route('/admin/mensalidade/remover/<int:id>')
def remover_mensalidade(id):
    if not session.get('admin'): return redirect(url_for('login'))
    db.session.delete(Pagamento.query.get_or_404(id)); db.session.commit(); return redirect(url_for('lista_mensalidades'))

@app.route('/admin/familias')
def lista_familias():
    if not session.get('admin'): return redirect(url_for('login'))
    return render_template('familias_lista.html', familias=Familia.query.all())

@app.route('/admin/familias/cadastrar', methods=['GET', 'POST'])
def cadastrar_familia():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method == 'POST':
        nova = Familia(responsavel=request.form['responsavel'].upper(), endereco=request.form['endereco'], bairro=request.form['bairro'], contato=request.form['contato'], num_eleitores=request.form['eleitores'], observacao=request.form['obs'])
        db.session.add(nova); db.session.commit(); return redirect(url_for('lista_familias'))
    return render_template('familias_form.html', familia=None)

@app.route('/admin/familias/remover/<int:id>')
def remover_familia(id):
    if not session.get('admin'): return redirect(url_for('login'))
    db.session.delete(Familia.query.get_or_404(id)); db.session.commit(); return redirect(url_for('lista_familias'))

@app.route('/admin/relatorio/pdf')
def gerar_pdf():
    if not session.get('admin'): return redirect(url_for('login'))
    html = render_template('pdf_modelo.html', lista=Associado.query.all())
    pdf = pdfkit.from_string(html, False)
    resp = make_response(pdf)
    resp.headers['Content-Type'] = 'application/pdf'
    return resp

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)

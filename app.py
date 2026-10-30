import os
import re
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, make_response
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'chave_secreta_segura_condominio'

# Configuração para evitar expiração rápida de sessão (8 horas)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# Desativa cache e força recarregamento automático dos modelos HTML
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

CORS(app)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ADMIN_USUARIO = "admin"
ADMIN_SENHA = "admin123condominio"

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# CONEXÃO COM TRATAMENTO DE PREFIXO DO POSTGRESQL NO RENDER
def conectar_banco():
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Trata o formato exigido pelo psycopg2 substituindo postgres:// por postgresql://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    else:
        # Fallback local com SQLite para desenvolvimento
        conexao = sqlite3.connect('condominio.db')
        conexao.row_factory = sqlite3.Row
        return conexao

def obter_placeholder():
    return "%s" if os.environ.get('DATABASE_URL') else "?"

def arquivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def apenas_numeros(valor):
    return re.sub(r'\D', '', str(valor or ''))

# VALIDAÇÃO MATEMÁTICA DE CPF
def validar_cpf(cpf):
    cpf = apenas_numeros(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        soma = sum(int(cpf[num]) * ((i + 1) - num) for num in range(0, i))
        digito = (soma * 10 % 11) % 10
        if int(cpf[i]) != digito:
            return False
    return True

# VALIDAÇÃO MATEMÁTICA DE CNPJ
def validar_cnpj(cnpj):
    cnpj = apenas_numeros(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    tamanho = 12
    numeros = cnpj[:tamanho]
    digitos = cnpj[tamanho:]
    
    def calc_digito(pos):
        soma = 0
        p = pos
        for num in numeros:
            soma += int(num) * p
            p -= 1
            if p < 2:
                p = 9
        d = 11 - (soma % 11)
        return 0 if d > 9 else d

    d1 = calc_digito(5)
    if int(digitos[0]) != d1:
        return False
    numeros += str(d1)
    d2 = calc_digito(6)
    return int(digitos[1]) == d2

def gerar_protocolo_anual(cursor):
    p = obter_placeholder()
    ano_atual = datetime.now().strftime("%Y")
    cursor.execute(f'''
        SELECT protocolo_anual FROM encomendas 
        WHERE protocolo_anual LIKE {p} 
        ORDER BY id DESC LIMIT 1
    ''', (f"{ano_atual}-%",))
    ultima = cursor.fetchone()
    
    if ultima:
        ultimo_num = int(ultima['protocolo_anual'].split('-')[1])
        novo_num = ultimo_num + 1
    else:
        novo_num = 1
        
    return f"{ano_atual}-{novo_num:04d}"

# CRIAÇÃO SEGURA DE TABELAS (SEM COMANDOS DESTRUCTIVOS / DROP TABLE)
def inicializar_tabelas():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        return

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS condominios (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            cnpj_cpf VARCHAR(20) UNIQUE,
            data_expiracao VARCHAR(20) NOT NULL,
            status VARCHAR(20) DEFAULT 'Ativo'
        );
        CREATE TABLE IF NOT EXISTS moradores (
            id SERIAL PRIMARY KEY,
            condominio_id INTEGER REFERENCES condominios(id),
            nome VARCHAR(255) NOT NULL,
            celular VARCHAR(20) NOT NULL,
            cpf VARCHAR(20) UNIQUE NOT NULL,
            senha VARCHAR(255) NOT NULL,
            bloco INTEGER NOT NULL,
            apartamento INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS porteiros (
            id SERIAL PRIMARY KEY,
            condominio_id INTEGER REFERENCES condominios(id),
            nome VARCHAR(255) NOT NULL,
            matricula VARCHAR(50) UNIQUE NOT NULL,
            senha VARCHAR(255) NOT NULL
        );
        CREATE TABLE IF NOT EXISTS encomendas (
            id SERIAL PRIMARY KEY,
            condominio_id INTEGER REFERENCES condominios(id),
            protocolo_anual VARCHAR(50) UNIQUE NOT NULL,
            bloco INTEGER NOT NULL,
            apartamento INTEGER NOT NULL,
            morador_id INTEGER REFERENCES moradores(id),
            tipo_encomenda VARCHAR(50) NOT NULL,
            empresa_entrega VARCHAR(100) NOT NULL,
            porteiro_id INTEGER REFERENCES porteiros(id),
            porteiro_nome VARCHAR(255),
            foto_url TEXT,
            data_recebimento VARCHAR(50) NOT NULL,
            status VARCHAR(20) DEFAULT 'Pendente',
            retirado_por VARCHAR(255),
            data_retirada VARCHAR(50)
        );
    ''')
    
    cursor.execute('SELECT COUNT(*) as total FROM condominios;')
    res = cursor.fetchone()
    total = res['total'] if isinstance(res, dict) else res[0]
    
    if total == 0:
        exp_inicial = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        cursor.execute(
            'INSERT INTO condominios (nome, cnpj_cpf, data_expiracao, status) VALUES (%s, %s, %s, %s);',
            ('Condomínio Padrão', '00000000000000', exp_inicial, 'Ativo')
        )

    conexao.commit()
    cursor.close()
    conexao.close()

try:
    inicializar_tabelas()
except Exception as e:
    print("Aviso na inicialização do banco PostgreSQL:", e)

@app.before_request
def checar_inatividade():
    session.permanent = True

@app.after_request
def aplicar_headers_seguranca(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/uploads/<filename>')
def imagem_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# PÁGINAS DO SISTEMA
@app.route('/')
def index(): return render_template('index.html')
@app.route('/login-porteiro')
def login_porteiro_page(): return render_template('login_porteiro.html')
@app.route('/login-admin')
def login_admin_page(): return render_template('login_admin.html')
@app.route('/admin-dashboard')
def admin_dashboard_page():
    if not session.get('admin_logado'): return redirect(url_for('login_admin_page'))
    return render_template('admin_dashboard.html')
@app.route('/cadastro-porteiro')
def cadastro_porteiro_page():
    if not session.get('admin_logado'): return redirect(url_for('login_admin_page'))
    return render_template('cadastro_porteiro.html')
@app.route('/login-morador')
def login_morador_page(): return render_template('login_morador.html')
@app.route('/meu-cadastro')
def meu_cadastro_page():
    if not session.get('morador_id'): return redirect(url_for('login_morador_page'))
    return render_template('meu_cadastro.html')
@app.route('/cadastro')
def pagina_cadastro(): return render_template('cadastro.html')
@app.route('/portaria')
def pagina_portaria():
    if not session.get('porteiro_logado'): return redirect(url_for('login_porteiro_page'))
    return render_template('portaria.html')
@app.route('/morador')
def pagina_morador():
    if not session.get('morador_id'): return redirect(url_for('login_morador_page'))
    resp = make_response(render_template('morador.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# LOGINS E AUTENTICAÇÕES
@app.route('/api/admin/login', methods=['POST'])
def login_admin():
    dados = request.json or {}
    if dados.get('usuario') == ADMIN_USUARIO and dados.get('senha') == ADMIN_SENHA:
        session.clear()
        session['admin_logado'] = True
        return jsonify({"sucesso": True}), 200
    return jsonify({"erro": "Usuário ou senha inválidos!"}), 401

@app.route('/api/porteiro/login', methods=['POST'])
def login_porteiro():
    p = obter_placeholder()
    dados = request.json or {}
    matricula = str(dados.get('matricula', '')).strip()
    senha = str(dados.get('senha', '')).strip()

    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute(f'''
        SELECT p.*, c.data_expiracao, c.nome as nome_condominio 
        FROM porteiros p
        LEFT JOIN condominios c ON p.condominio_id = c.id
        WHERE TRIM(p.matricula) = {p} AND TRIM(p.senha) = {p}
    ''', (matricula, senha))
    porteiro = cursor.fetchone()
    conexao.close()

    if not porteiro:
        return jsonify({"erro": "Matrícula ou Senha incorretas!"}), 401

    if porteiro['data_expiracao']:
        data_exp = datetime.strptime(porteiro['data_expiracao'], "%Y-%m-%d")
        if datetime.now() > data_exp:
            return jsonify({"erro": f"Acesso do condomínio '{porteiro['nome_condominio']}' expirado!"}), 403

    session.clear()
    session['porteiro_logado'] = True
    session['porteiro_id'] = porteiro['id']
    session['porteiro_nome'] = porteiro['nome']
    session['condominio_id'] = porteiro['condominio_id']

    return jsonify({"sucesso": True, "nome": porteiro['nome']}), 200

@app.route('/api/morador/login', methods=['POST'])
def login_morador():
    p = obter_placeholder()
    dados = request.json or {}
    cpf = apenas_numeros(dados.get('cpf', ''))
    senha = str(dados.get('senha', '')).strip()

    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute(f'SELECT * FROM moradores WHERE REPLACE(REPLACE(REPLACE(cpf, ".", ""), "-", ""), " ", "") = {p} AND TRIM(senha) = {p}', (cpf, senha))
    morador = cursor.fetchone()

    if not morador:
        conexao.close()
        return jsonify({"erro": "CPF ou Senha incorretos!"}), 401

    morador_dict = dict(morador)
    session.clear()
    session.permanent = True
    session['morador_id'] = morador_dict['id']
    conexao.close()

    return jsonify({"sucesso": True, "morador": morador_dict}), 200

# GESTÃO DE CONDOMÍNIOS
@app.route('/api/admin/condominios', methods=['GET', 'POST'])
def gerenciar_condominios_admin():
    p = obter_placeholder()
    conexao = conectar_banco()
    cursor = conexao.cursor()

    if request.method == 'GET':
        cursor.execute('SELECT * FROM condominios ORDER BY id DESC')
        rows = cursor.fetchall()
        lista = []
        hoje = datetime.now()
        for row in rows:
            item = dict(row)
            data_exp = datetime.strptime(item['data_expiracao'], "%Y-%m-%d")
            dias_restantes = (data_exp - hoje).days + 1
            item['dias_restantes'] = max(0, dias_restantes)
            item['ativo'] = dias_restantes > 0
            item['data_expiracao_br'] = data_exp.strftime("%d/%m/%Y")
            lista.append(item)
        conexao.close()
        return jsonify(lista), 200

    if not session.get('admin_logado'):
        conexao.close()
        return jsonify({"erro": "Acesso negado!"}), 403

    dados = request.json or {}
    nome = dados.get('nome', '').strip()
    doc = apenas_numeros(dados.get('cnpj_cpf', ''))
    dias = int(dados.get('dias', 30))

    if not nome:
        conexao.close()
        return jsonify({"erro": "Informe o nome!"}), 400

    nova_expiracao = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")

    try:
        cursor.execute(f'''
            INSERT INTO condominios (nome, cnpj_cpf, data_expiracao, status)
            VALUES ({p}, {p}, {p}, 'Ativo')
        ''', (nome, doc if doc else None, nova_expiracao))
        conexao.commit()
        return jsonify({"mensagem": f"Condomínio '{nome}' cadastrado!"}), 201
    except Exception:
        return jsonify({"erro": "Erro ou CNPJ/CPF duplicado!"}), 400
    finally:
        conexao.close()

@app.route('/api/admin/condominios/<int:id>/renovar', methods=['PUT'])
def renovar_prazo_cliente(id):
    p = obter_placeholder()
    if not session.get('admin_logado'): return jsonify({"erro": "Negado"}), 403
    dados = request.json or {}
    dias_add = int(dados.get('dias', 30))

    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute(f'SELECT data_expiracao FROM condominios WHERE id = {p}', (id,))
    cliente = cursor.fetchone()

    if not cliente:
        conexao.close()
        return jsonify({"erro": "Não encontrado"}), 404

    data_atual_exp = datetime.strptime(cliente['data_expiracao'], "%Y-%m-%d")
    base_calc = max(datetime.now(), data_atual_exp)
    nova_expiracao = (base_calc + timedelta(days=dias_add)).strftime("%Y-%m-%d")

    cursor.execute(f'UPDATE condominios SET data_expiracao = {p}, status = \'Ativo\' WHERE id = {p}', (nova_expiracao, id))
    conexao.commit()
    conexao.close()

    return jsonify({"mensagem": f"Renovado até {datetime.strptime(nova_expiracao, '%Y-%m-%d').strftime('%d/%m/%Y')}"}), 200

# PORTEIROS
@app.route('/api/porteiro/cadastrar', methods=['POST'])
def cadastrar_porteiro():
    p = obter_placeholder()
    if not session.get('admin_logado'): return jsonify({"erro": "Apenas Admin"}), 403
    dados = request.json or {}
    nome = dados.get('nome', '').strip()
    matricula = str(dados.get('matricula', '')).strip()
    senha = str(dados.get('senha', '')).strip()
    condominio_id = dados.get('condominio_id')

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:
        if not condominio_id:
            cursor.execute('SELECT id FROM condominios ORDER BY id ASC LIMIT 1')
            c = cursor.fetchone()
            condominio_id = c['id'] if c else 1

        cursor.execute(f'''
            INSERT INTO porteiros (condominio_id, nome, matricula, senha)
            VALUES ({p}, {p}, {p}, {p})
        ''', (condominio_id, nome, matricula, senha))
        conexao.commit()
        return jsonify({"mensagem": "Porteiro cadastrado com sucesso!"}), 201
    except Exception:
        return jsonify({"erro": "Matrícula já cadastrada!"}), 400
    finally:
        conexao.close()

# MORADORES E MEU CADASTRO
@app.route('/api/moradores/cadastrar', methods=['POST'])
def cadastrar_morador():
    p = obter_placeholder()
    dados = request.json or {}
    nome = dados.get('nome', '').strip()
    celular = dados.get('celular', '').strip()
    cpf_limpo = apenas_numeros(dados.get('cpf', ''))
    senha = dados.get('senha')
    bloco = int(dados.get('bloco'))
    apartamento = int(dados.get('apartamento'))

    if not validar_cpf(cpf_limpo):
        return jsonify({"erro": "CPF inválido!"}), 400

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(f'SELECT COUNT(*) as total FROM moradores WHERE bloco = {p} AND apartamento = {p}', (bloco, apartamento))
        res = cursor.fetchone()
        tot = res['total'] if isinstance(res, dict) else res[0]
        if tot >= 4:
            return jsonify({"erro": "Limite de 4 moradores por apartamento atingido!"}), 400

        cursor.execute('SELECT id FROM condominios ORDER BY id ASC LIMIT 1')
        c = cursor.fetchone()
        condominio_id = c['id'] if c else 1

        cursor.execute(f'''
            INSERT INTO moradores (condominio_id, nome, celular, cpf, senha, bloco, apartamento)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
        ''', (condominio_id, nome, celular, cpf_limpo, senha, bloco, apartamento))
        conexao.commit()
        return jsonify({"mensagem": "Morador cadastrado!"}), 201
    except Exception:
        return jsonify({"erro": "CPF já cadastrado!"}), 400
    finally:
        conexao.close()

@app.route('/api/morador/meus-dados', methods=['GET', 'PUT'])
def gerenciar_proprio_cadastro():
    p = obter_placeholder()
    morador_id = session.get('morador_id')
    if not morador_id: return jsonify({"erro": "Sessão inválida"}), 401

    conexao = conectar_banco()
    cursor = conexao.cursor()

    if request.method == 'GET':
        cursor.execute(f'SELECT id, nome, celular, cpf, bloco, apartamento FROM moradores WHERE id = {p}', (morador_id,))
        m = cursor.fetchone()
        conexao.close()
        return jsonify(dict(m)) if m else (jsonify({"erro": "Não encontrado"}), 404)

    if request.method == 'PUT':
        dados = request.json or {}
        nome = dados.get('nome')
        celular = dados.get('celular')
        cpf_limpo = apenas_numeros(dados.get('cpf', ''))
        senha = dados.get('senha')

        if not validar_cpf(cpf_limpo):
            conexao.close()
            return jsonify({"erro": "CPF inválido!"}), 400

        try:
            if senha:
                cursor.execute(f'UPDATE moradores SET nome={p}, celular={p}, cpf={p}, senha={p} WHERE id={p}', (nome, celular, cpf_limpo, senha, morador_id))
            else:
                cursor.execute(f'UPDATE moradores SET nome={p}, celular={p}, cpf={p} WHERE id={p}', (nome, celular, cpf_limpo, morador_id))
            conexao.commit()
            return jsonify({"mensagem": "Dados atualizados com sucesso!"}), 200
        except Exception:
            return jsonify({"erro": "CPF já em uso!"}), 400
        finally:
            conexao.close()

@app.route('/api/admin/porteiros', methods=['GET'])
def listar_porteiros_admin():
    if not session.get('admin_logado'): return jsonify({"erro": "Negado"}), 403
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('SELECT p.id, p.nome, p.matricula, c.nome as condominio_nome FROM porteiros p LEFT JOIN condominios c ON p.condominio_id = c.id')
    lista = [dict(row) for row in cursor.fetchall()]
    conexao.close()
    return jsonify(lista), 200

@app.route('/api/admin/porteiros/<int:id>', methods=['DELETE', 'PUT'])
def gerenciar_porteiro_admin(id):
    p = obter_placeholder()
    if not session.get('admin_logado'): return jsonify({"erro": "Negado"}), 403
    conexao = conectar_banco()
    cursor = conexao.cursor()
    if request.method == 'DELETE':
        cursor.execute(f'DELETE FROM porteiros WHERE id = {p}', (id,))
        conexao.commit()
        conexao.close()
        return jsonify({"mensagem": "Removido!"}), 200
    if request.method == 'PUT':
        dados = request.json or {}
        cursor.execute(f'UPDATE porteiros SET nome={p}, matricula={p} WHERE id={p}', (dados.get('nome'), dados.get('matricula'), id))
        conexao.commit()
        conexao.close()
        return jsonify({"mensagem": "Atualizado!"}), 200

@app.route('/api/admin/moradores', methods=['GET'])
def listar_moradores_admin():
    if not session.get('admin_logado'): return jsonify({"erro": "Negado"}), 403
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('SELECT id, nome, celular, cpf, bloco, apartamento FROM moradores ORDER BY bloco, apartamento')
    lista = [dict(row) for row in cursor.fetchall()]
    conexao.close()
    return jsonify(lista), 200

@app.route('/api/admin/moradores/<int:id>', methods=['DELETE', 'PUT'])
def gerenciar_morador_admin(id):
    p = obter_placeholder()
    if not session.get('admin_logado'): return jsonify({"erro": "Negado"}), 403
    conexao = conectar_banco()
    cursor = conexao.cursor()
    if request.method == 'DELETE':
        cursor.execute(f'DELETE FROM moradores WHERE id = {p}', (id,))
        conexao.commit()
        conexao.close()
        return jsonify({"mensagem": "Removido!"}), 200
    if request.method == 'PUT':
        dados = request.json or {}
        cursor.execute(f'UPDATE moradores SET nome={p}, celular={p}, cpf={p}, bloco={p}, apartamento={p} WHERE id={p}',
                       (dados.get('nome'), dados.get('celular'), apenas_numeros(dados.get('cpf')), dados.get('bloco'), dados.get('apartamento'), id))
        conexao.commit()
        conexao.close()
        return jsonify({"mensagem": "Atualizado!"}), 200

@app.route('/api/moradores/buscar/<int:bloco>/<int:apartamento>', methods=['GET'])
def buscar_moradores_unidade(bloco, apartamento):
    p = obter_placeholder()
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute(f'SELECT id, nome, celular FROM moradores WHERE bloco = {p} AND apartamento = {p}', (bloco, apartamento))
    moradores = [dict(row) for row in cursor.fetchall()]
    conexao.close()
    return jsonify(moradores), 200

# REGISTRO E CONSULTA DE ENCOMENDAS
@app.route('/api/encomendas', methods=['POST'])
def registrar_encomenda():
    p = obter_placeholder()
    if not session.get('porteiro_logado') and not session.get('admin_logado'): 
        return jsonify({"erro": "Sessão expirada!"}), 401

    bloco = request.form.get('bloco')
    apartamento = request.form.get('apartamento')
    morador_id = request.form.get('morador_id')
    tipo = request.form.get('tipo_encomenda')
    empresa = request.form.get('empresa_entrega', 'Outros')
    porteiro_nome = session.get('porteiro_nome', 'Administração')
    condominio_id = session.get('condominio_id', 1)
    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")

    foto_caminho = None
    if 'foto' in request.files:
        file = request.files['foto']
        if file and arquivo_permitido(file.filename):
            nome_arquivo = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_arquivo))
            foto_caminho = f"/uploads/{nome_arquivo}"

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        protocolo = gerar_protocolo_anual(cursor)
        cursor.execute(f'''
            INSERT INTO encomendas (condominio_id, protocolo_anual, bloco, apartamento, morador_id, tipo_encomenda, empresa_entrega, porteiro_nome, foto_url, data_recebimento)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
        ''', (condominio_id, protocolo, bloco, apartamento, morador_id, tipo, empresa, porteiro_nome, foto_caminho, data_atual))
        conexao.commit()

        cursor.execute(f'SELECT nome, celular FROM moradores WHERE id = {p}', (morador_id,))
        morador = cursor.fetchone()

        return jsonify({
            "mensagem": f"Encomenda registrada! Protocolo: #{protocolo}",
            "protocolo": protocolo,
            "empresa": empresa,
            "porteiro_nome": porteiro_nome,
            "celular_morador": morador['celular'] if morador else None,
            "nome_morador": morador['nome'] if morador else "Morador",
            "foto_url": foto_caminho
        }), 201
    except Exception as e:
        return jsonify({"erro": str(e)}), 400
    finally:
        conexao.close()

@app.route('/api/encomendas/busca', methods=['GET'])
def buscar_encomendas_portaria():
    termo = request.args.get('q', '').strip()
    conexao = conectar_banco()
    cursor = conexao.cursor()
    sql = '''
        SELECT e.id, e.protocolo_anual, e.bloco, e.apartamento, e.tipo_encomenda, 
               e.empresa_entrega, e.porteiro_nome, e.data_recebimento, e.status, 
               e.retirado_por, e.data_retirada, e.foto_url, 
               m.nome as nome_morador, m.celular as celular_morador
        FROM encomendas e
        LEFT JOIN moradores m ON e.morador_id = m.id
        WHERE 1=1
    '''
    parametros = []
    if termo:
        p = obter_placeholder()
        sql += f" AND (m.nome LIKE {p} OR CAST(e.bloco AS TEXT) LIKE {p} OR CAST(e.apartamento AS TEXT) LIKE {p} OR e.protocolo_anual LIKE {p} OR e.empresa_entrega LIKE {p})"
        parametros.extend([f"%{termo}%", f"%{termo}%", f"%{termo}%", f"%{termo}%", f"%{termo}%"])

    sql += " ORDER BY e.id DESC"
    cursor.execute(sql, parametros)
    encomendas = [dict(row) for row in cursor.fetchall()]
    conexao.close()
    return jsonify(encomendas), 200

# VISIBILIDADE COMPARTILHADA DA UNIDADE (BLOCO E APARTAMENTO)
@app.route('/api/morador/minhas-encomendas', methods=['GET'])
def buscar_minhas_encomendas():
    p = obter_placeholder()
    morador_id = session.get('morador_id')
    if not morador_id: return jsonify({"erro": "Sessão inválida"}), 401

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute(f'SELECT bloco, apartamento FROM moradores WHERE id = {p}', (morador_id,))
    morador = cursor.fetchone()

    if not morador:
        conexao.close()
        return jsonify({"erro": "Morador não encontrado"}), 404

    bloco = morador['bloco']
    apartamento = morador['apartamento']

    cursor.execute(f'''
        SELECT e.id, e.protocolo_anual, e.tipo_encomenda, e.empresa_entrega, 
               e.data_recebimento, e.status, e.retirado_por, e.data_retirada, e.foto_url,
               m.nome as nome_destinatario
        FROM encomendas e
        LEFT JOIN moradores m ON e.morador_id = m.id
        WHERE e.bloco = {p} AND e.apartamento = {p}
        ORDER BY e.id DESC
    ''', (bloco, apartamento))

    encomendas = [dict(row) for row in cursor.fetchall()]
    conexao.close()
    return jsonify(encomendas), 200

@app.route('/api/encomendas/<int:id_encomenda>/retirar', methods=['PUT'])
def dar_baixa_encomenda(id_encomenda):
    p = obter_placeholder()
    dados = request.json or {}
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute(f'''
        UPDATE encomendas SET status = 'Entregue', retirado_por = {p}, data_retirada = {p} WHERE id = {p}
    ''', (dados.get('retirado_por', 'Próprio Morador'), datetime.now().strftime("%d/%m/%Y %H:%M"), id_encomenda))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Entrega confirmada!"}), 200

@app.route('/api/admin/encomendas/<int:id>', methods=['DELETE', 'PUT'])
def gerenciar_encomenda_admin(id):
    p = obter_placeholder()
    if not session.get('admin_logado'): return jsonify({"erro": "Negado"}), 403
    conexao = conectar_banco()
    cursor = conexao.cursor()
    if request.method == 'DELETE':
        cursor.execute(f'DELETE FROM encomendas WHERE id = {p}', (id,))
        conexao.commit()
        conexao.close()
        return jsonify({"mensagem": "Excluído!"}), 200
    if request.method == 'PUT':
        dados = request.json or {}
        cursor.execute(f'UPDATE encomendas SET empresa_entrega={p}, status={p} WHERE id={p}', (dados.get('empresa_entrega'), dados.get('status'), id))
        conexao.commit()
        conexao.close()
        return jsonify({"mensagem": "Atualizado!"}), 200

if __name__ == '__main__':
    # REMOVIDA QUALQUER EXECUÇÃO DE RECRIAÇÃO DE BANCO LOCAL PARA EVITAR PERDA DE DADOS
    app.run(debug=True, host='0.0.0.0', port=5000)
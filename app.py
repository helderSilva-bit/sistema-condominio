import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session
from flask_cors import CORS
from werkzeug.utils import secure_filename
import init_db

app = Flask(__name__)
app.secret_key = 'chave_secreta_segura_condominio'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)  # Expira por inatividade (standby) em 5 min
CORS(app)

DATABASE = 'condominio.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

ADMIN_USUARIO = "admin"
ADMIN_SENHA = "admin123condominio"

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def conectar_banco():
    conexao = sqlite3.connect(DATABASE)
    conexao.row_factory = sqlite3.Row
    return conexao

def arquivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def gerar_protocolo_anual(cursor):
    ano_atual = datetime.now().strftime("%Y")
    cursor.execute('''
        SELECT protocolo_anual FROM encomendas 
        WHERE protocolo_anual LIKE ? 
        ORDER BY id DESC LIMIT 1
    ''', (f"{ano_atual}-%",))
    ultima = cursor.fetchone()
    
    if ultima:
        ultimo_num = int(ultima['protocolo_anual'].split('-')[1])
        novo_num = ultimo_num + 1
    else:
        novo_num = 1
        
    return f"{ano_atual}-{novo_num:04d}"

@app.before_request
def checar_inatividade():
    session.permanent = True

@app.after_request
def aplicar_headers_seguranca(response):
    # Evita que o navegador salve a senha ou mantenha o login ao voltar
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/uploads/<filename>')
def imagem_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ROTAS DE PÁGINAS
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login-porteiro')
def login_porteiro_page():
    return render_template('login_porteiro.html')

@app.route('/login-admin')
def login_admin_page():
    return render_template('login_admin.html')

@app.route('/cadastro-porteiro')
def cadastro_porteiro_page():
    if not session.get('admin_logado'):
        return redirect(url_for('login_admin_page'))
    return render_template('cadastro_porteiro.html')

@app.route('/login-morador')
def login_morador_page():
    return render_template('login_morador.html')

@app.route('/cadastro')
def pagina_cadastro():
    return render_template('cadastro.html')

@app.route('/portaria')
def pagina_portaria():
    if not session.get('porteiro_logado'):
        return redirect(url_for('login_porteiro_page'))
    return render_template('portaria.html')

@app.route('/morador')
def pagina_morador():
    if not session.get('morador_id'):
        return redirect(url_for('login_morador_page'))
    return render_template('morador.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# LOGINS
@app.route('/api/admin/login', methods=['POST'])
def login_admin():
    dados = request.json
    usuario = dados.get('usuario')
    senha = dados.get('senha')

    if usuario == ADMIN_USUARIO and senha == ADMIN_SENHA:
        session.clear()
        session['admin_logado'] = True
        return jsonify({"sucesso": True}), 200
    return jsonify({"erro": "Usuário ou senha de Administrador inválidos!"}), 401

@app.route('/api/porteiro/login', methods=['POST'])
def login_porteiro():
    dados = request.json
    matricula = dados.get('matricula', '').strip()
    senha = dados.get('senha')

    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('SELECT * FROM porteiros WHERE matricula = ? AND senha = ?', (matricula, senha))
    porteiro = cursor.fetchone()
    conexao.close()

    if porteiro:
        session.clear()
        session['porteiro_logado'] = True
        session['porteiro_id'] = porteiro['id']
        session['porteiro_nome'] = porteiro['nome']
        return jsonify({"sucesso": True, "nome": porteiro['nome']}), 200
    return jsonify({"erro": "Matrícula ou Senha de porteiro incorretos!"}), 401

@app.route('/api/morador/login', methods=['POST'])
def login_morador():
    dados = request.json
    cpf = dados.get('cpf', '').strip()
    senha = dados.get('senha')

    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('SELECT * FROM moradores WHERE cpf = ? AND senha = ?', (cpf, senha))
    morador = cursor.fetchone()

    if not morador:
        conexao.close()
        return jsonify({"erro": "CPF ou Senha incorretos!"}), 401

    morador_dict = dict(morador)
    session.clear()
    session['morador_id'] = morador_dict['id']

    cursor.execute('''
        SELECT e.*, m.nome as nome_destinatario 
        FROM encomendas e
        LEFT JOIN moradores m ON e.morador_id = m.id
        WHERE e.bloco = ? AND e.apartamento = ?
        ORDER BY e.id DESC
    ''', (morador_dict['bloco'], morador_dict['apartamento']))
    encomendas = [dict(row) for row in cursor.fetchall()]

    conexao.close()

    return jsonify({
        "sucesso": True,
        "morador": morador_dict,
        "encomendas": encomendas
    }), 200

# CADASTRO DE PORTEIRO POR MATRÍCULA
@app.route('/api/porteiro/cadastrar', methods=['POST'])
def cadastrar_porteiro():
    if not session.get('admin_logado'):
        return jsonify({"erro": "Apenas o Administrador pode cadastrar novos porteiros!"}), 403

    dados = request.json
    nome = dados.get('nome')
    matricula = dados.get('matricula', '').strip()
    senha = dados.get('senha')

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:
        cursor.execute('INSERT INTO porteiros (nome, matricula, senha) VALUES (?, ?, ?)', (nome, matricula, senha))
        conexao.commit()
        return jsonify({"mensagem": "Porteiro cadastrado com sucesso!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"erro": "Matrícula de porteiro já cadastrada!"}), 400
    except Exception as e:
        return jsonify({"erro": str(e)}), 400
    finally:
        conexao.close()

@app.route('/api/moradores/cadastrar', methods=['POST'])
def cadastrar_morador():
    dados = request.json
    nome = dados.get('nome')
    celular = dados.get('celular')
    cpf = dados.get('cpf', '').strip()
    senha = dados.get('senha')
    bloco = int(dados.get('bloco'))
    apartamento = int(dados.get('apartamento'))

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:
        cursor.execute('SELECT COUNT(*) as total FROM moradores WHERE bloco = ? AND apartamento = ?', (bloco, apartamento))
        qtd = cursor.fetchone()['total']

        if qtd >= 4:
            return jsonify({"erro": "Limite atingido! Este apartamento já possui 4 moradores cadastrados."}), 400

        cursor.execute('''
            INSERT INTO moradores (nome, celular, cpf, senha, bloco, apartamento)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (nome, celular, cpf, senha, bloco, apartamento))
        conexao.commit()
        return jsonify({"mensagem": "Morador cadastrado com sucesso!"}), 201

    except sqlite3.IntegrityError:
        return jsonify({"erro": "CPF já cadastrado!"}), 400
    except Exception as e:
        return jsonify({"erro": str(e)}), 400
    finally:
        conexao.close()

@app.route('/api/moradores/buscar/<int:bloco>/<int:apartamento>', methods=['GET'])
def buscar_moradores_unidade(bloco, apartamento):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('SELECT id, nome, celular FROM moradores WHERE bloco = ? AND apartamento = ?', (bloco, apartamento))
    moradores = [dict(row) for row in cursor.fetchall()]
    conexao.close()
    return jsonify(moradores), 200

# REGISTRAR ENCOMENDA
@app.route('/api/encomendas', methods=['POST'])
def registrar_encomenda():
    if not session.get('porteiro_logado'):
        return jsonify({"erro": "Sessão expirada. Faça login novamente!"}), 401

    bloco = request.form.get('bloco')
    apartamento = request.form.get('apartamento')
    morador_id = request.form.get('morador_id')
    tipo = request.form.get('tipo_encomenda')
    empresa = request.form.get('empresa_entrega', 'Outros')
    
    porteiro_id = session.get('porteiro_id')
    porteiro_nome = session.get('porteiro_nome', 'Portaria')
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

        cursor.execute('''
            INSERT INTO encomendas (protocolo_anual, bloco, apartamento, morador_id, tipo_encomenda, empresa_entrega, porteiro_id, porteiro_nome, foto_url, data_recebimento)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (protocolo, bloco, apartamento, morador_id, tipo, empresa, porteiro_id, porteiro_nome, foto_caminho, data_atual))
        conexao.commit()

        cursor.execute('SELECT nome, celular FROM moradores WHERE id = ?', (morador_id,))
        morador = cursor.fetchone()

        celular = morador['celular'] if morador else None
        nome_morador = morador['nome'] if morador else "Morador"

        return jsonify({
            "mensagem": f"Encomenda registrada por {porteiro_nome}! Protocolo: #{protocolo}",
            "protocolo": protocolo,
            "empresa": empresa,
            "porteiro_nome": porteiro_nome,
            "celular_morador": celular,
            "nome_morador": nome_morador
        }), 201

    except Exception as e:
        return jsonify({"erro": f"Erro interno ao salvar: {str(e)}"}), 400
    finally:
        conexao.close()

# CONSULTA GLOBAL DA PORTARIA
@app.route('/api/encomendas/busca', methods=['GET'])
def buscar_encomendas_portaria():
    termo = request.args.get('q', '').strip()
    status_filtro = request.args.get('status', 'Todos')

    conexao = conectar_banco()
    cursor = conexao.cursor()

    sql = '''
        SELECT e.*, m.nome as nome_morador 
        FROM encomendas e
        LEFT JOIN moradores m ON e.morador_id = m.id
        WHERE 1=1
    '''
    parametros = []

    if termo:
        sql += " AND (m.nome LIKE ? OR e.bloco LIKE ? OR e.apartamento LIKE ? OR e.protocolo_anual LIKE ? OR e.empresa_entrega LIKE ? OR e.porteiro_nome LIKE ?)"
        parametros.extend([f"%{termo}%", f"%{termo}%", f"%{termo}%", f"%{termo}%", f"%{termo}%", f"%{termo}%"])

    if status_filtro in ['Pendente', 'Entregue']:
        sql += " AND e.status = ?"
        parametros.append(status_filtro)

    sql += " ORDER BY e.id DESC"

    cursor.execute(sql, parametros)
    encomendas = [dict(row) for row in cursor.fetchall()]
    conexao.close()

    return jsonify(encomendas), 200

@app.route('/api/encomendas/<int:id_encomenda>/retirar', methods=['PUT'])
def dar_baixa_encomenda(id_encomenda):
    dados = request.json
    retirado_por = dados.get('retirado_por', 'Próprio Morador')
    data_retirada = datetime.now().strftime("%d/%m/%Y %H:%M")

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute('''
        UPDATE encomendas 
        SET status = 'Entregue', retirado_por = ?, data_retirada = ?
        WHERE id = ?
    ''', (retirado_por, data_retirada, id_encomenda))
    
    conexao.commit()
    conexao.close()

    return jsonify({"mensagem": "Entrega confirmada com sucesso!"}), 200

# ROTA FORÇADA PARA RECONSTRUÇÃO COMPLETA DA BASE DE DADOS NA NUVEM
@app.route('/reconstruir-banco-agora-99')
def reconstruir_banco_agora():
    conexao = sqlite3.connect(DATABASE)
    cursor = conexao.cursor()
    
    cursor.execute('DROP TABLE IF EXISTS encomendas')
    cursor.execute('DROP TABLE IF EXISTS moradores')
    cursor.execute('DROP TABLE IF EXISTS porteiros')
    
    cursor.execute('''
        CREATE TABLE moradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            celular TEXT NOT NULL,
            cpf TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            bloco INTEGER NOT NULL,
            apartamento INTEGER NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE porteiros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            matricula TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE encomendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            protocolo_anual TEXT UNIQUE NOT NULL,
            bloco INTEGER NOT NULL,
            apartamento INTEGER NOT NULL,
            morador_id INTEGER,
            tipo_encomenda TEXT NOT NULL,
            empresa_entrega TEXT NOT NULL,
            porteiro_id INTEGER,
            porteiro_nome TEXT,
            foto_url TEXT,
            data_recebimento TEXT NOT NULL,
            status TEXT DEFAULT 'Pendente',
            retirado_por TEXT,
            data_retirada TEXT,
            FOREIGN KEY (morador_id) REFERENCES moradores(id),
            FOREIGN KEY (porteiro_id) REFERENCES porteiros(id)
        )
    ''')
    
    conexao.commit()
    conexao.close()
    
    return "<h1>✅ Base de dados do Render totalmente limpa e recriada com a coluna MATRICULA!</h1>"

if __name__ == '__main__':
    init_db.criar_banco()
    app.run(debug=True, host='0.0.0.0', port=5000)
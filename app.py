import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session
from flask_cors import CORS
from werkzeug.utils import secure_filename
import init_db

app = Flask(__name__)
app.secret_key = 'chave_secreta_segura_condominio'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)
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

def verificar_assinatura_ativa():
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('SELECT data_expiracao FROM assinatura ORDER BY id DESC LIMIT 1')
    sub = cursor.fetchone()
    conexao.close()

    if not sub:
        return False

    data_exp = datetime.strptime(sub['data_expiracao'], "%Y-%m-%d")
    return datetime.now() <= data_exp

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
def index():
    return render_template('index.html')

@app.route('/login-porteiro')
def login_porteiro_page():
    return render_template('login_porteiro.html')

@app.route('/login-admin')
def login_admin_page():
    return render_template('login_admin.html')

@app.route('/admin-dashboard')
def admin_dashboard_page():
    if not session.get('admin_logado'):
        return redirect(url_for('login_admin_page'))
    return render_template('admin_dashboard.html')

@app.route('/cadastro-porteiro')
def cadastro_porteiro_page():
    if not session.get('admin_logado'):
        return redirect(url_for('login_admin_page'))
    return render_template('cadastro_porteiro.html')

@app.route('/login-morador')
def login_morador_page():
    return render_template('login_morador.html')

@app.route('/meu-cadastro')
def meu_cadastro_page():
    if not session.get('morador_id'):
        return redirect(url_for('login_morador_page'))
    return render_template('meu_cadastro.html')

@app.route('/cadastro')
def pagina_cadastro():
    return render_template('cadastro.html')

@app.route('/portaria')
def pagina_portaria():
    if not session.get('porteiro_logado'):
        return redirect(url_for('login_porteiro_page'))
    if not verificar_assinatura_ativa():
        session.clear()
        return "<h1>⚠️ A assinatura do sistema está expirada. Entre em contacto com a administração!</h1>", 403
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

# APIS DE LOGINS
@app.route('/api/admin/login', methods=['POST'])
def login_admin():
    dados = request.json
    if dados.get('usuario') == ADMIN_USUARIO and dados.get('senha') == ADMIN_SENHA:
        session.clear()
        session['admin_logado'] = True
        return jsonify({"sucesso": True}), 200
    return jsonify({"erro": "Usuário ou senha de Administrador inválidos!"}), 401

@app.route('/api/porteiro/login', methods=['POST'])
def login_porteiro():
    if not verificar_assinatura_ativa():
        return jsonify({"erro": "Assinatura do sistema expirada! Contacte a administração."}), 403

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
    return jsonify({"erro": "Matrícula ou Senha incorretas!"}), 401

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
    conexao.close()

    return jsonify({"sucesso": True, "morador": morador_dict}), 200

# GERENCIAMENTO DE ASSINATURAS
@app.route('/api/admin/assinatura', methods=['GET', 'POST'])
def gerenciar_assinatura():
    if not session.get('admin_logado'):
        return jsonify({"erro": "Acesso negado!"}), 403

    conexao = conectar_banco()
    cursor = conexao.cursor()

    if request.method == 'GET':
        cursor.execute('SELECT data_expiracao, status FROM assinatura ORDER BY id DESC LIMIT 1')
        sub = cursor.fetchone()
        conexao.close()
        
        if not sub:
            return jsonify({"data_expiracao": "N/A", "dias_restantes": 0, "ativo": False}), 200

        data_exp = datetime.strptime(sub['data_expiracao'], "%Y-%m-%d")
        dias_restantes = (data_exp - datetime.now()).days + 1
        
        return jsonify({
            "data_expiracao": data_exp.strftime("%d/%m/%Y"),
            "dias_restantes": max(0, dias_restantes),
            "ativo": dias_restantes > 0
        }), 200

    if request.method == 'POST':
        dados = request.json
        plano = dados.get('plano')
        
        dias_add = 30
        if plano == '6meses':
            dias_add = 180
        elif plano == '1ano':
            dias_add = 365

        cursor.execute('SELECT data_expiracao FROM assinatura ORDER BY id DESC LIMIT 1')
        sub = cursor.fetchone()
        
        if sub:
            data_atual_exp = datetime.strptime(sub['data_expiracao'], "%Y-%m-%d")
            base_calc = max(datetime.now(), data_atual_exp)
        else:
            base_calc = datetime.now()

        nova_expiracao = (base_calc + timedelta(days=dias_add)).strftime("%Y-%m-%d")

        cursor.execute('DELETE FROM assinatura')
        cursor.execute('INSERT INTO assinatura (data_expiracao, status) VALUES (?, ?)', (nova_expiracao, 'Ativo'))
        conexao.commit()
        conexao.close()

        return jsonify({"mensagem": f"Plano liberado com sucesso! Nova validade: {datetime.strptime(nova_expiracao, '%Y-%m-%d').strftime('%d/%m/%Y')}"}), 200

# OPERAÇÕES DO PAINEL ADMIN
@app.route('/api/admin/porteiros', methods=['GET'])
def listar_porteiros_admin():
    if not session.get('admin_logado'): return jsonify({"erro": "Negado"}), 403
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('SELECT id, nome, matricula FROM porteiros')
    lista = [dict(row) for row in cursor.fetchall()]
    conexao.close()
    return jsonify(lista), 200

@app.route('/api/admin/porteiros/<int:id>', methods=['DELETE'])
def gerenciar_porteiro_admin(id):
    if not session.get('admin_logado'): return jsonify({"erro": "Negado"}), 403
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('DELETE FROM porteiros WHERE id = ?', (id,))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Porteiro removido!"}), 200

@app.route('/api/admin/moradores', methods=['GET'])
def listar_moradores_admin():
    if not session.get('admin_logado'): return jsonify({"erro": "Negado"}), 403
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('SELECT id, nome, celular, cpf, bloco, apartamento FROM moradores ORDER BY bloco, apartamento')
    lista = [dict(row) for row in cursor.fetchall()]
    conexao.close()
    return jsonify(lista), 200

@app.route('/api/admin/moradores/<int:id>', methods=['DELETE'])
def gerenciar_morador_admin(id):
    if not session.get('admin_logado'): return jsonify({"erro": "Negado"}), 403
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('DELETE FROM moradores WHERE id = ?', (id,))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Morador removido!"}), 200

@app.route('/api/admin/encomendas/<int:id>', methods=['DELETE'])
def excluir_encomenda_admin(id):
    if not session.get('admin_logado'): return jsonify({"erro": "Negado"}), 403
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('DELETE FROM encomendas WHERE id = ?', (id,))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Encomenda excluída!"}), 200

# CADASTROS E RECEPÇÃO
@app.route('/api/porteiro/cadastrar', methods=['POST'])
def cadastrar_porteiro():
    if not session.get('admin_logado'):
        return jsonify({"erro": "Apenas o Administrador pode cadastrar porteiros!"}), 403

    dados = request.json
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute('INSERT INTO porteiros (nome, matricula, senha) VALUES (?, ?, ?)', 
                       (dados.get('nome'), dados.get('matricula', '').strip(), dados.get('senha')))
        conexao.commit()
        return jsonify({"mensagem": "Porteiro cadastrado com sucesso!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"erro": "Matrícula já cadastrada!"}), 400
    finally:
        conexao.close()

@app.route('/api/moradores/cadastrar', methods=['POST'])
def cadastrar_morador():
    dados = request.json
    bloco = int(dados.get('bloco'))
    apartamento = int(dados.get('apartamento'))

    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute('SELECT COUNT(*) as total FROM moradores WHERE bloco = ? AND apartamento = ?', (bloco, apartamento))
        if cursor.fetchone()['total'] >= 4:
            return jsonify({"erro": "Limite de 4 moradores por apartamento atingido!"}), 400

        cursor.execute('''
            INSERT INTO moradores (nome, celular, cpf, senha, bloco, apartamento)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (dados.get('nome'), dados.get('celular'), dados.get('cpf', '').strip(), dados.get('senha'), bloco, apartamento))
        conexao.commit()
        return jsonify({"mensagem": "Morador cadastrado com sucesso!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"erro": "CPF já cadastrado!"}), 400
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

@app.route('/api/encomendas', methods=['POST'])
def registrar_encomenda():
    if not session.get('porteiro_logado') and not session.get('admin_logado'):
        return jsonify({"erro": "Sessão expirada. Faça login!"}), 401

    bloco = request.form.get('bloco')
    apartamento = request.form.get('apartamento')
    morador_id = request.form.get('morador_id')
    tipo = request.form.get('tipo_encomenda')
    empresa = request.form.get('empresa_entrega', 'Outros')
    porteiro_nome = session.get('porteiro_nome', 'Administração')
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
            INSERT INTO encomendas (protocolo_anual, bloco, apartamento, morador_id, tipo_encomenda, empresa_entrega, porteiro_nome, foto_url, data_recebimento)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (protocolo, bloco, apartamento, morador_id, tipo, empresa, porteiro_nome, foto_caminho, data_atual))
        conexao.commit()

        cursor.execute('SELECT nome, celular FROM moradores WHERE id = ?', (morador_id,))
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
        SELECT e.*, m.nome as nome_morador 
        FROM encomendas e
        LEFT JOIN moradores m ON e.morador_id = m.id
        WHERE 1=1
    '''
    parametros = []
    if termo:
        sql += " AND (m.nome LIKE ? OR e.bloco LIKE ? OR e.apartamento LIKE ? OR e.protocolo_anual LIKE ? OR e.empresa_entrega LIKE ?)"
        parametros.extend([f"%{termo}%", f"%{termo}%", f"%{termo}%", f"%{termo}%", f"%{termo}%"])

    sql += " ORDER BY e.id DESC"
    cursor.execute(sql, parametros)
    encomendas = [dict(row) for row in cursor.fetchall()]
    conexao.close()
    return jsonify(encomendas), 200

@app.route('/api/encomendas/<int:id_encomenda>/retirar', methods=['PUT'])
def dar_baixa_encomenda(id_encomenda):
    dados = request.json
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('''
        UPDATE encomendas SET status = 'Entregue', retirado_por = ?, data_retirada = ? WHERE id = ?
    ''', (dados.get('retirado_por', 'Próprio Morador'), datetime.now().strftime("%d/%m/%Y %H:%M"), id_encomenda))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Entrega confirmada!"}), 200

# ROTA DE RECONSTRUÇÃO DO BANCO DE DADOS
@app.route('/reconstruir-banco-agora-99')
def reconstruir_banco_agora():
    init_db.criar_banco()
    return "<h1>✅ Base de dados limpa e pronta para uso com o Painel Admin!</h1>"

if __name__ == '__main__':
    init_db.criar_banco()
    app.run(debug=True, host='0.0.0.0', port=5000)
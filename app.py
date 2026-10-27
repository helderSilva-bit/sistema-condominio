import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

DATABASE = 'condominio.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def conectar_banco():
    conexao = sqlite3.connect(DATABASE)
    conexao.row_factory = sqlite3.Row
    return conexao

def arquivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def gerar_protocolo_diario(cursor):
    hoje_prefixo = datetime.now().strftime("%Y%m%d")
    cursor.execute('''
        SELECT protocolo_diario FROM encomendas 
        WHERE protocolo_diario LIKE ? 
        ORDER BY id DESC LIMIT 1
    ''', (f"{hoje_prefixo}-%",))
    ultima = cursor.fetchone()
    
    if ultima:
        ultimo_num = int(ultima['protocolo_diario'].split('-')[1])
        novo_num = ultimo_num + 1
    else:
        novo_num = 1
        
    return f"{hoje_prefixo}-{novo_num:03d}"

@app.route('/uploads/<filename>')
def imagem_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ROTAS DE PÁGINAS (HTML)
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login-porteiro')
def login_porteiro_page():
    return render_template('login_porteiro.html')

@app.route('/cadastro-porteiro')
def cadastro_porteiro_page():
    return render_template('cadastro_porteiro.html')

@app.route('/login-morador')
def login_morador_page():
    return render_template('login_morador.html')

@app.route('/cadastro')
def pagina_cadastro():
    return render_template('cadastro.html')

@app.route('/portaria')
def pagina_portaria():
    return render_template('portaria.html')

@app.route('/morador')
def pagina_morador():
    return render_template('morador.html')

# API: Cadastro de Morador
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

# API: Cadastro de Porteiro
@app.route('/api/porteiro/cadastrar', methods=['POST'])
def cadastrar_porteiro():
    dados = request.json
    nome = dados.get('nome')
    cpf = dados.get('cpf', '').strip()
    senha = dados.get('senha')

    conexao = conectar_banco()
    cursor = conexao.cursor()

    try:
        cursor.execute('''
            INSERT INTO porteiros (nome, cpf, senha)
            VALUES (?, ?, ?)
        ''', (nome, cpf, senha))
        conexao.commit()
        return jsonify({"mensagem": "Porteiro cadastrado com sucesso!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"erro": "CPF de porteiro já cadastrado!"}), 400
    except Exception as e:
        return jsonify({"erro": str(e)}), 400
    finally:
        conexao.close()

# API: Login de Porteiro
@app.route('/api/porteiro/login', methods=['POST'])
def login_porteiro():
    dados = request.json
    cpf = dados.get('cpf', '').strip()
    senha = dados.get('senha')

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute('SELECT * FROM porteiros WHERE cpf = ? AND senha = ?', (cpf, senha))
    porteiro = cursor.fetchone()
    conexao.close()

    if porteiro:
        return jsonify({"sucesso": True, "nome": porteiro['nome']}), 200
    return jsonify({"erro": "CPF ou Senha de porteiro incorretos!"}), 401

# API: Login de Morador
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

# API: Buscar moradores por Bloco/Apartamento
@app.route('/api/moradores/buscar/<int:bloco>/<int:apartamento>', methods=['GET'])
def buscar_moradores_unidade(bloco, apartamento):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    cursor.execute('SELECT id, nome, celular FROM moradores WHERE bloco = ? AND apartamento = ?', (bloco, apartamento))
    moradores = [dict(row) for row in cursor.fetchall()]
    conexao.close()
    return jsonify(moradores), 200

# API: Registrar Encomenda
@app.route('/api/encomendas', methods=['POST'])
def registrar_encomenda():
    bloco = request.form.get('bloco')
    apartamento = request.form.get('apartamento')
    morador_id = request.form.get('morador_id')
    tipo = request.form.get('tipo_encomenda')
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
        protocolo = gerar_protocolo_diario(cursor)

        cursor.execute('''
            INSERT INTO encomendas (protocolo_diario, bloco, apartamento, morador_id, tipo_encomenda, foto_url, data_recebimento)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (protocolo, bloco, apartamento, morador_id, tipo, foto_caminho, data_atual))
        conexao.commit()

        cursor.execute('SELECT nome, celular FROM moradores WHERE id = ?', (morador_id,))
        morador = cursor.fetchone()

        celular = morador['celular'] if morador else None
        nome_morador = morador['nome'] if morador else "Morador"

        return jsonify({
            "mensagem": f"Encomenda registrada para {nome_morador}! Protocolo: #{protocolo}",
            "protocolo": protocolo,
            "celular_morador": celular,
            "nome_morador": nome_morador
        }), 201

    except Exception as e:
        return jsonify({"erro": str(e)}), 400
    finally:
        conexao.close()

# API: Buscar Encomendas na Portaria
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
        sql += " AND (m.nome LIKE ? OR e.bloco LIKE ? OR e.apartamento LIKE ? OR e.protocolo_diario LIKE ?)"
        parametros.extend([f"%{termo}%", f"%{termo}%", f"%{termo}%", f"%{termo}%"])

    if status_filtro in ['Pendente', 'Entregue']:
        sql += " AND e.status = ?"
        parametros.append(status_filtro)

    sql += " ORDER BY e.id DESC"

    cursor.execute(sql, parametros)
    encomendas = [dict(row) for row in cursor.fetchall()]
    conexao.close()

    return jsonify(encomendas), 200

# API: Dar Baixa em Encomenda
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
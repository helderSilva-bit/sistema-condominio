import sqlite3
from datetime import datetime, timedelta

def criar_banco():
    conexao = sqlite3.connect('condominio.db')
    cursor = conexao.cursor()

    # Elimina tabelas antigas para recriar com a nova estrutura de clientes
    cursor.execute('DROP TABLE IF EXISTS encomendas')
    cursor.execute('DROP TABLE IF EXISTS moradores')
    cursor.execute('DROP TABLE IF EXISTS porteiros')
    cursor.execute('DROP TABLE IF EXISTS condominios')

    # Tabela de Clientes / Condomínios com validade individual
    cursor.execute('''
        CREATE TABLE condominios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cnpj_cpf TEXT UNIQUE,
            data_expiracao TEXT NOT NULL,
            status TEXT DEFAULT 'Ativo'
        )
    ''')

    # Tabela de Moradores
    cursor.execute('''
        CREATE TABLE moradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condominio_id INTEGER,
            nome TEXT NOT NULL,
            celular TEXT NOT NULL,
            cpf TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            bloco INTEGER NOT NULL,
            apartamento INTEGER NOT NULL,
            FOREIGN KEY (condominio_id) REFERENCES condominios(id)
        )
    ''')

    # Tabela de Porteiros
    cursor.execute('''
        CREATE TABLE porteiros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condominio_id INTEGER,
            nome TEXT NOT NULL,
            matricula TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            FOREIGN KEY (condominio_id) REFERENCES condominios(id)
        )
    ''')

    # Tabela de Encomendas
    cursor.execute('''
        CREATE TABLE encomendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condominio_id INTEGER,
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
            FOREIGN KEY (condominio_id) REFERENCES condominios(id),
            FOREIGN KEY (morador_id) REFERENCES moradores(id),
            FOREIGN KEY (porteiro_id) REFERENCES porteiros(id)
        )
    ''')

    # Insere um condomínio inicial padrão com 30 dias de teste
    exp_inicial = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    cursor.execute('INSERT INTO condominios (nome, cnpj_cpf, data_expiracao, status) VALUES (?, ?, ?, ?)',
                   ('Condomínio Padrão', '00000000000000', exp_inicial, 'Ativo'))

    conexao.commit()
    conexao.close()

if __name__ == '__main__':
    criar_banco()
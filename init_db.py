import sqlite3
from datetime import datetime, timedelta

def criar_banco():
    conexao = sqlite3.connect('condominio.db')
    cursor = conexao.cursor()

    # Elimina tabelas antigas para garantir a nova estrutura
    cursor.execute('DROP TABLE IF EXISTS encomendas')
    cursor.execute('DROP TABLE IF EXISTS moradores')
    cursor.execute('DROP TABLE IF EXISTS porteiros')
    cursor.execute('DROP TABLE IF EXISTS assinatura')

    # Tabela de Moradores
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

    # Tabela de Porteiros (Usa MATRICULA em vez de CPF)
    cursor.execute('''
        CREATE TABLE porteiros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            matricula TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    ''')

    # Tabela de Encomendas
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

    # Tabela de Assinatura do Condomínio
    cursor.execute('''
        CREATE TABLE assinatura (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_expiracao TEXT NOT NULL,
            status TEXT DEFAULT 'Ativo'
        )
    ''')

    # Insere uma assinatura inicial padrão de 30 dias de teste
    data_inicial = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    cursor.execute('INSERT INTO assinatura (data_expiracao, status) VALUES (?, ?)', (data_inicial, 'Ativo'))

    conexao.commit()
    conexao.close()

if __name__ == '__main__':
    criar_banco()
Python
import sqlite3

def criar_banco():
    conexao = sqlite3.connect('condominio.db')
    cursor = conexao.cursor()

    # Tabela de Moradores
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS moradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            celular TEXT NOT NULL,
            cpf TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            bloco INTEGER NOT NULL,
            apartamento INTEGER NOT NULL
        )
    ''')

    # Tabela de Porteiros
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS porteiros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cpf TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    ''')

    # Tabela de Encomendas (Com Empresa e Porteiro Responsavel)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS encomendas (
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

if __name__ == '__main__':
    criar_banco()
2. Ficheiro app.py
import sqlite3
import os

def criar_banco():
    if not os.path.exists('uploads'):
        os.makedirs('uploads')

    conexao = sqlite3.connect('condominio.db')
    cursor = conexao.cursor()

    print("⚙️ Criando banco de dados atualizado...")

    # 1. Tabela de Moradores (com senha e CPF)
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

    # 2. Tabela de Porteiros (cadastrados com sua própria senha)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS porteiros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cpf TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    ''')

    # 3. Tabela de Encomendas (vinculada ao morador_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS encomendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            protocolo_diario TEXT NOT NULL,
            bloco INTEGER NOT NULL,
            apartamento INTEGER NOT NULL,
            morador_id INTEGER,
            tipo_encomenda TEXT NOT NULL,
            foto_url TEXT,
            status TEXT NOT NULL DEFAULT 'Pendente',
            data_recebimento TEXT NOT NULL,
            data_retirada TEXT,
            retirado_por TEXT,
            FOREIGN KEY (morador_id) REFERENCES moradores (id)
        )
    ''')

    conexao.commit()
    conexao.close()
    print("✅ Banco de dados recriado com tabelas de Moradores, Porteiros e Encomendas!")

if __name__ == '__main__':
    criar_banco()
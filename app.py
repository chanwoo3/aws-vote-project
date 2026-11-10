import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)
DB_PATH = os.environ.get('DB_PATH', 'votes.db')


def connect_db():
    return sqlite3.connect(DB_PATH, timeout=10)


def init_db():
    with connect_db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS votes (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, count INTEGER NOT NULL DEFAULT 0)')
        for name in ['밴드 공연', '댄스 공연', '힙합 공연']:
            db.execute('INSERT OR IGNORE INTO votes (name) VALUES (?)', (name,))


@app.route('/')
def index():
    with connect_db() as db:
        votes = db.execute('SELECT id, name, count FROM votes ORDER BY id').fetchall()
    return render_template('index.html', votes=votes)


@app.route('/vote', methods=['POST'])
def vote():
    vote_id = request.form.get('vote_id', type=int)
    if vote_id is not None:
        with connect_db() as db:
            db.execute('UPDATE votes SET count = count + 1 WHERE id = ?', (vote_id,))
    return redirect(url_for('index'))


@app.route('/add', methods=['POST'])
def add():
    name = request.form.get('name', '').strip()
    if name and len(name) <= 50:
        with connect_db() as db:
            db.execute('INSERT OR IGNORE INTO votes (name) VALUES (?)', (name,))
    return redirect(url_for('index'))


@app.route('/api/health')
def health():
    return {'status': 'ok'}


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

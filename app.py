import hmac
import os
import sqlite3
from datetime import datetime
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
DB_PATH = os.environ.get('DB_PATH', 'votes.db')
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']


def connect_db():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout = 10000')
    return db


def init_db():
    with connect_db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            count INTEGER NOT NULL DEFAULT 0
        )''')
        columns = [row['name'] for row in db.execute('PRAGMA table_info(votes)')]
        if 'description' not in columns:
            db.execute("ALTER TABLE votes ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        for name in ['밴드 공연', '댄스 공연', '힙합 공연']:
            db.execute('INSERT OR IGNORE INTO votes (name) VALUES (?)', (name,))
        db.execute('''CREATE TABLE IF NOT EXISTS cheers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vote_id INTEGER NOT NULL,
            nickname TEXT NOT NULL,
            content TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_cheers_vote ON cheers(vote_id)')


def get_stats():
    with connect_db() as db:
        votes = db.execute('SELECT * FROM votes ORDER BY count DESC, id ASC').fetchall()
    total = sum(row['count'] for row in votes)
    top_count = votes[0]['count'] if votes else 0
    leaders = [row['name'] for row in votes if row['count'] == top_count] if top_count else []
    return votes, total, ', '.join(leaders) if leaders else '아직 투표가 없습니다'


def admin_ok():
    return hmac.compare_digest(request.form.get('admin_password', ''), ADMIN_PASSWORD)


@app.route('/')
def index():
    votes, total, leader = get_stats()
    return render_template('index.html', votes=votes[:3], total=total, leader=leader)


@app.route('/vote', methods=['GET', 'POST'])
def vote():
    if request.method == 'POST':
        if session.get('voted'):
            flash('이 브라우저에서는 이미 투표했습니다.', 'error')
            return redirect(url_for('vote'))
        vote_id = request.form.get('vote_id', type=int)
        if vote_id is None:
            flash('공연을 선택해 주세요.', 'error')
            return redirect(url_for('vote'))
        with connect_db() as db:
            cursor = db.execute('UPDATE votes SET count = count + 1 WHERE id = ?', (vote_id,))
        if cursor.rowcount == 0:
            flash('존재하지 않는 공연입니다.', 'error')
        else:
            session['voted'] = True
            flash('투표가 완료되었습니다!', 'success')
        return redirect(url_for('vote'))

    q = request.args.get('q', '').strip()[:50]
    with connect_db() as db:
        if q:
            votes = db.execute('SELECT * FROM votes WHERE name LIKE ? ORDER BY id', (f'%{q}%',)).fetchall()
        else:
            votes = db.execute('SELECT * FROM votes ORDER BY id').fetchall()
    return render_template('vote.html', votes=votes, q=q, already_voted=session.get('voted', False))


@app.route('/performance/<int:vote_id>')
def detail(vote_id):
    with connect_db() as db:
        item = db.execute('SELECT * FROM votes WHERE id = ?', (vote_id,)).fetchone()
        total = db.execute('SELECT COALESCE(SUM(count), 0) FROM votes').fetchone()[0]
        cheers = db.execute('SELECT nickname, content, created_at FROM cheers WHERE vote_id = ? ORDER BY id DESC LIMIT 5', (vote_id,)).fetchall()
    if item is None:
        abort(404)
    percent = round(item['count'] / total * 100, 1) if total else 0
    return render_template('detail.html', item=item, percent=percent, cheers=cheers)


@app.route('/results')
def results():
    votes, total, leader = get_stats()
    ranked = [(i, row, round(row['count'] / total * 100, 1) if total else 0) for i, row in enumerate(votes, 1)]
    return render_template('results.html', ranked=ranked, total=total, leader=leader)


@app.route('/board')
def board():
    vote_id = request.args.get('vote_id', type=int)
    with connect_db() as db:
        performances = db.execute('SELECT id, name FROM votes ORDER BY id').fetchall()
        if vote_id is not None:
            cheers = db.execute('''SELECT c.*, v.name AS performance_name FROM cheers c
                LEFT JOIN votes v ON c.vote_id = v.id WHERE c.vote_id = ? ORDER BY c.id DESC LIMIT 100''', (vote_id,)).fetchall()
        else:
            cheers = db.execute('''SELECT c.*, v.name AS performance_name FROM cheers c
                LEFT JOIN votes v ON c.vote_id = v.id ORDER BY c.id DESC LIMIT 100''').fetchall()
    return render_template('board.html', cheers=cheers, performances=performances, selected=vote_id)


@app.route('/board/add', methods=['POST'])
def add_cheer():
    vote_id = request.form.get('vote_id', type=int)
    nickname = request.form.get('nickname', '').strip()
    content = request.form.get('content', '').strip()
    password = request.form.get('password', '')
    if not (1 <= len(nickname) <= 20 and 1 <= len(content) <= 300 and 4 <= len(password) <= 100):
        flash('닉네임 1~20자, 내용 1~300자, 삭제 비밀번호 4~100자로 입력해 주세요.', 'error')
        return redirect(url_for('board'))
    with connect_db() as db:
        exists = db.execute('SELECT id FROM votes WHERE id = ?', (vote_id,)).fetchone()
        if not exists:
            flash('공연을 선택해 주세요.', 'error')
            return redirect(url_for('board'))
        db.execute('INSERT INTO cheers (vote_id, nickname, content, password_hash, created_at) VALUES (?, ?, ?, ?, ?)',
                   (vote_id, nickname, content, generate_password_hash(password), datetime.now().strftime('%Y-%m-%d %H:%M')))
    flash('응원 메시지를 등록했습니다.', 'success')
    return redirect(url_for('board'))


@app.route('/board/delete/<int:cheer_id>', methods=['POST'])
def delete_cheer(cheer_id):
    password = request.form.get('password', '')
    with connect_db() as db:
        cheer = db.execute('SELECT password_hash FROM cheers WHERE id = ?', (cheer_id,)).fetchone()
        if not cheer:
            flash('존재하지 않는 게시글입니다.', 'error')
        elif not check_password_hash(cheer['password_hash'], password):
            flash('게시글 삭제 비밀번호가 틀렸습니다.', 'error')
        else:
            db.execute('DELETE FROM cheers WHERE id = ?', (cheer_id,))
            flash('게시글을 삭제했습니다.', 'success')
    return redirect(url_for('board'))


@app.route('/manage')
def manage():
    with connect_db() as db:
        votes = db.execute('SELECT * FROM votes ORDER BY id').fetchall()
    return render_template('manage.html', votes=votes)


@app.route('/add', methods=['POST'])
def add():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    if not (1 <= len(name) <= 50 and len(description) <= 500):
        flash('공연 이름은 1~50자, 소개는 500자 이내로 입력해 주세요.', 'error')
        return redirect(url_for('manage'))
    with connect_db() as db:
        cursor = db.execute('INSERT OR IGNORE INTO votes (name, description) VALUES (?, ?)', (name, description))
    flash('공연이 추가되었습니다.' if cursor.rowcount else '이미 존재하는 공연 이름입니다.', 'success' if cursor.rowcount else 'error')
    return redirect(url_for('manage'))


@app.route('/edit/<int:vote_id>', methods=['POST'])
def edit(vote_id):
    if not admin_ok():
        flash('관리자 비밀번호가 틀렸습니다.', 'error')
        return redirect(url_for('manage'))
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    if not (1 <= len(name) <= 50 and len(description) <= 500):
        flash('공연 이름은 1~50자, 소개는 500자 이내로 입력해 주세요.', 'error')
        return redirect(url_for('manage'))
    try:
        with connect_db() as db:
            cursor = db.execute('UPDATE votes SET name = ?, description = ? WHERE id = ?', (name, description, vote_id))
        flash('공연 정보를 수정했습니다.' if cursor.rowcount else '공연을 찾을 수 없습니다.', 'success' if cursor.rowcount else 'error')
    except sqlite3.IntegrityError:
        flash('이미 존재하는 공연 이름입니다.', 'error')
    return redirect(url_for('manage'))


@app.route('/delete', methods=['POST'])
def delete():
    if not admin_ok():
        flash('관리자 비밀번호가 틀렸습니다.', 'error')
        return redirect(url_for('manage'))
    vote_id = request.form.get('vote_id', type=int)
    with connect_db() as db:
        cursor = db.execute('DELETE FROM votes WHERE id = ?', (vote_id,))
        if cursor.rowcount:
            db.execute('DELETE FROM cheers WHERE vote_id = ?', (vote_id,))
    flash('공연과 관련 응원 글을 삭제했습니다.' if cursor.rowcount else '존재하지 않는 공연입니다.', 'success' if cursor.rowcount else 'error')
    return redirect(url_for('manage'))


@app.route('/api/health')
def health():
    return {'status': 'ok'}


init_db()
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
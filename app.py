
import os
import hmac
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)

DB_PATH = os.environ.get('DB_PATH', 'votes.db')
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
app.secret_key = os.environ['SECRET_KEY']


def connect_db():
    return sqlite3.connect(DB_PATH, timeout=10)


def init_db():
    with connect_db() as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                count INTEGER NOT NULL DEFAULT 0
            )
        ''')

        for name in ['밴드 공연', '댄스 공연', '힙합 공연']:
            db.execute(
                'INSERT OR IGNORE INTO votes (name) VALUES (?)',
                (name,)
            )


# 메인 페이지
@app.route('/')
def index():
    with connect_db() as db:
        votes = db.execute(
            'SELECT id, name, count FROM votes ORDER BY id'
        ).fetchall()

    # 전체 투표수 계산
    total_votes = sum(count for id, name, count in votes)

    # 현재 1위 계산
    max_votes = max((count for id, name, count in votes), default=0)

    if max_votes > 0:
        winners = [
            name for id, name, count in votes
            if count == max_votes
        ]
        first_place = ', '.join(winners)
    else:
        first_place = '아직 투표가 없습니다'

    # 공연별 득표율 계산
    results = []

    for id, name, count in votes:
        if total_votes > 0:
            percent = round(count / total_votes * 100, 1)
        else:
            percent = 0

        results.append((id, name, count, percent))

    return render_template(
        'index.html',
        votes=votes,
        results=results,
        total_votes=total_votes,
        first_place=first_place,
        already_voted=session.get('voted', False),
        message=request.args.get('message', '')
    )


# 투표하기
@app.route('/vote', methods=['POST'])
def vote():
    # 중복 투표 방지
    if session.get('voted'):
        return redirect(url_for('index', message='이미 투표하셨습니다.'))

    vote_id = request.form.get('vote_id', type=int)

    if vote_id is None:
        return redirect(url_for('index', message='공연을 선택해 주세요.'))

    with connect_db() as db:
        cursor = db.execute(
            'UPDATE votes SET count = count + 1 WHERE id = ?',
            (vote_id,)
        )

        if cursor.rowcount == 0:
            return redirect(url_for('index', message='존재하지 않는 공연입니다.'))

    # 투표 완료 기록
    session['voted'] = True

    return redirect(url_for('index', message='투표가 완료되었습니다.'))


# 공연 추가
@app.route('/add', methods=['POST'])
def add():
    name = request.form.get('name', '').strip()

    if not name or len(name) > 50:
        return redirect(
            url_for('index', message='공연 이름은 1~50자로 입력해 주세요.')
        )

    with connect_db() as db:
        cursor = db.execute(
            'INSERT OR IGNORE INTO votes (name) VALUES (?)',
            (name,)
        )

    if cursor.rowcount == 0:
        return redirect(url_for('index', message='이미 존재하는 공연입니다.'))

    return redirect(url_for('index', message='공연이 추가되었습니다.'))


# 공연 삭제 (관리자 비밀번호 필요)
@app.route('/delete', methods=['POST'])
def delete():
    vote_id = request.form.get('vote_id', type=int)
    password = request.form.get('password', '')

    # 관리자 비밀번호 확인
    if not hmac.compare_digest(password, ADMIN_PASSWORD):
        return redirect(
            url_for('index', message='관리자 비밀번호가 틀렸습니다.')
        )

    if vote_id is None:
        return redirect(
            url_for('index', message='삭제할 공연을 선택해 주세요.')
        )

    with connect_db() as db:
        cursor = db.execute(
            'DELETE FROM votes WHERE id = ?',
            (vote_id,)
        )

    if cursor.rowcount == 0:
        return redirect(
            url_for('index', message='존재하지 않는 공연입니다.')
        )

    return redirect(url_for('index', message='공연이 삭제되었습니다.'))


# 서버 상태 확인
@app.route('/api/health')
def health():
    return {'status': 'ok'}


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

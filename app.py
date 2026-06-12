from flask import Flask, render_template, request, jsonify, session, redirect, make_response
import json
import os
import secrets
import time
from datetime import datetime, timezone, timedelta

# 로컬 환경: .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass  # Vercel 환경에는 dotenv 불필요

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_KST = timezone(timedelta(hours=9))

# ─── Secret Key (세션용) ────────────────────────────────────
_SECRET_KEY_FILE = os.path.join(BASE_DIR, 'data', '.secret_key')

def _get_or_create_secret_key():
    """환경변수 우선, 로컬 파일 폴백, 없으면 신규 생성"""
    env_key = os.environ.get('FLASK_SECRET_KEY')
    if env_key:
        return env_key
    if os.path.exists(_SECRET_KEY_FILE):
        with open(_SECRET_KEY_FILE, 'r') as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(_SECRET_KEY_FILE), exist_ok=True)
        with open(_SECRET_KEY_FILE, 'w') as f:
            f.write(key)
    except OSError:
        pass  # 읽기전용 파일시스템 (Vercel 등)
    return key

app.secret_key = _get_or_create_secret_key()

# ─── Supabase Storage ───────────────────────────────────────
_SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
_SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
_SUPABASE_BUCKET = 'mold-index'
_supabase_client = None

def _get_supabase():
    global _supabase_client
    if _supabase_client is None and _SUPABASE_URL and _SUPABASE_KEY:
        try:
            from supabase import create_client
            _supabase_client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        except Exception as e:
            print(f'[Supabase] 클라이언트 생성 실패: {e}')
    return _supabase_client

def _storage_load(filename, default=None):
    """Supabase에서 JSON 로드. 미설정 시 로컬 파일 폴백."""
    sb = _get_supabase()
    if sb:
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                raw = sb.storage.from_(_SUPABASE_BUCKET).download(filename)
                return json.loads(raw.decode('utf-8'))
            except Exception as e:
                err_str = str(e).lower()
                if 'not found' in err_str or '404' in err_str or 'object not found' in err_str:
                    print(f'[Supabase] 파일 없음 ({filename}), 기본값 사용')
                    return default
                print(f'[Supabase] load 실패 ({filename}) [시도 {attempt}/{max_retries}]: {e}')
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)
                else:
                    raise RuntimeError(f'데이터 로드 실패 (Supabase 연결 오류). 잠시 후 다시 시도해주세요.') from e
    # Supabase 미설정 시 로컬 파일 폴백
    local_path = os.path.join(BASE_DIR, 'data', filename)
    if os.path.exists(local_path):
        with open(local_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def _storage_save(filename, data):
    """Supabase에 JSON 저장. 미설정 시 로컬 파일 폴백."""
    content = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    sb = _get_supabase()
    if sb:
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                sb.storage.from_(_SUPABASE_BUCKET).upload(
                    path=filename,
                    file=content,
                    file_options={'content-type': 'application/json', 'upsert': 'true'}
                )
                print(f'[Supabase] 저장 성공 ({filename})')
                return True
            except Exception as e:
                print(f'[Supabase] 저장 실패 ({filename}) [시도 {attempt}/{max_retries}]: {e}')
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)
        return False
    # 로컬 파일 폴백
    try:
        local_path = os.path.join(BASE_DIR, 'data', filename)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(content.decode('utf-8'))
        return True
    except OSError:
        return False

# ─── 앱 데이터 로드/저장 ────────────────────────────────────
APP_DATA_FILE = 'app_data.json'

_APP_DATA_DEFAULT = {
    'ssautotech_mold_v2': None,
    'ssautotech_mold_date': None,
    'ssautotech_sections_v2': None,
    'ssautotech_labels_v1': None,
    'ssautotech_rack_types_v1': None,
    'ssautotech_rack_sizes_v1': None,
}

def load_app_data():
    data = _storage_load(APP_DATA_FILE, {})
    result = dict(_APP_DATA_DEFAULT)
    result.update(data)
    return result

def save_app_data(data):
    return _storage_save(APP_DATA_FILE, data)

# ─── config ─────────────────────────────────────────────────
CONFIG_FILE = 'config.json'

def load_config():
    default = {
        'admin_password': '0000',
        'readonly_password': '1111',
    }
    result = _storage_load(CONFIG_FILE, None)
    if result is None:
        return default
    return result

# ─── 인증 헬퍼 ──────────────────────────────────────────────
def _get_role():
    """현재 세션의 역할 반환: 'admin' | 'readonly' | None"""
    return session.get('role')

def _is_admin():
    return session.get('role') == 'admin'

def _is_authenticated():
    return session.get('role') in ('admin', 'readonly')

@app.before_request
def check_auth():
    """인증 확인: 미인증이면 API는 401, 페이지는 /login으로 리다이렉트"""
    if request.path in ('/login', '/favicon.ico'):
        return
    if request.path.startswith('/api/auth/'):
        return
    if request.path.startswith('/static/'):
        return
    if request.path.startswith('/libs/'):
        return

    if not _is_authenticated():
        if request.path.startswith('/api/'):
            return jsonify({'error': '로그인이 필요합니다.', 'auth_required': True}), 401
        return redirect('/login')

    # 쓰기 작업은 관리자만
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not _is_admin():
            return jsonify({'error': '관리자 권한이 필요합니다.', 'auth_required': True}), 401

# ─── 라우트 ─────────────────────────────────────────────────
@app.route('/login')
def login_page():
    if _is_authenticated():
        return redirect('/')
    r = make_response(render_template('login.html'))
    r.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    r.headers['Pragma'] = 'no-cache'
    return r

@app.route('/')
def index():
    if not _is_authenticated():
        return redirect('/login')
    try:
        app_data = load_app_data()
    except Exception as e:
        return f'데이터 로드 실패: {e}', 500
    r = make_response(render_template(
        'index.html',
        is_admin=_is_admin(),
        server_data=json.dumps(app_data, ensure_ascii=False)
    ))
    r.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    r.headers['Pragma'] = 'no-cache'
    return r

# ─── 인증 API ───────────────────────────────────────────────
@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    return jsonify({
        'is_admin': _is_admin(),
        'role': _get_role(),
        'authenticated': _is_authenticated(),
    })

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    body = request.get_json(silent=True, force=True) or {}
    password = body.get('password', '')
    config = load_config()
    admin_pwd = config.get('admin_password', '0000')
    readonly_pwd = config.get('readonly_password', '1111')

    if admin_pwd and secrets.compare_digest(str(password), str(admin_pwd)):
        session.clear()
        session['role'] = 'admin'
        session.permanent = True
        return jsonify({'success': True, 'role': 'admin'})
    if readonly_pwd and secrets.compare_digest(str(password), str(readonly_pwd)):
        session.clear()
        session['role'] = 'readonly'
        session.permanent = True
        return jsonify({'success': True, 'role': 'readonly'})
    return jsonify({'error': '비밀번호가 틀렸습니다'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'success': True})

# ─── 데이터 API ─────────────────────────────────────────────
@app.route('/api/data', methods=['GET'])
def get_data():
    """앱 데이터 전체 반환"""
    try:
        data = load_app_data()
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/data', methods=['POST'])
def save_data():
    """앱 데이터 저장 (관리자 전용 — before_request에서 이미 검사)"""
    body = request.get_json(silent=True, force=True) or {}
    if not body:
        return jsonify({'error': '데이터 없음'}), 400
    try:
        current = load_app_data()
        # 클라이언트가 보낸 키만 업데이트
        for key, value in body.items():
            current[key] = value
        ok = save_app_data(current)
        if ok:
            return jsonify({'success': True})
        else:
            return jsonify({'error': '저장 실패'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── 정적 파일 서빙 (libs/) ─────────────────────────────────
@app.route('/libs/<path:filename>')
def serve_libs(filename):
    from flask import send_from_directory
    return send_from_directory(os.path.join(BASE_DIR, 'libs'), filename)

# ─── 실행 ────────────────────────────────────────────────────
if __name__ == '__main__':
    os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    print(f'서버 시작: http://0.0.0.0:{port}')
    print(f'로컬 접속: http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, debug=debug)

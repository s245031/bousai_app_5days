from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from urllib.parse import urlparse, urljoin
from functools import wraps
import json
import os
import random
import urllib.request
from datetime import datetime, timedelta, timezone

# app.py はプロジェクト直下に置く。
# 実体（templates / static / data）は bousai_app/ 配下にあるので、そこを参照する。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, 'bousai_app')

app = Flask(
    __name__,
    template_folder=os.path.join(APP_DIR, 'templates'),
    static_folder=os.path.join(APP_DIR, 'static'),
)
app.secret_key = 'your-secret-key-here'

# 管理者認証情報
ADMIN_CREDENTIALS = {
    'admin': '123'
}

# ────────────────────────────────
# 気象警報・注意報設定
PREFECTURE_CODE = "020000"  # 青森県
AREA_NAME = "青森市"

# 現在の JMA の live API は 0220500 系の areaCode を返すため、
# サンプルの 1420500 も受け取れるように両方を許容する。
AREA_CODES = ("0220500", "1420500")

WARNING_URL = (
    f"https://www.jma.go.jp/bosai/warning/data/r8/{PREFECTURE_CODE}.json"
)

JST = timezone(timedelta(hours=9))

# 警報・注意報のコード一覧
WARNING_CODES = {
    "00": "解除",
    "02": "暴風雪警報",
    "03": "レベル3大雨警報",
    "04": "洪水警報",
    "05": "暴風警報",
    "06": "大雪警報",
    "07": "波浪警報",
    "08": "レベル3高潮警報",
    "09": "レベル3土砂災害警報",
    "10": "レベル2大雨注意報",
    "12": "大雪注意報",
    "13": "風雪注意報",
    "14": "雷注意報",
    "15": "強風注意報",
    "16": "波浪注意報",
    "17": "融雪注意報",
    "18": "洪水注意報",
    "19": "レベル2高潮注意報",
    "20": "濃霧注意報",
    "21": "乾燥注意報",
    "22": "なだれ注意報",
    "23": "低温注意報",
    "24": "霜注意報",
    "25": "着氷注意報",
    "26": "着雪注意報",
    "27": "その他の注意報",
    "29": "レベル2土砂災害注意報",
    "32": "暴風雪特別警報",
    "33": "レベル5大雨特別警報",
    "35": "暴風特別警報",
    "36": "大雪特別警報",
    "37": "波浪特別警報",
    "38": "レベル5高潮特別警報",
    "39": "レベル5土砂災害特別警報",
    "43": "レベル4大雨危険警報",
    "48": "レベル4高潮危険警報",
    "49": "レベル4土砂災害危険警報"
}

# ────────────────────────────────
# サンプルデータの読み込み
DATA_FILE = os.path.join(APP_DIR, 'data', 'shelters.json')
INSTRUCTIONS_FILE = os.path.join(APP_DIR, 'data', 'instructions.json')

def load_json(path, default):
    """JSONファイルを読み込む（存在しない・壊れている場合は default を返す）"""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

shelters = load_json(DATA_FILE, [])
instructions = load_json(INSTRUCTIONS_FILE, [])


def get_default_shelter_coordinates(shelter=None, index=0):
    """地図表示用の適当な座標を生成する。初期表示の範囲内に収まるように少しだけ散らばらせる。"""
    shelter_id = shelter.get('id') if shelter else None
    base_index = shelter_id if shelter_id is not None else index

    # 既存データには一貫した位置を与えつつ、初期地図範囲内で少しだけ散らばらせる
    rng = random.Random(base_index + 100)
    lat = 40.8230 + rng.uniform(-0.0060, 0.0060)
    lng = 140.7450 + rng.uniform(-0.0100, 0.0100)

    return round(lat, 4), round(lng, 4)


def normalize_shelter_coordinates():
    """避難所データに座標がない場合のみ適当な座標を補完する"""
    for index, shelter in enumerate(shelters):
        if shelter.get('lat') is None or shelter.get('lng') is None:
            shelter['lat'], shelter['lng'] = get_default_shelter_coordinates(shelter, index)
    return shelters


shelters = normalize_shelter_coordinates()


def save_instructions():
    """指示ボードのデータをファイルに保存する"""
    try:
        with open(INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(instructions, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_shelters():
    """避難所データをファイルに保存する"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(shelters, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
# ────────────────────────────────

# ────────────────────────────────
# 認証関連の設定とヘルパー関数
def is_safe_url(target):
    """リダイレクト先URLが安全かどうかチェック"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def login_required(f):
    """認証が必要なページに付けるデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            # 現在のURLをnextパラメータとしてログイン画面にリダイレクト
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def get_japan_time():
    """日本時間（JST）の現在時刻を取得する"""
    return datetime.now(JST).strftime("%Y年%m月%d日 %H:%M")


def format_report_time(iso_str):
    """気象庁の発表時刻（ISO形式）をJSTの表示用文字列に変換する"""
    if not iso_str:
        return "不明"
    try:
        parsed = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        if parsed.tzinfo:
            parsed = parsed.astimezone(JST)
        return parsed.strftime("%Y年%m月%d日 %H:%M")
    except ValueError:
        return iso_str


def to_int(value, default=0):
    """文字列・数値を安全に int に変換する"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def remaining_capacity(shelter):
    """残り受け入れ人数を計算する"""
    capacity = to_int(shelter.get('capacity'), 0)
    current = to_int(shelter.get('current'), 0)
    return max(capacity - current, 0)


def filter_shelters(district=None, sort=None, only_available=False):
    """district 指定があれば一致する避難所のみ、必要なら並び替えする"""
    results = [s for s in shelters if not district or s.get('district') == district]

    if only_available:
        results = [s for s in results if remaining_capacity(s) > 0]

    if sort == 'current_asc':
        return sorted(results, key=lambda s: (to_int(s.get('current'), 0), s.get('name', '')))
    if sort == 'current_desc':
        return sorted(results, key=lambda s: (-to_int(s.get('current'), 0), s.get('name', '')))
    if sort == 'remaining_asc':
        return sorted(results, key=lambda s: (remaining_capacity(s), s.get('name', '')))
    if sort == 'remaining_desc':
        return sorted(results, key=lambda s: (-remaining_capacity(s), s.get('name', '')))

    return results


def get_shelter_by_id(shelter_id):
    """IDから避難所を取得する"""
    for shelter in shelters:
        if shelter.get('id') == shelter_id:
            return shelter
    return None


def parse_area_warnings(warning_data):
    """気象庁のJSONから対象市区町村の警報・注意報情報を抽出する"""
    if isinstance(warning_data, list):
        reports = warning_data
    elif isinstance(warning_data, dict):
        reports = [warning_data]
    else:
        raise ValueError("気象庁の警報・注意報データの形式が不正です")

    warnings = []
    seen = set()
    latest_report_datetime = ""

    def add_warning(code, status):
        if not code:
            return
        item_key = (code, status)
        if item_key in seen:
            return

        warnings.append({
            "name": WARNING_CODES.get(
                code,
                f"不明な警報・注意報 (コード: {code})"
            ),
            "code": code,
            "status": status
        })
        seen.add(item_key)

    for report in reports:
        if not isinstance(report, dict):
            continue

        report_datetime = report.get("reportDatetime", "")
        if report_datetime:
            latest_report_datetime = report_datetime

        # 現在の live API 形式: report -> warning -> class20Items[] -> areaCode / kinds[]
        warning_info = report.get("warning")
        if isinstance(warning_info, dict):
            class20_items = warning_info.get("class20Items", [])
            if isinstance(class20_items, list):
                for item in class20_items:
                    if not isinstance(item, dict):
                        continue
                    if item.get("areaCode") not in AREA_CODES:
                        continue

                    kinds = item.get("kinds", [])
                    if not isinstance(kinds, list):
                        continue

                    for kind in kinds:
                        if not isinstance(kind, dict):
                            continue
                        status = kind.get("status", "")
                        code = kind.get("code", "")
                        if status in ("発表警報・注意報はなし", ""):
                            continue
                        if status == "解除" and not code:
                            continue
                        add_warning(code, status)

        # 参考として示された areaTypes 形式にも対応
        area_types = report.get("areaTypes", [])
        if isinstance(area_types, list):
            for area_type in area_types:
                if not isinstance(area_type, dict):
                    continue

                areas = area_type.get("areas", [])
                if not isinstance(areas, list):
                    continue

                for area in areas:
                    if not isinstance(area, dict):
                        continue
                    if area.get("code") not in AREA_CODES:
                        continue

                    for warning in area.get("warnings", []):
                        if not isinstance(warning, dict):
                            continue

                        status = warning.get("status", "")
                        code = warning.get("code", "")
                        if status in ("発表警報・注意報はなし", ""):
                            continue
                        if status == "解除" and not code:
                            continue
                        add_warning(code, status)

    return warnings, latest_report_datetime


def get_weather_warnings():
    """対象市区町村の警報・注意報を取得する"""
    try:
        # 青森県の新形式（令和8年～）警報・注意報データを取得
        with urllib.request.urlopen(url=WARNING_URL, timeout=10) as res:
            warning_data = json.loads(res.read())

        warnings, report_datetime = parse_area_warnings(warning_data)

        return {
            "area_name": AREA_NAME,
            "warnings": warnings,
            "report_time": format_report_time(report_datetime),
            "last_fetch_time": get_japan_time()
        }

    except Exception:
        return {
            "area_name": AREA_NAME,
            "warnings": [],
            "report_time": "取得失敗",
            "last_fetch_time": get_japan_time(),
            "error": True
        }


# トップページ：templates/index.html を返す（住民向け指示も表示する）
@app.route('/')
def index():
    resident_notices = [i for i in instructions if i.get('target') == '住民']
    return render_template('index.html', resident_notices=resident_notices)

# ログインページ
@app.route('/login', methods=['GET', 'POST'])
def login():
    # リダイレクト先を取得（デフォルトは避難所登録画面）
    next_url = request.args.get('next') or request.form.get('next')

    # 安全でないURLの場合はデフォルトページにリダイレクト
    if not next_url or not is_safe_url(next_url):
        next_url = url_for('shelter_register')

    if request.method == 'POST':
        password = request.form.get('password', '').strip()

        # 認証チェック
        username = next(
            (name for name, registered_password in ADMIN_CREDENTIALS.items()
             if registered_password == password),
            None
        )
        if username:
            session['logged_in'] = True
            session['username'] = username
            # ログイン成功後は指定されたページにリダイレクト
            return redirect(next_url)
        return render_template('login.html', error=True, message="パスワードが正しくありません。", next=next_url)

    # ログイン済みの場合は指定されたページにリダイレクト
    if session.get('logged_in'):
        return redirect(next_url)

    return render_template('login.html', next=next_url)

# ログアウト
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# 避難所登録ページ
@app.route('/shelter_register', methods=['GET', 'POST'])
@login_required
def shelter_register():
    if request.method == 'POST':
        shelter_name = request.form.get('name', '').strip()
        capacity = request.form.get('capacity', '').strip()
        current = request.form.get('current', '').strip()

        if not shelter_name:
            return render_template(
                'shelter_register.html',
                shelters=shelters,
                error=True,
                message='避難所名を入力してください。'
            )

        if capacity == '':
            capacity = 0
        if current == '':
            current = 0

        try:
            capacity = int(capacity)
            current = int(current)
        except ValueError:
            return render_template(
                'shelter_register.html',
                shelters=shelters,
                error=True,
                message='受け入れ可能人数と現在の受け入れ人数は整数で入力してください。'
            )

        if capacity < 0 or current < 0:
            return render_template(
                'shelter_register.html',
                shelters=shelters,
                error=True,
                message='人数は0以上で入力してください。'
            )

        if capacity and current > capacity:
            return render_template(
                'shelter_register.html',
                shelters=shelters,
                error=True,
                message='受け入れ人数が受け入れ可能人数を上回っています。'
            )

        new_id = max((s.get('id', 0) for s in shelters), default=0) + 1
        lat, lng = get_default_shelter_coordinates({'id': new_id}, len(shelters))
        shelters.append({
            'id': new_id,
            'name': shelter_name,
            'capacity': capacity,
            'current': current,
            'lat': lat,
            'lng': lng
        })
        save_shelters()

        return render_template(
            'shelter_register.html',
            shelters=shelters,
            success=True,
            message=f'避難所「{shelter_name}」を登録しました。'
        )

    return render_template('shelter_register.html', shelters=shelters)


@app.route('/shelter_delete/<int:shelter_id>', methods=['POST'])
@login_required
def shelter_delete(shelter_id):
    shelter = get_shelter_by_id(shelter_id)
    if shelter:
        shelters[:] = [s for s in shelters if s.get('id') != shelter_id]
        save_shelters()

    return redirect(url_for('shelter_register'))


@app.route('/shelter_edit/<int:shelter_id>', methods=['GET', 'POST'])
@login_required
def shelter_edit(shelter_id):
    shelter = get_shelter_by_id(shelter_id)
    if not shelter:
        return redirect(url_for('shelter_register'))

    if request.method == 'POST':
        shelter_name = request.form.get('name', '').strip()
        capacity = request.form.get('capacity', '').strip()
        current = request.form.get('current', '').strip()

        if not shelter_name:
            return render_template(
                'shelter_edit.html',
                shelter=shelter,
                error=True,
                message='避難所名を入力してください。'
            )

        if capacity == '':
            capacity = 0
        if current == '':
            current = 0

        try:
            capacity = int(capacity)
            current = int(current)
        except ValueError:
            return render_template(
                'shelter_edit.html',
                shelter=shelter,
                error=True,
                message='受け入れ可能人数と現在の受け入れ人数は整数で入力してください。'
            )

        if capacity < 0 or current < 0:
            return render_template(
                'shelter_edit.html',
                shelter=shelter,
                error=True,
                message='人数は0以上で入力してください。'
            )

        if capacity and current > capacity:
            return render_template(
                'shelter_edit.html',
                shelter=shelter,
                error=True,
                message='受け入れ人数が受け入れ可能人数を上回っています。'
            )

        shelter['name'] = shelter_name
        shelter['capacity'] = capacity
        shelter['current'] = current
        save_shelters()
        return redirect(url_for('shelter_register'))

    return render_template('shelter_edit.html', shelter=shelter)

# 避難所検索ページ
@app.route('/shelter_search')
def shelter_search():
    return render_template('shelter_search.html')

# 全施設一覧ページ
@app.route('/all_shelters')
def all_shelters():
    return render_template('search_results.html', results=shelters)


# 指示ボード：住民向けの指示を一覧で確認する
# 住民向けの情報なのでログインなしでも閲覧できるようにする
@app.route('/board')
def board():
    resident_instructions = [i for i in instructions if i.get('target') == '住民']
    return render_template('board.html', instructions=resident_instructions)

# 検索結果ページ：templates/search_results.html を返す
@app.route('/search_results')
def search_results():
    normalize_shelter_coordinates()
    sort = request.args.get('sort', 'remaining_desc')
    results = filter_shelters(request.args.get('district'), sort=sort, only_available=False)
    return render_template('search_results.html', results=results, sort=sort)

# JSON API：/shelters?district=地区名
@app.route('/shelters', methods=['GET'])
def get_shelters():
    sort = request.args.get('sort', 'remaining_desc')
    results = filter_shelters(request.args.get('district'), sort=sort, only_available=False)

    if not results:
        # 見つからなければエラー JSON を返す
        return jsonify({'error': 'No shelters found'}), 404

    # 見つかったらリストを JSON で返す
    return jsonify(results)

# 気象警報・注意報API
@app.route('/api/weather_warnings')
def api_weather_warnings():
    """気象警報・注意報をJSON形式で返すAPI"""
    return jsonify(get_weather_warnings())

if __name__ == '__main__':
    app.run(debug=True, port=5000)

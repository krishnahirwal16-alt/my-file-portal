import os
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'crixdata_secret_key_2026')

db_url = os.environ.get('DATABASE_URL', 'sqlite:///files.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class FileRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    public_id = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), default="General Cricket")

cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)

db_created = False

@app.before_request
def create_tables_once():
    global db_created
    if not db_created:
        try:
            db.create_all()
            db_created = True
        except Exception:
            pass

def format_score_inngs(inng_data):
    if not inng_data:
        return ""
    runs = inng_data.get('runs', 0)
    wickets = inng_data.get('wickets', 0)
    overs = inng_data.get('overs')
    if overs is not None and str(overs) != "":
        return f"{runs}/{wickets} ({overs} ov)"
    return f"{runs}/{wickets}"

def parse_ist_date_and_day(timestamp_ms):
    if not timestamp_ms:
        return "Date/Time N/A"
    try:
        ts = int(timestamp_ms) / 1000.0
        utc_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        ist_dt = utc_dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
        return ist_dt.strftime("%A, %d %b %Y | %I:%M %p IST")
    except Exception:
        return "Date N/A"

def fetch_real_cricket_data():
    api_key = os.environ.get('RAPIDAPI_KEY')
    matches_data = {"live": [], "upcoming": [], "finished": []}

    if not api_key:
        return matches_data

    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "cricbuzz-cricket.p.rapidapi.com"
    }

    processed_match_ids = set()

    def extract_and_append_match(m, match_category="Other", series_name="Cricket Series", force_live=False):
        m_info = m.get('matchInfo', {})
        m_score = m.get('matchScore', {})
        match_id = m_info.get('matchId')

        if not match_id or match_id in processed_match_ids:
            return
        processed_match_ids.add(match_id)

        team1 = m_info.get('team1', {}).get('teamName', 'Team 1')
        team2 = m_info.get('team2', {}).get('teamName', 'Team 2')
        match_format = (m_info.get('matchFormat') or m_info.get('format', 'CRICKET')).upper()
        status = m_info.get('status', '')
        state = (m_info.get('state') or '').lower().strip()

        start_time_ms = m_info.get('startDate') or m_info.get('matchStartTimestamp')
        match_date_ist = parse_ist_date_and_day(start_time_ms)

        score_str = ""
        if m_score:
            t1_score = m_score.get('team1Score', {})
            t2_score = m_score.get('team2Score', {})

            t1_i1 = format_score_inngs(t1_score.get('inngs1'))
            t1_i2 = format_score_inngs(t1_score.get('inngs2'))
            t2_i1 = format_score_inngs(t2_score.get('inngs1'))
            t2_i2 = format_score_inngs(t2_score.get('inngs2'))

            if match_format == 'TEST':
                t1_full = f"{t1_i1}" + (f" & {t1_i2}" if t1_i2 else "")
                t2_full = f"{t2_i1}" + (f" & {t2_i2}" if t2_i2 else "")
                score_parts = [p for p in [f"{team1}: {t1_full}" if t1_full else "", f"{team2}: {t2_full}" if t2_full else ""] if p]
                score_str = " | ".join(score_parts)
            else:
                score_parts = [p for p in [f"{team1}: {t1_i1}" if t1_i1 else "", f"{team2}: {t2_i1}" if t2_i1 else ""] if p]
                score_str = " | ".join(score_parts)

        if not score_str:
            score_str = "Live Match In Progress"

        venue_info = m_info.get('venueInfo', {})
        ground = venue_info.get('ground', '')
        city = venue_info.get('city', '')
        venue = f"{ground}, {city}".strip(", ") if (ground or city) else "Cricket Ground"

        item = {
            "title": f"{team1} vs {team2}",
            "format": match_format,
            "category": match_category,
            "series": series_name,
            "status": status if status else "In Progress",
            "score": score_str,
            "date": match_date_ist,
            "venue": venue
        }

        status_lower = status.lower()

        is_finished = (
            "complete" in state or "result" in state or 
            "won by" in status_lower or "beat" in status_lower or 
            "drawn" in status_lower or "tied" in status_lower or 
            "abandoned" in status_lower or "no result" in status_lower
        )
        
        is_upcoming = "upcoming" in state or "preview" in state or "starts at" in status_lower

        if force_live:
            if not is_finished and not is_upcoming:
                matches_data["live"].append(item)
            elif is_finished:
                matches_data["finished"].append(item)
            else:
                matches_data["live"].append(item)
        else:
            if is_finished:
                matches_data["finished"].append(item)
            elif is_upcoming:
                matches_data["upcoming"].append(item)
            else:
                matches_data["live"].append(item)

    def parse_api_response(url, is_live_endpoint=False):
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                raw = res.json()
                type_matches = raw.get('typeMatches', [])
                if type_matches:
                    for type_group in type_matches:
                        match_category = type_group.get('matchType', 'Other')
                        series_matches = type_group.get('seriesMatches', [])
                        
                        for series_item in series_matches:
                            series_ad = series_item.get('seriesAdWrapper', {})
                            series_name = series_ad.get('seriesName') or series_item.get('seriesName', 'Cricket Series')
                            matches = series_ad.get('matches', []) or series_item.get('matches', [])

                            for m in matches:
                                extract_and_append_match(m, match_category, series_name, force_live=is_live_endpoint)
                elif 'matches' in raw:
                    for m in raw.get('matches', []):
                        extract_and_append_match(m, force_live=is_live_endpoint)

        except Exception as e:
            print("Cricbuzz API Exception:", e)

    # 1. Fetch live matches first
    parse_api_response("https://cricbuzz-cricket.p.rapidapi.com/matches/v1/live", is_live_endpoint=True)
    # 2. Fetch recent matches
    parse_api_response("https://cricbuzz-cricket.p.rapidapi.com/matches/v1/recent")
    # 3. Fetch upcoming matches
    parse_api_response("https://cricbuzz-cricket.p.rapidapi.com/matches/v1/upcoming")

    return matches_data

@app.route('/')
def index():
    try:
        files = FileRecord.query.all()
    except Exception:
        files = []
    is_admin = session.get('is_admin', False)
    cricket_data = fetch_real_cricket_data()
    return render_template('index.html', files=files, is_admin=is_admin, cricket_data=cricket_data)

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'admin123')
        if password == admin_pass:
            session['is_admin'] = True
            flash('Admin Access Granted!')
            return redirect(url_for('index'))
        else:
            flash('Incorrect Admin Password!')
    return render_template('admin.html')

@app.route('/logout')
def logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    title = request.form.get('title')
    category = request.form.get('category', 'General Cricket')
    file = request.files.get('file')
    if file and title:
        upload_result = cloudinary.uploader.upload(file, resource_type="auto")
        new_file = FileRecord(
            title=title,
            file_url=upload_result['secure_url'],
            public_id=upload_result['public_id'],
            category=category
        )
        db.session.add(new_file)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    file_item = FileRecord.query.get_or_404(file_id)
    cloudinary.uploader.destroy(file_item.public_id, invalidate=True)
    db.session.delete(file_item)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

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
    matches_data = {"live": [], "upcoming": [], "finished": []}
    processed_match_ids = set()

    # Priority 1: Open Cricket Data Feed
    try:
        open_res = requests.get("https://api.cricapi.com/v1/cda?apikey=36474df6-72be-4573-a442-88ec0c5bc622&offset=0", timeout=6)
        if open_res.status_code == 200:
            data_list = open_res.json().get('data', [])
            for item in data_list:
                m_id = item.get('id')
                if m_id in processed_match_ids:
                    continue
                processed_match_ids.add(m_id)

                t1 = item.get('teams', ['Team 1', 'Team 2'])[0]
                t2 = item.get('teams', ['Team 1', 'Team 2'])[1] if len(item.get('teams', [])) > 1 else "Team 2"
                t1_short = t1[:4].upper()
                t2_short = t2[:4].upper()

                status = item.get('status', 'Scheduled')
                match_format = (item.get('matchType') or 'T20').upper()
                venue = item.get('venue', 'Cricket Ground')
                date_str = item.get('date', 'Date N/A')

                match_card = {
                    "title": f"{t1} vs {t2}",
                    "team1_short": t1_short,
                    "team1_score": "Yet to Bat",
                    "team1_batting": False,
                    "team2_short": t2_short,
                    "team2_score": "Yet to Bat",
                    "team2_batting": False,
                    "format": match_format,
                    "category": "International",
                    "series": item.get('name', 'Cricket Series'),
                    "status": status,
                    "date": date_str,
                    "venue": venue
                }

                if item.get('matchEnded', False):
                    matches_data["finished"].append(match_card)
                elif item.get('matchStarted', False):
                    matches_data["live"].append(match_card)
                else:
                    matches_data["upcoming"].append(match_card)
    except Exception as e:
        print("Open Feed Fetch Error:", e)

    # Priority 2: RapidAPI Cricbuzz Call (Fallback)
    if not any(matches_data.values()):
        api_key = os.environ.get('RAPIDAPI_KEY')
        if api_key:
            headers = {
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": "cricbuzz-cricket.p.rapidapi.com"
            }
            for ep in ["live", "recent", "upcoming"]:
                try:
                    res = requests.get(f"https://cricbuzz-cricket.p.rapidapi.com/matches/v1/{ep}", headers=headers, timeout=6)
                    if res.status_code == 200:
                        type_matches = res.json().get('typeMatches', [])
                        for type_group in type_matches:
                            match_category = type_group.get('matchType', 'Other')
                            for series_item in type_group.get('seriesMatches', []):
                                series_ad = series_item.get('seriesAdWrapper', {})
                                series_name = series_ad.get('seriesName') or series_item.get('seriesName', 'Cricket Series')
                                matches = series_ad.get('matches', []) or series_item.get('matches', [])
                                for m in matches:
                                    m_info = m.get('matchInfo', {})
                                    m_id = m_info.get('matchId')
                                    if not m_id or m_id in processed_match_ids:
                                        continue
                                    processed_match_ids.add(m_id)

                                    team1 = m_info.get('team1', {}).get('teamName', 'Team 1')
                                    team2 = m_info.get('team2', {}).get('teamName', 'Team 2')
                                    status = m_info.get('status', '')
                                    state = (m_info.get('state') or '').lower().strip()

                                    card = {
                                        "title": f"{team1} vs {team2}",
                                        "team1_short": m_info.get('team1', {}).get('sName', team1[:4].upper()),
                                        "team1_score": "Yet to Bat",
                                        "team1_batting": False,
                                        "team2_short": m_info.get('team2', {}).get('sName', team2[:4].upper()),
                                        "team2_score": "Yet to Bat",
                                        "team2_batting": False,
                                        "format": (m_info.get('matchFormat') or 'T20').upper(),
                                        "category": match_category,
                                        "series": series_name,
                                        "status": status,
                                        "date": parse_ist_date_and_day(m_info.get('startDate')),
                                        "venue": m_info.get('venueInfo', {}).get('ground', 'Cricket Ground')
                                    }

                                    status_lower = status.lower()
                                    if "complete" in state or "result" in state or "finished" in state:
                                        matches_data["finished"].append(card)
                                    elif "upcoming" in state or "preview" in state:
                                        matches_data["upcoming"].append(card)
                                    else:
                                        matches_data["live"].append(card)
                except Exception:
                    pass

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

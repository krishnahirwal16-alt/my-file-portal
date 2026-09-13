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
    api_key = os.environ.get('RAPIDAPI_KEY')
    matches_data = {"live": [], "upcoming": [], "finished": []}
    processed_match_ids = set()

    headers = {
        "x-rapidapi-key": api_key or "",
        "x-rapidapi-host": "cricbuzz-cricket.p.rapidapi.com"
    }

    def process_match_item(m, match_category="International", series_name="Cricket Series"):
        try:
            m_info = m.get('matchInfo', m)
            match_id = m_info.get('matchId') or m.get('matchId')

            if not match_id or match_id in processed_match_ids:
                return
            processed_match_ids.add(match_id)

            team1 = m_info.get('team1', {}).get('teamName', 'Team 1')
            team2 = m_info.get('team2', {}).get('teamName', 'Team 2')
            team1_short = m_info.get('team1', {}).get('sName', team1[:4].upper())
            team2_short = m_info.get('team2', {}).get('sName', team2[:4].upper())

            match_format = (m_info.get('matchFormat') or m_info.get('format', 'T20')).upper()
            status = m_info.get('status', 'Match Scheduled')
            state = (m_info.get('state') or '').lower().strip()

            start_time_ms = m_info.get('startDate') or m_info.get('matchStartTimestamp')
            match_date_ist = parse_ist_date_and_day(start_time_ms)

            venue_info = m_info.get('venueInfo', {})
            ground = venue_info.get('ground', '')
            city = venue_info.get('city', '')
            venue = f"{ground}, {city}".strip(", ") if (ground or city) else "Cricket Stadium"

            item = {
                "title": f"{team1} vs {team2}",
                "team1_short": team1_short,
                "team1_score": "Yet to Bat",
                "team1_batting": False,
                "team2_short": team2_short,
                "team2_score": "Yet to Bat",
                "team2_batting": False,
                "format": match_format,
                "category": match_category,
                "series": series_name,
                "status": status,
                "date": match_date_ist,
                "venue": venue
            }

            status_lower = status.lower()
            is_finished = (
                "complete" in state or "result" in state or "finished" in state or
                "won by" in status_lower or "beat" in status_lower or 
                "drawn" in status_lower or "tied" in status_lower or 
                "abandoned" in status_lower or "no result" in status_lower
            )
            is_upcoming = "upcoming" in state or "preview" in state or "starts at" in status_lower or "scheduled" in state

            if is_finished:
                matches_data["finished"].append(item)
            elif is_upcoming:
                matches_data["upcoming"].append(item)
            else:
                matches_data["live"].append(item)
        except Exception:
            pass

    def fetch_url(url):
        if not api_key:
            return
        try:
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code == 200:
                raw = res.json()
                type_matches = raw.get('typeMatches') or raw.get('typeMatch') or []
                for type_group in type_matches:
                    match_category = type_group.get('matchType', 'General')
                    series_matches = type_group.get('seriesMatches', [])
                    for series_item in series_matches:
                        series_ad = series_item.get('seriesAdWrapper', {})
                        series_name = series_ad.get('seriesName') or series_item.get('seriesName', 'International Match')
                        matches = series_ad.get('matches', []) or series_item.get('matches', [])
                        for m in matches:
                            process_match_item(m, match_category, series_name)
        except Exception:
            pass

    fetch_url("https://cricbuzz-cricket.p.rapidapi.com/matches/v1/live")
    fetch_url("https://cricbuzz-cricket.p.rapidapi.com/matches/v1/recent")
    fetch_url("https://cricbuzz-cricket.p.rapidapi.com/matches/v1/upcoming")

    # Fallback to display data if API block/quota hit happens
    if len(matches_data["live"]) == 0 and len(matches_data["upcoming"]) == 0 and len(matches_data["finished"]) == 0:
        matches_data["live"].append({
            "title": "IND vs AUS", "team1_short": "IND", "team1_score": "Yet to Bat", "team1_batting": True,
            "team2_short": "AUS", "team2_score": "Yet to Bat", "team2_batting": False,
            "format": "T20I", "category": "International", "series": "T20 Championship 2026",
            "status": "Match in progress", "date": "Today | 07:00 PM IST", "venue": "M. Chinnaswamy Stadium, Bengaluru"
        })
        matches_data["upcoming"].append({
            "title": "ENG vs NZ", "team1_short": "ENG", "team1_score": "Yet to Bat", "team1_batting": False,
            "team2_short": "NZ", "team2_score": "Yet to Bat", "team2_batting": False,
            "format": "ODI", "category": "International", "series": "ODI International Series",
            "status": "Match Starts at 02:30 PM IST", "date": "Tomorrow | 02:30 PM IST", "venue": "Lords, London"
        })
        matches_data["finished"].append({
            "title": "SA vs PAK", "team1_short": "SA", "team1_score": "185-4", "team1_batting": False,
            "team2_short": "PAK", "team2_score": "142-10", "team2_batting": False,
            "format": "T20I", "category": "International", "series": "T20 World Series",
            "status": "South Africa won by 43 runs", "date": "13 Sep 2026", "venue": "Gqeberha"
        })

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

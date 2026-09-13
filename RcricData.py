import os
import requests
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

def fetch_real_cricket_data():
    api_key = os.environ.get('RAPIDAPI_KEY')
    matches_data = {"live": [], "upcoming": [], "finished": []}

    if not api_key:
        return matches_data

    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "cricbuzz-cricket.p.rapidapi.com"
    }

    # Helper function to parse matches list from Cricbuzz JSON API
    def parse_api_response(url):
        try:
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                raw = res.json()
                for type_group in raw.get('typeMatches', []):
                    match_type_category = type_group.get('matchType', 'Other')  # International, League, Women, etc.
                    
                    for series_wrapper in type_group.get('seriesMatches', []):
                        series_ad = series_wrapper.get('seriesAdWrapper', {})
                        series_name = series_ad.get('seriesName', 'Cricket Series')
                        matches_list = series_ad.get('matches', [])
                        
                        # Fallback if structure varies
                        if not matches_list and 'matches' in series_wrapper:
                            matches_list = series_wrapper.get('matches', [])

                        for m in matches_list:
                            m_info = m.get('matchInfo', {})
                            m_score = m.get('matchScore', {})

                            team1 = m_info.get('team1', {}).get('teamName', 'Team 1')
                            team2 = m_info.get('team2', {}).get('teamName', 'Team 2')
                            match_format = m_info.get('matchFormat', 'CRICKET').upper()
                            status = m_info.get('status', 'In Progress')
                            state = m_info.get('state', '').lower()

                            # Score Extract
                            t1_runs = m_score.get('team1Score', {}).get('inngs1', {}).get('runs', '')
                            t1_wkts = m_score.get('team1Score', {}).get('inngs1', {}).get('wickets', '')
                            t2_runs = m_score.get('team2Score', {}).get('inngs1', {}).get('runs', '')
                            t2_wkts = m_score.get('team2Score', {}).get('inngs1', {}).get('wickets', '')

                            score_str = ""
                            if t1_runs != '' or t2_runs != '':
                                s1 = f"{t1_runs}/{t1_wkts}" if t1_runs != '' else ""
                                s2 = f"{t2_runs}/{t2_wkts}" if t2_runs != '' else ""
                                score_str = f"{team1}: {s1} | {team2}: {s2}".strip(" |")
                            else:
                                score_str = "Match Status Updating..."

                            venue = f"{m_info.get('venueInfo', {}).get('ground', '')}, {m_info.get('venueInfo', {}).get('city', '')}".strip(", ")

                            item = {
                                "title": f"{team1} vs {team2}",
                                "format": match_format,
                                "category": match_type_category,
                                "series": series_name,
                                "status": status,
                                "score": score_str,
                                "venue": venue if venue else "Cricket Ground"
                            }

                            # Filter into Live, Upcoming, Finished
                            if "complete" in state or "result" in state or "won" in status.lower():
                                matches_data["finished"].append(item)
                            elif "upcoming" in state or "preview" in state or "scheduled" in state:
                                matches_data["upcoming"].append(item)
                            else:
                                matches_data["live"].append(item)
        except Exception as e:
            print("API Error:", e)

    # Fetching live/recent matches endpoint
    parse_api_response("https://cricbuzz-cricket.p.rapidapi.com/matches/v1/recent")
    # Fetching upcoming matches endpoint
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

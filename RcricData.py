import os
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'crixdata_secret_key_2026')

# Database Configuration
db_url = os.environ.get('DATABASE_URL', 'sqlite:///files.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy()
db.init_app(app)

class FileRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    public_id = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), default="General Cricket")

with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print("Database initialization error:", e)

# Live Cricket Scores Helper Function
def fetch_live_cricket_data():
    rapid_api_key = os.environ.get('RAPIDAPI_KEY')
    if rapid_api_key:
        url = "https://cricbuzz-cricket.p.rapidapi.com/matches/v1/recent"
        headers = {
            "x-rapidapi-key": rapid_api_key,
            "x-rapidapi-host": "cricbuzz-cricket.p.rapidapi.com"
        }
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass

    # Sample/Fallback Cricket Data
    return {
        "type": "Featured Matches",
        "matches": [
            {
                "title": "IND vs AUS - T20 Series",
                "status": "India won by 18 runs",
                "score": "IND: 185/5 (20.0) | AUS: 167/9 (20.0)",
                "venue": "M. Chinnaswamy Stadium, Bengaluru"
            },
            {
                "title": "ENG vs NZ - ODI Match",
                "status": "In Progress (2nd Innings)",
                "score": "ENG: 290/8 (50.0) | NZ: 145/3 (24.2)",
                "venue": "Lord's, London"
            }
        ]
    }

@app.route('/')
def index():
    files = FileRecord.query.all()
    is_admin = session.get('is_admin', False)
    live_scores = fetch_live_cricket_data()
    return render_template('index.html', files=files, is_admin=is_admin, live_scores=live_scores)

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'admin123')
        if password == admin_pass:
            session['is_admin'] = True
            flash('Welcome back to CrixData Admin!')
            return redirect(url_for('index'))
        else:
            flash('Incorrect Admin Password!')
    return render_template('admin.html')

@app.route('/logout')
def logout():
    session.pop('is_admin', None)
    flash('Logged out from CrixData Admin.')
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if not session.get('is_admin'):
        flash('Unauthorized action!')
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
        flash('Cricket File Vault Updated Successfully!')
    return redirect(url_for('index'))

@app.route('/delete/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    if not session.get('is_admin'):
        flash('Unauthorized action!')
        return redirect(url_for('index'))

    file_item = FileRecord.query.get_or_404(file_id)
    cloudinary.uploader.destroy(file_item.public_id, invalidate=True)
    db.session.delete(file_item)
    db.session.commit()
    flash('File removed permanently!')
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

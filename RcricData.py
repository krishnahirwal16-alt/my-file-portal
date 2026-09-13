import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# PostgreSQL Database Configuration
db_url = os.environ.get('DATABASE_URL', 'sqlite:///files.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Cloudinary Configuration
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)

# Database Model
class FileRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    public_id = db.Column(db.String(200), nullable=False)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    files = FileRecord.query.all()
    return render_template('index.html', files=files)

@app.route('/upload', methods=['POST'])
def upload_file():
    title = request.form.get('title')
    file = request.files.get('file')
    
    if file and title:
        # Upload directly to Cloudinary
        upload_result = cloudinary.uploader.upload(file, resource_type="auto")
        
        # Save link & metadata into PostgreSQL
        new_file = FileRecord(
            title=title,
            file_url=upload_result['secure_url'],
            public_id=upload_result['public_id']
        )
        db.session.add(new_file)
        db.session.commit()
        flash('File uploaded successfully!')
    return redirect(url_for('index'))

@app.route('/delete/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    file_item = FileRecord.query.get_or_404(file_id)
    
    # Delete from Cloudinary
    cloudinary.uploader.destroy(file_item.public_id, invalidate=True)
    
    # Delete from PostgreSQL
    db.session.delete(file_item)
    db.session.commit()
    flash('File deleted permanently!')
    return redirect(url_for('index'))

@app.route('/api/search')
def search():
    query = request.args.get('q', '')
    if query:
        results = FileRecord.query.filter(FileRecord.title.ilike(f'%{query}%')).all()
    else:
        results = FileRecord.query.all()
    return jsonify([{'id': f.id, 'title': f.title, 'url': f.file_url} for f in results])

if __name__ == '__main__':
    app.run(debug=True)

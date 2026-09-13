import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key_123')

# Database Configuration
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
    is_admin = session.get('is_admin', False)
    return render_template('index.html', files=files, is_admin=is_admin)

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'admin123')
        if password == admin_pass:
            session['is_admin'] = True
            flash('Admin access granted!')
            return redirect(url_for('index'))
        else:
            flash('Incorrect Password!')
    return render_template('admin.html')

@app.route('/logout')
def logout():
    session.pop('is_admin', None)
    flash('Logged out successfully.')
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if not session.get('is_admin'):
        flash('Unauthorized action!')
        return redirect(url_for('index'))
        
    title = request.form.get('title')
    file = request.files.get('file')
    
    if file and title:
        upload_result = cloudinary.uploader.upload(file, resource_type="auto")
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
    if not session.get('is_admin'):
        flash('Unauthorized action!')
        return redirect(url_for('index'))

    file_item = FileRecord.query.get_or_404(file_id)
    cloudinary.uploader.destroy(file_item.public_id, invalidate=True)
    db.session.delete(file_item)
    db.session.commit()
    flash('File deleted permanently!')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)

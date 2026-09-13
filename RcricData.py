import os
from flask import Flask, render_template_string, request, redirect, session, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'mysecretkey123'

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///files_data.db'
db = SQLAlchemy(app)

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

USER_CREDENTIALS = {"admin": "1234"}

class FileRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    custom_name = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(200), nullable=False)

with app.app_context():
    db.create_all()

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Live Search File Portal</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .main-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 16px;
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.2);
            width: 100%;
            max-width: 650px;
        }
        .suggestions-box {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            z-index: 1000;
            background: white;
            border-radius: 8px;
            box-shadow: 0 8px 16px rgba(0,0,0,0.15);
            max-height: 200px;
            overflow-y: auto;
            display: none;
        }
        .suggestion-item {
            padding: 10px 15px;
            cursor: pointer;
            border-bottom: 1px solid #eee;
        }
        .suggestion-item:hover {
            background-color: #f0f4ff;
        }
    </style>
</head>
<body>

    <div class="main-card p-4 p-md-5 m-3">
        {% if not logged_in %}
            <!-- LOGIN SECTION -->
            <div class="text-center mb-4">
                <i class="fa-solid fa-user-shield fa-3x text-primary mb-2"></i>
                <h3 class="fw-bold">Welcome Back</h3>
            </div>
            
            {% if error %}
                <div class="alert alert-danger py-2 text-center">{{ error }}</div>
            {% endif %}

            <form method="POST" action="/login">
                <div class="mb-3">
                    <label class="form-label fw-semibold">Username</label>
                    <input type="text" name="username" class="form-control" required>
                </div>
                <div class="mb-4">
                    <label class="form-label fw-semibold">Password</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                <button type="submit" class="btn btn-primary w-100 py-2 fw-bold">Login</button>
            </form>

        {% else %}
            <!-- FILE MANAGER SECTION -->
            <div class="d-flex justify-content-between align-items-center mb-4 border-bottom pb-3">
                <h4 class="fw-bold m-0 text-dark"><i class="fa-solid fa-folder-open text-warning me-2"></i>File Manager</h4>
                <a href="/logout" class="btn btn-outline-danger btn-sm rounded-pill">Logout</a>
            </div>
            
            <!-- UPLOAD FORM -->
            <form method="POST" action="/upload" enctype="multipart/form-data" class="mb-4 bg-light p-3 rounded border">
                <div class="mb-2">
                    <label class="form-label fw-semibold">File Ka Display Name:</label>
                    <input type="text" name="custom_name" class="form-control" placeholder="E.g., Math Project..." required>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">File Select Karein:</label>
                    <input type="file" name="file" class="form-control" required>
                </div>
                <button type="submit" class="btn btn-success fw-bold w-100">Upload File</button>
            </form>

            <!-- LIVE SEARCH BAR -->
            <form method="GET" action="/" class="mb-4 position-relative">
                <div class="input-group">
                    <input type="text" id="searchInput" name="search" class="form-control" placeholder="Type first letter to get suggestions..." value="{{ search_query }}" autocomplete="off">
                    <button type="submit" class="btn btn-primary"><i class="fa-solid fa-magnifying-glass"></i> Search</button>
                    {% if search_query %}
                        <a href="/" class="btn btn-outline-secondary">Clear</a>
                    {% endif %}
                </div>
                <!-- Live Suggestions Container -->
                <div id="suggestionsBox" class="suggestions-box"></div>
            </form>

            <!-- FILE LIST -->
            <h5 class="fw-bold mb-3 text-secondary">Saved Files ({{ records|length }}):</h5>
            
            {% if records %}
                <div class="list-group">
                    {% for item in records %}
                        <div class="list-group-item d-flex justify-content-between align-items-center border rounded mb-2">
                            <div>
                                <h6 class="mb-0 fw-bold text-dark">{{ item.custom_name }}</h6>
                                <a href="/uploads/{{ item.filename }}" target="_blank" class="text-decoration-none small text-primary">
                                    <i class="fa-regular fa-file-lines me-1"></i>Open File ({{ item.filename }})
                                </a>
                            </div>
                            <form method="POST" action="/delete/{{ item.id }}" class="m-0">
                                <button type="submit" class="btn btn-danger btn-sm"><i class="fa-solid fa-trash-can"></i></button>
                            </form>
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <p class="text-muted text-center py-3 border rounded bg-light">No files found.</p>
            {% endif %}

        {% endif %}
    </div>

    <!-- JAVASCRIPT FOR AUTO-SUGGESTION -->
    <script>
        const searchInput = document.getElementById('searchInput');
        const suggestionsBox = document.getElementById('suggestionsBox');

        if (searchInput) {
            searchInput.addEventListener('input', function() {
                const query = this.value.trim();

                if (query.length > 0) {
                    // Backend API se suggestions fetch karein
                    fetch(`/api/search?q=${encodeURIComponent(query)}`)
                        .then(response => response.json())
                        .then(data => {
                            suggestionsBox.innerHTML = '';
                            if (data.length > 0) {
                                data.forEach(item => {
                                    const div = document.createElement('div');
                                    div.className = 'suggestion-item';
                                    div.innerHTML = `<i class="fa-solid fa-font me-2 text-primary"></i><b>${item.custom_name}</b>`;
                                    
                                    // Click karne par input fill ho jayega aur search submit hoga
                                    div.onclick = function() {
                                        searchInput.value = item.custom_name;
                                        suggestionsBox.style.display = 'none';
                                        searchInput.form.submit();
                                    };
                                    suggestionsBox.appendChild(div);
                                });
                                suggestionsBox.style.display = 'block';
                            } else {
                                suggestionsBox.style.display = 'none';
                            }
                        });
                } else {
                    suggestionsBox.style.display = 'none';
                }
            });

            // Page par kahin aur click hone par suggestions chhup jayein
            document.addEventListener('click', function(e) {
                if (e.target !== searchInput) {
                    suggestionsBox.style.display = 'none';
                }
            });
        }
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    logged_in = session.get('logged_in', False)
    search_query = request.args.get('search', '').strip()
    
    if logged_in:
        if search_query:
            records = FileRecord.query.filter(FileRecord.custom_name.ilike(f'%{search_query}%')).all()
        else:
            records = FileRecord.query.all()
    else:
        records = []
        
    return render_template_string(HTML_TEMPLATE, logged_in=logged_in, records=records, search_query=search_query)

# API Route Live Suggestions ke liye (Jo input ke sath dynamic data bhejega)
@app.route('/api/search')
def api_search():
    if not session.get('logged_in'):
        return jsonify([])
    
    query = request.args.get('q', '').strip()
    if query:
        # Starting letter ya text se match karne wali top 5 files fetch honge
        results = FileRecord.query.filter(FileRecord.custom_name.ilike(f'{query}%')).limit(5).all()
        return jsonify([{'id': r.id, 'custom_name': r.custom_name} for r in results])
    return jsonify([])

@app.route('/login', methods=['POST'])
def login():
    uname = request.form.get('username')
    pwd = request.form.get('password')
    if USER_CREDENTIALS.get(uname) == pwd:
        session['logged_in'] = True
        return redirect('/')
    return render_template_string(HTML_TEMPLATE, logged_in=False, error="Invalid Username or Password!")

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect('/')

@app.route('/upload', methods=['POST'])
def upload_file():
    if not session.get('logged_in'):
        return redirect('/')
    
    custom_name = request.form.get('custom_name')
    file = request.files.get('file')
    
    if file and file.filename != '':
        filename = file.filename
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        new_record = FileRecord(custom_name=custom_name, filename=filename)
        db.session.add(new_record)
        db.session.commit()
        
    return redirect('/')

@app.route('/uploads/<filename>')
def display_file(filename):
    if not session.get('logged_in'):
        return redirect('/')
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/delete/<int:record_id>', methods=['POST'])
def delete_file(record_id):
    if not session.get('logged_in'):
        return redirect('/')
    
    record = FileRecord.query.get(record_id)
    if record:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], record.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        db.session.delete(record)
        db.session.commit()
        
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
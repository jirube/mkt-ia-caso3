from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import base64
import datetime
from bedrock_client import generate_image, edit_text_content

app = Flask(__name__)
app.config['SECRET_KEY'] = 'clave-secreta-jimmy-segura'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///marketing.db'
app.config['UPLOAD_FOLDER'] = 'static/images'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- 4.4 MODERACIÓN ---
BANNED_KEYWORDS = ['violencia', 'droga', 'sangre', 'odio', 'racismo', 'desnudo', 'nude', 'blood', 'hate']

def moderate_content(text):
    if not text: return False, "Texto vacío"
    text_lower = text.lower()
    for word in BANNED_KEYWORDS:
        if word in text_lower:
            return True, f"⚠️ CONTENIDO BLOQUEADO: Se detectó el término prohibido '{word}'. Por políticas de seguridad, petición rechazada."
    return False, "OK"

# --- MODELOS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password_hash = db.Column(db.String(200)) 
    role = db.Column(db.String(50))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class ContentHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action_type = db.Column(db.String(50))
    prompt_or_input = db.Column(db.Text)
    result_path_or_text = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content_id = db.Column(db.Integer, db.ForeignKey('content_history.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    text = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- INICIALIZACIÓN DE DB ---
with app.app_context():
    # Solo crea las tablas si no existen (no borra datos)
    db.create_all()
    
    # Solo crear usuarios si no existen
    if User.query.count() == 0:
        users_data = [
            ("Jimmy_Admin", "admin123", "admin"), 
            ("Ana_Disenador", "diseno123", "disenador"), 
            ("Luis_Redactor", "redactor123", "redactor")
        ]
        for name, pwd, role in users_data:
            new_user = User(username=name, role=role)
            new_user.set_password(pwd)
            db.session.add(new_user)
        
        db.session.commit()
        print("✅ Base de datos inicializada: Usuarios creados.")
    else:
        print("✅ Base de datos existente cargada.")

# --- RUTAS ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            error = "Credenciales inválidas"
    all_users = User.query.all()
    return render_template('login.html', users=all_users, error=error)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('dashboard.html', user=current_user)

@app.route('/api/generate-image', methods=['POST'])
@login_required
def api_gen_image():
    if current_user.role == 'redactor': return jsonify({"error": "⛔ Rol no autorizado"}), 403
    data = request.json
    prompt = data.get('prompt')
    is_flagged, message = moderate_content(prompt)
    if is_flagged: return jsonify({"error": message}), 400
    img_base64 = generate_image(prompt, data.get('style'))
    if img_base64:
        filename = f"img_{datetime.datetime.now().timestamp()}.png"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(filepath, "wb") as fh: fh.write(base64.b64decode(img_base64))
        log = ContentHistory(user_id=current_user.id, action_type='image_gen', prompt_or_input=prompt, result_path_or_text=filename)
        db.session.add(log)
        db.session.commit()
        return jsonify({"image_url": f"/static/images/{filename}", "status": "success"})
    return jsonify({"error": "Fallo generación"}), 500

@app.route('/api/edit-text', methods=['POST'])
@login_required
def api_edit_text():
    if current_user.role == 'disenador': return jsonify({"error": "⛔ Rol no autorizado"}), 403
    data = request.json
    text = data.get('text')
    is_flagged, message = moderate_content(text)
    if is_flagged: return jsonify({"error": message}), 400
    full_instruction = f"{data.get('action_type')}: {data.get('instruction', '')}"
    new_text = edit_text_content(text, full_instruction)
    log = ContentHistory(user_id=current_user.id, action_type='text_edit', prompt_or_input=text, result_path_or_text=new_text)
    db.session.add(log)
    db.session.commit()
    return jsonify({"result": new_text})

@app.route('/api/add-comment', methods=['POST'])
@login_required
def add_comment():
    data = request.json
    is_flagged, message = moderate_content(data.get('text'))
    if is_flagged: return jsonify({"error": message}), 400
    new_comment = Comment(content_id=data.get('content_id'), user_id=current_user.id, text=data.get('text'))
    db.session.add(new_comment)
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/get-comments/<int:content_id>')
@login_required
def get_comments(content_id):
    comments = Comment.query.filter_by(content_id=content_id).order_by(Comment.timestamp.asc()).all()
    data = [{"user": User.query.get(c.user_id).username, "text": c.text, "date": c.timestamp.strftime("%Y-%m-%d %H:%M")} for c in comments]
    return jsonify(data)

@app.route('/api/history-full')
@login_required
def history_full():
    logs = ContentHistory.query.order_by(ContentHistory.timestamp.desc()).limit(50).all()
    data = []
    for l in logs:
        item = {"id": l.id, "user": User.query.get(l.user_id).username, "action": l.action_type, "date": l.timestamp.strftime("%Y-%m-%d %H:%M"), "original": l.prompt_or_input, "result": l.result_path_or_text, "comments": Comment.query.filter_by(content_id=l.id).count()}
        if l.action_type == 'image_gen': item['url'] = f"/static/images/{l.result_path_or_text}"
        data.append(item)
    return jsonify(data)

@app.route('/history')
@login_required
def get_history():
    logs = ContentHistory.query.order_by(ContentHistory.timestamp.desc()).limit(20).all()
    data = [{"user": User.query.get(l.user_id).username, "action": l.action_type, "date": l.timestamp.strftime("%Y-%m-%d %H:%M"), "result": l.result_path_or_text} for l in logs]
    return jsonify(data)

@app.route('/api/my-images')
@login_required
def my_images():
    query = ContentHistory.query.filter_by(action_type='image_gen')
    if current_user.role != 'admin': query = query.filter_by(user_id=current_user.id)
    imgs = query.order_by(ContentHistory.timestamp.desc()).limit(50).all()
    data = [{"filename": i.result_path_or_text, "prompt": i.prompt_or_input, "date": i.timestamp.strftime("%Y-%m-%d %H:%M"), "url": f"/static/images/{i.result_path_or_text}"} for i in imgs]
    return jsonify(data)

@app.route('/api/text-history')
@login_required
def text_history():
    """Obtiene historial de ediciones de texto para comparar y revertir"""
    query = ContentHistory.query.filter_by(action_type='text_edit')
    if current_user.role != 'admin':
        query = query.filter_by(user_id=current_user.id)
    edits = query.order_by(ContentHistory.timestamp.desc()).limit(30).all()
    data = [{
        "id": e.id,
        "user": User.query.get(e.user_id).username,
        "original": e.prompt_or_input,
        "result": e.result_path_or_text,
        "date": e.timestamp.strftime("%Y-%m-%d %H:%M")
    } for e in edits]
    return jsonify(data)

@app.route('/api/all-history')
@login_required
def all_history():
    """Historial completo: Admin ve todo, otros solo lo suyo"""
    query = ContentHistory.query
    if current_user.role != 'admin':
        query = query.filter_by(user_id=current_user.id)
    logs = query.order_by(ContentHistory.timestamp.desc()).limit(100).all()
    data = []
    for l in logs:
        item = {
            "id": l.id,
            "user": User.query.get(l.user_id).username,
            "action": l.action_type,
            "input": l.prompt_or_input[:100] + "..." if len(l.prompt_or_input) > 100 else l.prompt_or_input,
            "result": l.result_path_or_text[:100] + "..." if len(l.result_path_or_text) > 100 else l.result_path_or_text,
            "date": l.timestamp.strftime("%Y-%m-%d %H:%M")
        }
        if l.action_type == 'image_gen':
            item['image_url'] = f"/static/images/{l.result_path_or_text}"
        data.append(item)
    return jsonify(data)
if __name__ == '__main__':
    app.run(debug=True, port=5000)

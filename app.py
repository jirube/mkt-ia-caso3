from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
import os
import base64
import datetime
from bedrock_client import generate_image, edit_text_content

app = Flask(__name__)
app.config['SECRET_KEY'] = 'clave-secreta-jimmy'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///marketing.db'
app.config['UPLOAD_FOLDER'] = 'static/images'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- MODELOS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    role = db.Column(db.String(50))

class ContentHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action_type = db.Column(db.String(50))
    prompt_or_input = db.Column(db.Text)
    result_path_or_text = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

# NUEVO: Tabla de Comentarios para Colaboración
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content_id = db.Column(db.Integer, db.ForeignKey('content_history.id')) # Enlace al contenido
    user_id = db.Column(db.Integer, db.ForeignKey('user.id')) # Quién comentó
    text = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- INICIALIZAR DB ---
with app.app_context():
    db.create_all()
    users = [("JimmyAdmin", "admin"), ("AnaDiseno", "disenador"), ("LuisRedactor", "redactor")]
    for name, role in users:
        if not User.query.filter_by(username=name).first():
            db.session.add(User(username=name, role=role))
    db.session.commit()

# --- RUTAS BÁSICAS ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        user = User.query.filter_by(username=username).first()
        if user:
            login_user(user)
            return redirect(url_for('index'))
    all_users = User.query.all()
    return render_template('login.html', users=all_users)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('dashboard.html', user=current_user)

# --- RUTAS API GENERACIÓN ---
@app.route('/api/generate-image', methods=['POST'])
@login_required
def api_gen_image():
    if current_user.role == 'redactor':
        return jsonify({"error": "⛔ Rol no autorizado"}), 403
    
    data = request.json
    img_base64 = generate_image(data.get('prompt'), data.get('style'))
    
    if img_base64:
        filename = f"img_{datetime.datetime.now().timestamp()}.png"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "wb") as fh:
            fh.write(base64.b64decode(img_base64))
        
        log = ContentHistory(user_id=current_user.id, action_type='image_gen', prompt_or_input=data.get('prompt'), result_path_or_text=filename)
        db.session.add(log)
        db.session.commit()
        return jsonify({"image_url": f"/static/images/{filename}", "status": "success"})
    return jsonify({"error": "Fallo generación"}), 500

@app.route('/api/edit-text', methods=['POST'])
@login_required
def api_edit_text():
    if current_user.role == 'disenador':
        return jsonify({"error": "⛔ Rol no autorizado"}), 403
    
    data = request.json
    # Concatenamos la acción específica (ej. Traducir) con el texto
    full_instruction = f"{data.get('action_type')}: {data.get('instruction', '')}"
    new_text = edit_text_content(data.get('text'), full_instruction)
    
    log = ContentHistory(user_id=current_user.id, action_type='text_edit', prompt_or_input=data.get('text'), result_path_or_text=new_text)
    db.session.add(log)
    db.session.commit()
    return jsonify({"result": new_text})

# --- RUTAS DE COLABORACIÓN (COMENTARIOS) ---
@app.route('/api/add-comment', methods=['POST'])
@login_required
def add_comment():
    data = request.json
    new_comment = Comment(
        content_id=data.get('content_id'),
        user_id=current_user.id,
        text=data.get('text')
    )
    db.session.add(new_comment)
    db.session.commit()
    return jsonify({"status": "success", "user": current_user.username, "date": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")})

@app.route('/api/get-comments/<int:content_id>')
@login_required
def get_comments(content_id):
    comments = Comment.query.filter_by(content_id=content_id).order_by(Comment.timestamp.asc()).all()
    data = []
    for c in comments:
        u = User.query.get(c.user_id)
        data.append({
            "user": u.username,
            "text": c.text,
            "date": c.timestamp.strftime("%Y-%m-%d %H:%M")
        })
    return jsonify(data)

# --- RUTAS DATOS ---
@app.route('/api/history-full')
@login_required
def history_full():
    # Devuelve historial con ID para poder comentar
    query = ContentHistory.query.order_by(ContentHistory.timestamp.desc()).limit(50)
    logs = query.all()
    
    data = []
    for l in logs:
        u_name = User.query.get(l.user_id).username
        # Contamos cuántos comentarios tiene cada item
        comment_count = Comment.query.filter_by(content_id=l.id).count()
        
        item = {
            "id": l.id,
            "user": u_name,
            "action": l.action_type,
            "date": l.timestamp.strftime("%Y-%m-%d %H:%M"),
            "original": l.prompt_or_input,
            "result": l.result_path_or_text,
            "comments": comment_count
        }
        
        if l.action_type == 'image_gen':
            item['url'] = f"/static/images/{l.result_path_or_text}"
        
        data.append(item)
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True, port=5000)

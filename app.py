from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
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

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Si no estás logueado, te manda al login

# --- MODELOS BD ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    role = db.Column(db.String(50)) # 'admin', 'disenador', 'redactor'

class ContentHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action_type = db.Column(db.String(50))
    prompt_or_input = db.Column(db.Text)
    result_path_or_text = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- INICIALIZACIÓN DE DATOS (SEED) ---
with app.app_context():
    db.create_all()
    # Creamos 3 usuarios con roles distintos para la demo
    users = [
        ("JimmyAdmin", "admin"),
        ("AnaDiseno", "disenador"),
        ("LuisRedactor", "redactor")
    ]
    for name, role in users:
        if not User.query.filter_by(username=name).first():
            db.session.add(User(username=name, role=role))
    db.session.commit()

# --- RUTAS DE ACCESO ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        user = User.query.filter_by(username=username).first()
        if user:
            login_user(user)
            return redirect(url_for('index'))
    # Mostrar pantalla de selección de usuario
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

# --- APIs CON PERMISOS POR ROL ---

@app.route('/api/generate-image', methods=['POST'])
@login_required
def api_gen_image():
    # RESTRICCIÓN DE ROL: Los redactores NO pueden generar imágenes
    if current_user.role == 'redactor':
        return jsonify({"error": "⛔ Acceso Denegado: Tu rol de 'Redactor' no permite generar imágenes."}), 403

    data = request.json
    prompt = data.get('prompt')
    style = data.get('style')
    
    forbidden = ["violencia", "odio", "desnudo", "sangre"]
    if any(w in prompt.lower() for w in forbidden):
        return jsonify({"error": "Contenido bloqueado por política ética."}), 400

    img_base64 = generate_image(prompt, style)
    
    if img_base64:
        filename = f"img_{datetime.datetime.now().timestamp()}.png"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(filepath, "wb") as fh:
            fh.write(base64.b64decode(img_base64))
        
        log = ContentHistory(user_id=current_user.id, action_type='image_gen', prompt_or_input=prompt, result_path_or_text=filename)
        db.session.add(log)
        db.session.commit()
        return jsonify({"image_url": f"/static/images/{filename}", "status": "success"})
    return jsonify({"error": "Fallo en AWS Bedrock"}), 500

@app.route('/api/edit-text', methods=['POST'])
@login_required
def api_edit_text():
    # RESTRICCIÓN DE ROL: Los diseñadores NO pueden editar texto
    if current_user.role == 'disenador':
        return jsonify({"error": "⛔ Acceso Denegado: Tu rol de 'Diseñador' no permite editar textos."}), 403

    data = request.json
    text = data.get('text')
    instruction = data.get('instruction')
    
    new_text = edit_text_content(text, instruction)
    
    log = ContentHistory(user_id=current_user.id, action_type='text_edit', prompt_or_input=text, result_path_or_text=new_text)
    db.session.add(log)
    db.session.commit()
    
    return jsonify({"result": new_text})

@app.route('/history')
@login_required
def get_history():
    # El Admin ve todo. Los empleados solo ven lo suyo.
    if current_user.role == 'admin':
        logs = ContentHistory.query.order_by(ContentHistory.timestamp.desc()).limit(20).all()
    else:
        logs = ContentHistory.query.filter_by(user_id=current_user.id).order_by(ContentHistory.timestamp.desc()).limit(10).all()
        
    data = []
    for l in logs:
        # Recuperamos nombre del usuario para mostrar en tabla
        u_name = User.query.get(l.user_id).username
        data.append({
            "user": u_name,
            "action": l.action_type, 
            "date": l.timestamp.strftime("%Y-%m-%d %H:%M"), 
            "result": l.result_path_or_text
        })
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True, port=5000)

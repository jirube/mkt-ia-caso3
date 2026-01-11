from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user
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
login_manager.login_view = 'index'

# --- MODELOS BD ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)

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

# --- CORRECCIÓN: Crear BD al iniciar, compatible con Render ---
with app.app_context():
    db.create_all()
    # Crear usuario admin si no existe
    if not User.query.filter_by(username="JimmyRugel").first():
        admin = User(username="JimmyRugel")
        db.session.add(admin)
        db.session.commit()

@app.route('/')
def index():
    # Login automático seguro
    user = User.query.filter_by(username="JimmyRugel").first()
    login_user(user)
    return render_template('dashboard.html')

@app.route('/api/generate-image', methods=['POST'])
@login_required
def api_gen_image():
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
    logs = ContentHistory.query.order_by(ContentHistory.timestamp.desc()).limit(10).all()
    data = [{"action": l.action_type, "date": l.timestamp.strftime("%Y-%m-%d %H:%M"), "result": l.result_path_or_text} for l in logs]
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True, port=5000)

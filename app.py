import os
import re
import unicodedata
import uuid
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "Open196!_System_Rozprawek_2024" # Klucz do sesji logowania

# Konfiguracja bazy danych
database_url = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# DANE DO LOGOWANIA
ADMIN_CREDENTIALS = {
    "Julia": "Open196!",
    "Kuba": "Open196!"
}

# DEKORATOR ZABEZPIECZAJĄCY PANEL ADMINA
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# MODELE BAZY DANYCH (v4)
class Student(db.Model):
    __tablename__ = 'student_v4'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url_slug = db.Column(db.String(150), unique=True, nullable=False)
    exam_unlocked = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    essays = db.relationship('Essay', backref='student', lazy=True)

class Essay(db.Model):
    __tablename__ = 'essay_v4'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    topic_full = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, default="")
    is_exam = db.Column(db.Boolean, default=False)
    time_spent = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, nullable=True)
    last_edited_at = db.Column(db.DateTime, nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    feedback = db.Column(db.Text, nullable=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student_v4.id'), nullable=False)

class Notification(db.Model):
    __tablename__ = 'notification_v4'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

with app.app_context():
    db.create_all()

# FUNKCJE POMOCNICZE
def slugify(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')

PRACTICE_TOPICS = [
    ("Teachers Computers", "As computers are being used more and more in education, there will be no role for teachers in the classroom. Give reasons for your answer and include any relevant examples from your own knowledge and experience."),
    ("Fluency", "Some people believe that the only way to become fluent in a foreign language is to live and work in a country where it is spoken. Do you agree or disagree with this statement? Give reasons for your answer and include any relevant examples from your own knowledge or experience."),
    ("Violence", "Violence in the media promotes violence in real life. Do you agree with that statement or disagree ? Give reasons for your answer and include any relevant examples from your own knowledge."),
    ("Fast food", "Fast food has become increasingly popular in many parts of the world due to its convenience and affordability. However, some people argue that it has negative effects on health and society. Discuss the advantages and disadvantages of eating fast food and give your own opinion."),
    ("Generations", "Young people should be encouraged to meet their grandparents more often, as this benefits both generations. Do you agree or disagree with this statement? Give reasons for your answer and include any relevant examples from your own knowledge and experience."),
    ("Boxing", "Some people believe that boxing is a dangerous sport that should be discouraged, while others argue that boxing is a valuable form of self-expression and personal development. What is your opinion? Include relevant examples from your own experience to support your answer.")
]

EXAM_TOPICS = [
    "Some people think it is beneficial for old people to learn something new, while others believe that once a person is past 65 years of age it is too late to learn. Do you agree or disagree? Give reasons using your own knowledge and examples from your own experience.",
    "Some people think that introducing children to team sports is the best way to teach children teamwork. Do you agree or disagree? Give reasons using your own knowledge and examples from your own experience."
]

# --- LOGOWANIE ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in ADMIN_CREDENTIALS and ADMIN_CREDENTIALS[username] == password:
            session['admin_user'] = username
            return redirect(url_for('admin'))
        return render_template('login.html', error="Błędny login lub hasło")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin_user', None)
    return redirect(url_for('login'))

# --- PANEL ADMINA ---
@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    if request.method == 'POST':
        student_name = request.form.get('name')
        slug = f"{uuid.uuid4().hex[:4]}-{slugify(student_name)}"
        new_student = Student(name=student_name, url_slug=slug)
        db.session.add(new_student)
        for title, full_topic in PRACTICE_TOPICS:
            db.session.add(Essay(title=title, topic_full=full_topic, is_exam=False, student=new_student))
        db.session.add(Essay(title="Egzamin (Wybierz temat)", is_exam=True, student=new_student))
        db.session.commit()
        return redirect(url_for('admin'))
        
    active_students = Student.query.filter_by(is_archived=False).all()
    archived_students = Student.query.filter_by(is_archived=True).all()
    notifications = Notification.query.order_by(Notification.created_at.desc()).limit(10).all()
    return render_template('admin.html', active_students=active_students, archived_students=archived_students, notifications=notifications)

@app.route('/admin/student/<int:student_id>')
@admin_required
def admin_student_detail(student_id):
    student = Student.query.get_or_404(student_id)
    return render_template('student_detail.html', student=student)

@app.route('/admin/student/<int:student_id>/unlock', methods=['POST'])
@admin_required
def unlock_exam_individual(student_id):
    student = Student.query.get_or_404(student_id)
    student.exam_unlocked = True
    db.session.commit()
    return redirect(url_for('admin_student_detail', student_id=student_id))

@app.route('/admin/student/<int:student_id>/archive', methods=['POST'])
@admin_required
def toggle_archive(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_archived = not student.is_archived
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/essay/<int:essay_id>/feedback', methods=['POST'])
@admin_required
def save_feedback(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    essay.feedback = request.form.get('feedback')
    db.session.commit()
    return redirect(url_for('admin_student_detail', student_id=essay.student_id))

@app.route('/admin/preview/<int:essay_id>')
@admin_required
def preview_essay(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    return render_template('preview.html', essay=essay)

@app.route('/admin/notif/clear', methods=['POST'])
@admin_required
def clear_notifs():
    Notification.query.delete()
    db.session.commit()
    return redirect(url_for('admin'))

# --- STUDENT ---
@app.route('/student/<url_slug>')
def student_dashboard(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    return render_template('student.html', student=student, exam_topics=EXAM_TOPICS)

@app.route('/student/<url_slug>/choose_exam', methods=['POST'])
def choose_exam(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    if not student.exam_unlocked: return "Zablokowane", 403
    topic_idx = int(request.form.get('topic_idx'))
    exam_essay = Essay.query.filter_by(student_id=student.id, is_exam=True).first()
    if not exam_essay.topic_full:
        exam_essay.topic_full = EXAM_TOPICS[topic_idx]
        exam_essay.title = f"EGZAMIN: Temat {topic_idx + 1}"
        db.session.commit()
    return redirect(url_for('write_essay', essay_id=exam_essay.id))

@app.route('/write/<int:essay_id>')
def write_essay(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    return render_template('write.html', essay=essay)

@app.route('/api/save/<int:essay_id>', methods=['POST'])
def auto_save(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    data = request.get_json()
    essay.content = data.get('content', essay.content)
    essay.time_spent = data.get('time_spent', essay.time_spent)
    
    became_completed = False
    if data.get('is_completed') and not essay.is_completed:
        essay.is_completed = True
        became_completed = True
    
    now = datetime.now()
    if not essay.started_at: essay.started_at = now
    essay.last_edited_at = now
    db.session.commit()

    if became_completed:
        db.session.add(Notification(message=f"Student {essay.student.name} ukończył rozprawkę: '{essay.title}'"))
        db.session.commit()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)

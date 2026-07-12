import os
import re
import unicodedata
import uuid
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = "Open196!_System_Rozprawek_2024"

UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

database_url = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ----------------- STARE I WSPÓLNE MODELE -----------------

teacher_university = db.Table('teacher_university',
    db.Column('teacher_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE')),
    db.Column('university_id', db.Integer, db.ForeignKey('universities.id', ondelete='CASCADE'))
)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='teacher', nullable=False)
    smtp_email = db.Column(db.String(120), nullable=True)
    smtp_password = db.Column(db.String(120), nullable=True)
    email_template = db.Column(db.Text, nullable=True)
    universities = db.relationship('University', secondary=teacher_university, backref='teachers')

class University(db.Model):
    __tablename__ = 'universities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email_template = db.Column(db.Text, nullable=True)
    materials = db.relationship('Material', backref='university', lazy=True, cascade="all, delete-orphan")
    students = db.relationship('Student', backref='university', lazy=True)

class Material(db.Model):
    __tablename__ = 'materials'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content_url = db.Column(db.String(500), nullable=False) 
    category = db.Column(db.String(50), default='interview')
    university_id = db.Column(db.Integer, db.ForeignKey('universities.id', ondelete='CASCADE'), nullable=False)

class QaTopic(db.Model):
    __tablename__ = 'qa_topics'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    topic_full = db.Column(db.Text, nullable=False)
    order_index = db.Column(db.Integer, default=0)

class MathQuestion(db.Model):
    __tablename__ = 'math_questions'
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    opt_a = db.Column(db.String(200), nullable=False)
    opt_b = db.Column(db.String(200), nullable=False)
    opt_c = db.Column(db.String(200), nullable=False)
    opt_d = db.Column(db.String(200), nullable=False)
    answer = db.Column(db.String(1), nullable=False)
    university_id = db.Column(db.Integer, db.ForeignKey('universities.id'), nullable=True)

class GbsMajor(db.Model):
    __tablename__ = 'gbs_majors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    is_cccu = db.Column(db.Boolean, default=False)

class GbsIntake(db.Model):
    __tablename__ = 'gbs_intakes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(20), default='#007bff')

class GbsQuestionSet(db.Model):
    __tablename__ = 'gbs_question_sets'
    id = db.Column(db.Integer, primary_key=True)
    intake_id = db.Column(db.Integer, db.ForeignKey('gbs_intakes.id', ondelete='CASCADE'))
    major_id = db.Column(db.Integer, db.ForeignKey('gbs_majors.id', ondelete='CASCADE'))
    q1 = db.Column(db.Text, default="")
    q2 = db.Column(db.Text, default="")
    q3 = db.Column(db.Text, default="")
    intake = db.relationship('GbsIntake', backref='question_sets')
    major = db.relationship('GbsMajor', backref='question_sets')

class GbsAttempt(db.Model):
    __tablename__ = 'gbs_attempts'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student_v5.id', ondelete='CASCADE'))
    q1_ans = db.Column(db.Text, default="")
    q2_ans = db.Column(db.Text, default="")
    q3_ans = db.Column(db.Text, default="")
    is_exam = db.Column(db.Boolean, default=False)
    submitted_at = db.Column(db.DateTime, default=datetime.now)

class MathTestResult(db.Model):
    __tablename__ = 'math_test_results'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student_v5.id', ondelete='CASCADE'))
    score = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=11)
    answers_json = db.Column(db.Text, default="{}")
    submitted_at = db.Column(db.DateTime, default=datetime.now)

class Student(db.Model):
    __tablename__ = 'student_v5'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url_slug = db.Column(db.String(150), unique=True, nullable=False)
    exam_unlocked = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    university_id = db.Column(db.Integer, db.ForeignKey('universities.id'), nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    email = db.Column(db.String(120), nullable=True)
    gbs_major_id = db.Column(db.Integer, db.ForeignKey('gbs_majors.id'), nullable=True)
    gbs_intake_id = db.Column(db.Integer, db.ForeignKey('gbs_intakes.id'), nullable=True)
    has_math_test = db.Column(db.Boolean, default=False)
    
    essays = db.relationship('Essay', backref='student', lazy=True, cascade="all, delete-orphan")
    gbs_attempts = db.relationship('GbsAttempt', backref='student', lazy=True, cascade="all, delete-orphan")
    math_results = db.relationship('MathTestResult', backref='student', lazy=True, cascade="all, delete-orphan")
    major = db.relationship('GbsMajor')
    intake = db.relationship('GbsIntake')

class Essay(db.Model):
    __tablename__ = 'essay_v5'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    topic_full = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, default="")
    marked_content = db.Column(db.Text, nullable=True) 
    chosen_topic = db.Column(db.String(255), nullable=True) 
    checklist_data = db.Column(db.String(200), default="none,none,none,none,none,none,none") 
    is_exam = db.Column(db.Boolean, default=False)
    time_spent = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, nullable=True)
    last_edited_at = db.Column(db.DateTime, nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    feedback = db.Column(db.Text, nullable=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student_v5.id'), nullable=False)

class Notification(db.Model):
    __tablename__ = 'notification_v5'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student_v5.id'), nullable=True)
    student = db.relationship('Student')


# ---------------- FUNKCJE POCZTOWE (GMAIL SMTP SYNCHRONICZNE - POPRAWKA RENDER) ----------------
def send_email_sync(sender_email, sender_password, recipient_email, subject, body):
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient_email

        # Zmiana: Port 465 (SSL) + wymuszony limit czasu na 7 sekund!
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=7)
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True, "Wysłano"
    except smtplib.SMTPAuthenticationError:
        return False, "Błąd autoryzacji: Złe hasło aplikacji Google lub e-mail."
    except TimeoutError:
        return False, "Serwer Render zablokował połączenie (Timeout). Google nie odpowiada."
    except Exception as e:
        return False, str(e)

def trigger_welcome_email(teacher, student, request_host):
    if not student.email or not teacher.smtp_email or not teacher.smtp_password:
        return False, "Nauczyciel nie ma uzupełnionego adresu e-mail / hasła aplikacji w systemie."
    
    # Określanie szablonu
    template = student.university.email_template if student.university and student.university.email_template else None
    if not template:
        template = teacher.email_template
    if not template:
        template = "Witaj {imie}!\n\nZostało utworzone Twoje konto. Twój link to:\n{link}\n\nPozdrawiamy!"
        
    # Wymuszenie HTTPS na Renderze
    link = f"https://{request_host}/student/{student.url_slug}"
    
    body = template.replace("{imie}", student.name).replace("{link}", link)
    subject = "Twój dostęp do platformy edukacyjnej"
    
    success, msg = send_email_sync(teacher.smtp_email, teacher.smtp_password, student.email, subject, body)
    return success, msg
# ---------------------------------------------------------------


# --- INITIAL DATA ---
def setup_database():
    db.create_all()
    queries = [
        'ALTER TABLE users ADD COLUMN smtp_email VARCHAR(120)',
        'ALTER TABLE users ADD COLUMN smtp_password VARCHAR(120)',
        'ALTER TABLE users ADD COLUMN email_template TEXT',
        'ALTER TABLE universities ADD COLUMN email_template TEXT',
        'ALTER TABLE student_v5 ADD COLUMN university_id INTEGER REFERENCES universities(id)',
        'ALTER TABLE student_v5 ADD COLUMN creator_id INTEGER REFERENCES users(id)',
        'ALTER TABLE student_v5 ADD COLUMN email VARCHAR(120)',
        'ALTER TABLE student_v5 ADD COLUMN gbs_major_id INTEGER REFERENCES gbs_majors(id)',
        'ALTER TABLE student_v5 ADD COLUMN gbs_intake_id INTEGER REFERENCES gbs_intakes(id)',
        'ALTER TABLE student_v5 ADD COLUMN has_math_test BOOLEAN DEFAULT FALSE',
        'ALTER TABLE student_v5 ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
        'ALTER TABLE notification_v5 ADD COLUMN recipient_id INTEGER REFERENCES users(id)',
        'ALTER TABLE notification_v5 ADD COLUMN student_id INTEGER REFERENCES student_v5(id)',
        'ALTER TABLE materials ADD COLUMN category VARCHAR(50) DEFAULT \'interview\'',
        'ALTER TABLE qa_topics ADD COLUMN order_index INTEGER DEFAULT 0',
        'ALTER TABLE math_questions ADD COLUMN university_id INTEGER REFERENCES universities(id)'
    ]
    for q in queries:
        try: db.session.execute(text(q)); db.session.commit()
        except Exception: db.session.rollback()

    qa_uni = University.query.filter_by(name="QA Higher Education").first() or University(name="QA Higher Education")
    gbs_uni = University.query.filter_by(name="GBS").first() or University(name="GBS")
    lcca_uni = University.query.filter_by(name="LCCA").first() or University(name="LCCA")
    db.session.add_all([qa_uni, gbs_uni, lcca_uni])
    db.session.commit()

    if not User.query.filter_by(username="Julia").first(): db.session.add(User(username="Julia", password_hash=generate_password_hash("Open196!"), role="admin"))
    if not User.query.filter_by(username="Kuba").first(): db.session.add(User(username="Kuba", password_hash=generate_password_hash("Open196!"), role="admin"))
    db.session.commit()

with app.app_context(): setup_database()

# ----------------- DEKORATORY I POMOCNICZE -----------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin': return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def slugify(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[-\s]+', '-', re.sub(r'[^\w\s-]', '', value.lower())).strip('-_')

def sort_students(students, sort_by):
    if sort_by == 'pending': students.sort(key=lambda s: sum(1 for e in s.essays if e.is_completed and not e.feedback), reverse=True)
    elif sort_by == 'alpha_desc': students.sort(key=lambda s: s.name.lower(), reverse=True)
    else: students.sort(key=lambda s: s.name.lower())
    return students

def get_dir_size(path):
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total

ARCHIVED_MSG = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Konto archiwalne</title></head>
<body style="text-align:center; padding: 50px; font-family: sans-serif; background: #f4f6f9;">
    <h2 style="color: #dc3545;">Konto archiwalne</h2>
    <p style="font-size: 18px;">Twoje konto nie jest już aktywne. Skontaktuj się z Open UK Study aby przywrócić dostęp do materiałów.</p>
</body></html>
"""

def check_archived(student):
    if student.is_archived: return ARCHIVED_MSG, 403
    return None

# ----------------- ŚCIEŻKI AUTORYZACJI -----------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            session.update({'user_id': user.id, 'username': user.username, 'role': user.role})
            return redirect(url_for('panel_master' if user.role == 'admin' else 'panel_dashboard'))
        return render_template('login.html', error="Błędny login lub hasło")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ----------------- PANEL KOORDYNACJI SYSTEMU PŁATFORMY (/panel) -----------------

@app.route('/panel')
@login_required
def panel_dashboard():
    user = User.query.get(session['user_id'])
    universities = University.query.all() if user.role == 'admin' else user.universities
    uni_ids = [u.id for u in universities]
    
    has_gbs = any("GBS" in u.name for u in universities)
    has_qa = any("QA" in u.name for u in universities)
    has_lcca = any("LCCA" in u.name for u in universities)
    
    majors = GbsMajor.query.all()
    intakes = GbsIntake.query.all()
    search_query = request.args.get('q', '').lower()
    sort_by = request.args.get('sort', 'alpha')
    
    students_query = Student.query.filter_by(is_archived=False)
    if user.role != 'admin':
        students_query = students_query.filter(Student.university_id.in_(uni_ids))
        notifications = Notification.query.join(Student, Notification.student_id == Student.id).filter(Student.university_id.in_(uni_ids)).order_by(Notification.created_at.desc()).limit(15).all()
    else:
        notifications = Notification.query.order_by(Notification.created_at.desc()).limit(15).all()
        
    if search_query: students_query = students_query.filter(db.func.lower(Student.name).contains(search_query))
    students = sort_students(students_query.all(), sort_by)
    
    qa_students = [s for s in students if s.university and 'QA' in s.university.name]
    gbs_students = [s for s in students if s.university and 'GBS' in s.university.name]
    lcca_students = [s for s in students if s.university and 'LCCA' in s.university.name]
    
    return render_template('panel_dashboard.html', qa_students=qa_students, gbs_students=gbs_students, lcca_students=lcca_students, universities=universities, majors=majors, intakes=intakes, teacher_name=user.username, notifications=notifications, user=user, sort_by=sort_by, search_query=search_query, has_gbs=has_gbs, has_qa=has_qa, has_lcca=has_lcca)

@app.route('/panel/student/add', methods=['POST'])
@login_required
def panel_add_student():
    user = User.query.get(session['user_id'])
    name = request.form.get('name')
    university_id = request.form.get('university_id')
    email = request.form.get('email')
    
    if not university_id and len(user.universities) == 1: university_id = user.universities[0].id
    if not name or not university_id: return redirect(url_for('panel_dashboard'))
        
    uni = University.query.get(int(university_id))
    new_student = Student(name=name, email=email, url_slug=f"{uuid.uuid4().hex[:4]}-{slugify(name)}", university_id=uni.id, creator_id=user.id)
    new_student.has_math_test = 'has_math_test' in request.form
    
    if "GBS" in uni.name:
        new_student.gbs_major_id = int(request.form.get('major_id')) if request.form.get('major_id') else None
        new_student.gbs_intake_id = int(request.form.get('intake_id')) if request.form.get('intake_id') else None
        db.session.add(new_student)
    elif "LCCA" in uni.name:
        db.session.add(new_student)
    else: 
        db.session.add(new_student)
        topics = QaTopic.query.order_by(QaTopic.order_index).all()
        for t in topics:
            db.session.add(Essay(title=t.title, topic_full=t.topic_full, is_exam=False, student=new_student))
        db.session.add(Essay(title="Egzamin", topic_full="[EGZAMIN] Tematy będą dostępne po wejściu.", is_exam=True, student=new_student))
        db.session.add(Essay(title="Egzamin Dodatkowy", topic_full="Wpisz temat nr 1...|||Wpisz temat nr 2...", is_exam=True, student=new_student))
    
    db.session.commit()
    
    # WYSYŁKA MAILA (Synchroniczna z obsługą błędów)
    if email:
        email_sent, msg = trigger_welcome_email(user, new_student, request.host)
        if email_sent:
            flash(f"Student {name} dodany pomyślnie. Mail został poprawnie wysłany na adres: {email}", "success")
        else:
            flash(f"Student dodany, ALE WYSYŁKA MAILA ZAWIODŁA! Powód: {msg}", "error")
    else:
        if "LCCA" in uni.name:
            flash(f"Student {name} dodany, ale nie podałeś e-maila (a LCCA go wymaga).", "warning")
        else:
            flash(f"Student {name} dodany pomyślnie!", "success")
        
    return redirect(url_for('panel_dashboard'))

# ----------------- SUPER-PANEL: BAZA WIEDZY I PYTAŃ -----------------

@app.route('/panel/database', methods=['GET', 'POST'])
@login_required
def panel_database():
    user = User.query.get(session['user_id'])
    universities = University.query.all() if user.role == 'admin' else user.universities
    has_gbs = any("GBS" in u.name for u in universities)
    has_qa = any("QA" in u.name for u in universities)
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_material':
            title = request.form.get('title')
            uni_id = request.form.get('university_id')
            category = request.form.get('category', 'interview')
            link_url = request.form.get('link_url')
            file = request.files.get('pdf_file')
            if not uni_id and len(universities) == 1: uni_id = universities[0].id
            
            content_url = ""
            if file and file.filename != '':
                ext = file.filename.split('.')[-1].lower()
                if ext in ['pdf', 'html', 'mp4', 'mov', 'avi']:
                    unique_filename = f"{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                    content_url = url_for('download_file', name=unique_filename)
                else:
                    flash("Niedozwolony format pliku. Użyj PDF, HTML lub Video.", "error")
                    return redirect(url_for('panel_database'))
            elif link_url: content_url = link_url
            
            if title and content_url and uni_id:
                db.session.add(Material(title=title, content_url=content_url, category=category, university_id=int(uni_id)))
                db.session.commit()
                flash("Materiał dodany!", "success")
                
        elif action == 'del_material':
            m = Material.query.get(request.form.get('material_id'))
            if m: db.session.delete(m); db.session.commit(); flash("Materiał usunięty.", "success")
            
        elif action == 'add_qa_topic':
            order_val = request.form.get('order_index', 0)
            db.session.add(QaTopic(title=request.form.get('title'), topic_full=request.form.get('topic_full'), order_index=int(order_val)))
            db.session.commit()
            flash("Temat rozprawki zapisany.", "success")
            
        elif action == 'edit_qa_order':
            t = QaTopic.query.get(request.form.get('topic_id'))
            if t: 
                t.order_index = int(request.form.get('order_index', 0))
                db.session.commit()
                flash("Kolejność zaktualizowana.", "success")
            
        elif action == 'del_qa_topic':
            t = QaTopic.query.get(request.form.get('topic_id'))
            if t: db.session.delete(t); db.session.commit(); flash("Temat usunięty.", "success")
            
        elif action == 'add_math_q':
            uni_id = request.form.get('university_id')
            if not uni_id and len(universities) == 1: uni_id = universities[0].id
            db.session.add(MathQuestion(text=request.form.get('text'), opt_a=request.form.get('opt_a'), opt_b=request.form.get('opt_b'), opt_c=request.form.get('opt_c'), opt_d=request.form.get('opt_d'), answer=request.form.get('answer'), university_id=int(uni_id)))
            db.session.commit()
            flash("Pytanie matematyczne dodane.", "success")
            
        elif action == 'del_math_q':
            mq = MathQuestion.query.get(request.form.get('question_id'))
            if mq: db.session.delete(mq); db.session.commit(); flash("Pytanie z matematyki usunięte.", "success")

        elif action == 'save_uni_template':
            uni = University.query.get(request.form.get('university_id'))
            if uni:
                uni.email_template = request.form.get('email_template')
                db.session.commit()
                flash(f"Szablon email dla uczelni {uni.name} zapisany pomyślnie!", "success")

        return redirect(url_for('panel_database'))

    qa_topics = QaTopic.query.order_by(QaTopic.order_index).all()
    math_questions = MathQuestion.query.all()
    return render_template('panel_database.html', universities=universities, qa_topics=qa_topics, math_questions=math_questions, user=user, has_gbs=has_gbs, has_qa=has_qa)

@app.route('/uploads/<name>')
def download_file(name):
    return send_from_directory(app.config['UPLOAD_FOLDER'], name, as_attachment=False)

# ----------------- PANEL GBS (KONFIGURACJA NABORÓW I PYTAŃ) -----------------
@app.route('/panel/gbs', methods=['GET', 'POST'])
@login_required
def panel_gbs():
    user = User.query.get(session['user_id'])
    universities = University.query.all() if user.role == 'admin' else user.universities
    has_gbs = any("GBS" in u.name for u in universities)
    has_qa = any("QA" in u.name for u in universities)
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_intake':
            db.session.add(GbsIntake(name=request.form.get('name'), color=request.form.get('color')))
            db.session.commit()
        elif action == 'edit_intake':
            i = GbsIntake.query.get(request.form.get('intake_id'))
            if i: i.name = request.form.get('name'); i.color = request.form.get('color'); db.session.commit()
        elif action == 'delete_intake':
            i = GbsIntake.query.get(request.form.get('intake_id'))
            if i: db.session.delete(i); db.session.commit()
        return redirect(url_for('panel_gbs'))
    return render_template('gbs/panel_gbs.html', intakes=GbsIntake.query.all(), has_qa=has_qa, has_gbs=has_gbs)

@app.route('/panel/gbs/intake/<int:intake_id>', methods=['GET', 'POST'])
@login_required
def panel_gbs_intake(intake_id):
    intake = GbsIntake.query.get_or_404(intake_id)
    if request.method == 'POST':
        major_id = request.form.get('major_id')
        qset = GbsQuestionSet.query.filter_by(intake_id=intake.id, major_id=major_id).first()
        if not qset:
            qset = GbsQuestionSet(intake_id=intake.id, major_id=major_id)
            db.session.add(qset)
        qset.q1 = request.form.get('q1', ''); qset.q2 = request.form.get('q2', ''); qset.q3 = request.form.get('q3', '')
        db.session.commit()
        flash("Pytania zapisane!", "success")
        return redirect(url_for('panel_gbs_intake', intake_id=intake.id))
    return render_template('gbs/panel_gbs_intake.html', intake=intake, majors=GbsMajor.query.all(), question_sets={qs.major_id: qs for qs in intake.question_sets})

# ----------------- WIDOKI I AKCJE STUDENTA -----------------

@app.route('/student/<url_slug>')
def student_dashboard(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    archived_view = check_archived(student)
    if archived_view: return archived_view
    
    materials = student.university.materials if student.university else []
    
    if student.university and "LCCA" in student.university.name:
        return render_template('lcca/student.html', student=student)
    elif student.university and "GBS" in student.university.name:
        return render_template('gbs/student_gbs_dashboard.html', student=student, materials=materials)
    
    essay_materials = [m for m in materials if m.category == 'essay']
    interview_materials = [m for m in materials if m.category == 'interview']
    return render_template('qa/student.html', student=student, essay_materials=essay_materials, interview_materials=interview_materials)

@app.route('/qa/essays/<url_slug>')
def qa_essays(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    archived_view = check_archived(student)
    if archived_view: return archived_view
    return render_template('qa/student_essays.html', student=student)

@app.route('/qa/grades/<url_slug>')
def qa_grades(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    archived_view = check_archived(student)
    if archived_view: return archived_view
    return render_template('qa/student_grades.html', student=student)

@app.route('/gbs/task/<url_slug>')
def gbs_task(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    archived_view = check_archived(student)
    if archived_view: return archived_view
    qset = GbsQuestionSet.query.filter_by(intake_id=student.gbs_intake_id, major_id=student.gbs_major_id).first()
    questions = [qset.q1, qset.q2, qset.q3] if qset else ["Pytanie 1 (Brak)", "Pytanie 2 (Brak)", "Pytanie 3 (Brak)"]
    return render_template('gbs/gbs_task.html', student=student, questions=questions, is_exam=(request.args.get('exam') == 'true'))

@app.route('/api/gbs/submit/<int:student_id>', methods=['POST'])
def gbs_submit(student_id):
    student = Student.query.get_or_404(student_id)
    data = request.get_json()
    attempt = GbsAttempt(student_id=student.id, q1_ans=data.get('q1', ''), q2_ans=data.get('q2', ''), q3_ans=data.get('q3', ''), is_exam=data.get('is_exam', False))
    db.session.add(attempt)
    db.session.add(Notification(message=f"<a href='/admin/student/{student.id}' class='notif-link'><b>{student.name}</b> oddał/a zadanie GBS.</a>", recipient_id=student.creator_id, student_id=student.id))
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/math/<url_slug>')
def math_test(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    archived_view = check_archived(student)
    if archived_view: return archived_view
    if not student.has_math_test: return "Brak dostępu do testu z matematyki", 403
    
    questions = MathQuestion.query.filter_by(university_id=student.university_id).all()
    return render_template('gbs/math_test.html', student=student, questions=questions)

@app.route('/api/math/submit/<int:student_id>', methods=['POST'])
def math_submit(student_id):
    student = Student.query.get_or_404(student_id)
    data = request.get_json() 
    questions = MathQuestion.query.filter_by(university_id=student.university_id).all()
    score = sum(1 for q in questions if data.get(str(q.id)) == q.answer)
    db.session.add(MathTestResult(student_id=student.id, score=score, total=len(questions), answers_json=json.dumps(data)))
    db.session.add(Notification(message=f"<a href='/admin/student/{student.id}' class='notif-link'><b>{student.name}</b> ukończył/a test z matmy ({score}/{len(questions)}).</a>", recipient_id=student.creator_id, student_id=student.id))
    db.session.commit()
    return jsonify({"status": "success", "score": score})

# ----------------- PANEL MASTER -----------------
@app.route('/panel/master', methods=['GET', 'POST'])
@admin_required
def panel_master():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_teacher':
            if not User.query.filter_by(username=request.form.get('username')).first():
                new_t = User(
                    username=request.form.get('username'), 
                    password_hash=generate_password_hash(request.form.get('password')), 
                    role='teacher',
                    smtp_email=request.form.get('smtp_email'),
                    smtp_password=request.form.get('smtp_password'),
                    email_template=request.form.get('email_template')
                )
                for uid in request.form.getlist('universities'): new_t.universities.append(University.query.get(int(uid)))
                db.session.add(new_t); db.session.commit()
                flash("Nauczyciel z przypisaną pocztą dodany!", "success")
        elif action == 'delete_teacher':
            t = User.query.get(request.form.get('teacher_id'))
            if t: db.session.delete(t); db.session.commit()
        elif action == 'delete_file':
            m = Material.query.get(request.form.get('material_id'))
            if m: 
                filename = m.content_url.split('/')[-1]
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(filepath): os.remove(filepath)
                db.session.delete(m)
                db.session.commit()
                flash("Plik całkowicie usunięty z serwera.", "success")
        return redirect(url_for('panel_master'))
    
    size_bytes = get_dir_size(app.config['UPLOAD_FOLDER'])
    folder_size_mb = round(size_bytes / (1024 * 1024), 2)
    folder_size_gb = round(size_bytes / (1024 * 1024 * 1024), 4)
    all_materials = Material.query.filter(Material.content_url.contains('/uploads/')).all()

    return render_template('panel_master.html', teachers=User.query.filter_by(role='teacher').all(), all_unis=University.query.all(), folder_size_mb=folder_size_mb, folder_size_gb=folder_size_gb, all_materials=all_materials, stats={})

# ----------------- FUNKCJE ROZPRAWEK (QA) -----------------
@app.route('/admin')
@login_required
def admin(): return redirect(url_for('panel_dashboard'))

@app.route('/admin/archive')
@login_required
def admin_archive():
    user = User.query.get(session['user_id'])
    query = Student.query.filter_by(is_archived=True)
    if user.role != 'admin': query = query.filter(Student.university_id.in_([u.id for u in user.universities]))
    return render_template('qa/admin_archive.html', archived_students=query.order_by(Student.name.asc()).all())

@app.route('/admin/student/<int:student_id>/restore', methods=['POST'])
@login_required
def restore_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_archived = False; db.session.commit()
    return redirect(url_for('admin_archive'))

@app.route('/admin/student/<int:student_id>/delete_forever', methods=['POST'])
@admin_required
def delete_student_forever(student_id):
    student = Student.query.get_or_404(student_id)
    Essay.query.filter_by(student_id=student.id).delete()
    db.session.delete(student); db.session.commit()
    return redirect(url_for('admin_archive'))

@app.route('/admin/student/<int:student_id>')
@login_required
def admin_student_detail(student_id):
    student = Student.query.get_or_404(student_id)
    essays_sorted = sorted(student.essays, key=lambda x: x.last_edited_at or datetime.min, reverse=True)
    gbs_attempts = sorted(student.gbs_attempts, key=lambda x: x.submitted_at, reverse=True)
    math_results = sorted(student.math_results, key=lambda x: x.submitted_at, reverse=True)
    return render_template('qa/student_detail.html', student=student, essays_sorted=essays_sorted, gbs_attempts=gbs_attempts, math_results=math_results)

@app.route('/admin/student/<int:student_id>/archive', methods=['POST'])
@login_required
def toggle_archive(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_archived = True; db.session.commit()
    return redirect(url_for('panel_dashboard'))

@app.route('/admin/student/<int:student_id>/extra_exam', methods=['POST'])
@login_required
def update_extra_exam(student_id):
    student = Student.query.get_or_404(student_id)
    extra_exam = Essay.query.filter_by(student_id=student.id, title="Egzamin Dodatkowy").first()
    if not extra_exam:
        extra_exam = Essay(title="Egzamin Dodatkowy", is_exam=True, student_id=student.id)
        db.session.add(extra_exam)
    extra_exam.topic_full = f"{request.form.get('topic1', '')}|||{request.form.get('topic2', '')}"
    db.session.commit()
    return redirect(url_for('admin_student_detail', student_id=student.id))

@app.route('/admin/essay/<int:essay_id>/return', methods=['POST'])
@login_required
def return_essay(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    essay.is_completed = False
    Notification.query.filter(Notification.message.contains(essay.student.name)).delete()
    db.session.commit()
    return redirect(url_for('admin_student_detail', student_id=essay.student_id))

@app.route('/admin/essay/<int:essay_id>/feedback', methods=['POST'])
@login_required
def save_feedback(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    essay.feedback = request.form.get('feedback')
    essay.marked_content = request.form.get('marked_content')
    Notification.query.filter(Notification.message.contains(essay.student.name)).delete()
    db.session.commit()
    return redirect(url_for('admin_student_detail', student_id=essay.student_id))

@app.route('/api/admin/essay/<int:essay_id>/content')
@login_required
def admin_get_live_content(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    return jsonify({"content": essay.content, "time_spent": essay.time_spent})

@app.route('/admin/notif/delete/<int:notif_id>', methods=['POST'])
@login_required
def delete_notif(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    db.session.delete(notif); db.session.commit()
    return redirect(url_for('panel_dashboard'))

@app.route('/exam/<url_slug>')
def exam_direct_link(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    archived_view = check_archived(student)
    if archived_view: return archived_view
    exam_essay = Essay.query.filter_by(student_id=student.id, title="Egzamin").first_or_404()
    topics = ["Some people think it is beneficial for old people to learn something new...", "Some people think that introducing children to team sports..."]
    return render_template('qa/write.html', essay=exam_essay, exam_topics=topics)

@app.route('/exam_extra/<url_slug>')
def exam_extra_direct_link(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    archived_view = check_archived(student)
    if archived_view: return archived_view
    exam_essay = Essay.query.filter_by(student_id=student.id, title="Egzamin Dodatkowy").first()
    topics = exam_essay.topic_full.split('|||') if exam_essay and exam_essay.topic_full else ["Brak tematu 1", "Brak tematu 2"]
    return render_template('qa/write.html', essay=exam_essay, exam_topics=topics)

@app.route('/write/<int:essay_id>')
def write_essay(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    student = Student.query.get(essay.student_id)
    archived_view = check_archived(student)
    if archived_view: return archived_view
    topics = essay.topic_full.split('|||') if essay.title == "Egzamin Dodatkowy" and essay.topic_full else []
    return render_template('qa/write.html', essay=essay, exam_topics=topics)

@app.route('/api/save/<int:essay_id>', methods=['POST'])
def auto_save(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    data = request.get_json()
    essay.content = data.get('content', essay.content)
    essay.time_spent = data.get('time_spent', essay.time_spent)
    if 'chosen_topic' in data: essay.chosen_topic = data['chosen_topic']
    became_completed = False
    if data.get('is_completed') and not essay.is_completed:
        essay.is_completed = True
        became_completed = True
    essay.last_edited_at = datetime.now()
    if not essay.started_at: essay.started_at = datetime.now()
    db.session.commit()
    if became_completed:
        db.session.add(Notification(message=f"<a href='/admin/student/{essay.student_id}' class='notif-link'><b>{essay.student.name}</b> ukończył/a: '{essay.title[:30]}'</a>", recipient_id=essay.student.creator_id, student_id=essay.student_id))
        db.session.commit()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)

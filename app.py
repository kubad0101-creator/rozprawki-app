import os
import re
import unicodedata
import uuid
import json
import requests
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = "Open196!_System_Rozprawek_2024"

# --- AUTOMATYCZNE PRZEKIEROWANIE NA WWW (Naprawia problem z logowaniem do Panelu Master) ---
@app.before_request
def enforce_www():
    host = request.host.lower()
    if host == "openukstudylearn.pl":
        return redirect(f"https://www.openukstudylearn.pl{request.full_path}", code=301)
# ------------------------------------------------------------------------------------------

# --- KONFIGURACJA BREVO API ---
BREVO_API_KEY = "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" 
BREVO_SENDER_DOMAIN = "openukstudylearn.pl" # Nowa zweryfikowana domena
DEFAULT_REPLY_TO = "kuba@openukstudy.com" # Awaryjny e-mail do odpowiedzi
# ------------------------------

UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

database_url = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ----------------- MODELE BAZY DANYCH -----------------

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
    email_template = db.Column(db.Text, nullable=True) 
    universities = db.relationship('University', secondary=teacher_university, backref='teachers')

class University(db.Model):
    __tablename__ = 'universities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email_template = db.Column(db.Text, nullable=True)
    materials = db.relationship('Material', backref='university', lazy=True, cascade="all, delete-orphan")
    students = db.relationship('Student', backref='university', lazy=True)

class QaMajor(db.Model):
    __tablename__ = 'qa_majors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)

class GbsMajor(db.Model):
    __tablename__ = 'gbs_majors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    is_cccu = db.Column(db.Boolean, default=False)

class Material(db.Model):
    __tablename__ = 'materials'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content_url = db.Column(db.String(500), nullable=False) 
    category = db.Column(db.String(50), default='interview') 
    university_id = db.Column(db.Integer, db.ForeignKey('universities.id', ondelete='CASCADE'), nullable=False)
    qa_major_id = db.Column(db.Integer, db.ForeignKey('qa_majors.id', ondelete='CASCADE'), nullable=True)
    gbs_major_id = db.Column(db.Integer, db.ForeignKey('gbs_majors.id', ondelete='CASCADE'), nullable=True)
    
    qa_major = db.relationship('QaMajor')
    gbs_major = db.relationship('GbsMajor')

class QaTopic(db.Model):
    __tablename__ = 'qa_topics'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    topic_full = db.Column(db.Text, nullable=False)
    order_index = db.Column(db.Integer, default=0)

class ExamTopic(db.Model):
    __tablename__ = 'exam_topics'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    topic_full = db.Column(db.Text, nullable=False)

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
    
    qa_major_id = db.Column(db.Integer, db.ForeignKey('qa_majors.id'), nullable=True)
    gbs_major_id = db.Column(db.Integer, db.ForeignKey('gbs_majors.id'), nullable=True)
    gbs_intake_id = db.Column(db.Integer, db.ForeignKey('gbs_intakes.id'), nullable=True)
    has_math_test = db.Column(db.Boolean, default=False)
    
    essays = db.relationship('Essay', backref='student', lazy=True, cascade="all, delete-orphan")
    gbs_attempts = db.relationship('GbsAttempt', backref='student', lazy=True, cascade="all, delete-orphan")
    math_results = db.relationship('MathTestResult', backref='student', lazy=True, cascade="all, delete-orphan")
    
    qa_major = db.relationship('QaMajor')
    gbs_major = db.relationship('GbsMajor')
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


# ---------------- FUNKCJE POCZTOWE (BREVO REST API - HTML) ----------------

POLISH_DAYS = {
    0: "Poniedziałek", 1: "Wtorek", 2: "Środa",
    3: "Czwartek", 4: "Piątek", 5: "Sobota", 6: "Niedziela"
}

def format_pl_date(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str.replace("T", " "), "%Y-%m-%d %H:%M")
        day_name = POLISH_DAYS[dt.weekday()]
        return f"{day_name}, {dt.day}.{dt.month:02d} o godzinie {dt.strftime('%H:%M')}"
    except ValueError:
        return date_str

def send_email_api(sender_email, sender_name, recipient_email, subject, body, reply_to_email=None):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient_email}],
        "subject": subject,
        "htmlContent": body
    }
    
    if reply_to_email:
        payload["replyTo"] = {"email": reply_to_email, "name": sender_name}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 201, 202):
            return True, "Wysłano pomyślnie przez API."
        else:
            err_details = response.json().get('message', response.text)
            return False, f"Odmowa API Brevo: {err_details}"
    except Exception as e:
        return False, f"Błąd połączenia z siecią: {str(e)}"

def trigger_welcome_email(teacher, student, request_host, termin1_raw, termin2_raw):
    if not student.email:
        return False, "Nie podano adresu e-mail studenta."
        
    safe_teacher_name = slugify(teacher.username)
    sender_email = f"{safe_teacher_name}@{BREVO_SENDER_DOMAIN}"
    
    # Naprawa powielania "Open UK Study" w nazwie nadawcy
    if "Open UK Study" in teacher.username:
        sender_name = teacher.username
    else:
        sender_name = f"{teacher.username} Open UK Study"
    
    reply_to_email = teacher.smtp_email if teacher.smtp_email else DEFAULT_REPLY_TO
    
    template = teacher.email_template
    if not template:
        template = student.university.email_template if student.university and student.university.email_template else None
    if not template:
        template = "<p>Witaj {imie}!</p><p>Oto Twój link do panelu:<br><a href='{link}'>{link}</a></p><p>Proponowany termin spotkania: {terminy}</p><p>Pozdrawiamy!</p>"
        
    link = f"https://{request_host}/student/{student.url_slug}"
    
    t1_fmt = format_pl_date(termin1_raw)
    t2_fmt = format_pl_date(termin2_raw)
    
    if t1_fmt and t2_fmt: terminy_str = f"{t1_fmt} lub {t2_fmt}"
    elif t1_fmt: terminy_str = t1_fmt
    elif t2_fmt: terminy_str = t2_fmt
    else: terminy_str = "Zostanie ustalony wkrótce."

    body = template
    replacements = {
        "{imie}": student.name,
        "{link}": link,
        "{terminy}": terminy_str
    }
    
    for tag, value in replacements.items():
        body = body.replace(tag, value)
    
    body = body.replace("{termin1}", t1_fmt)
    body = body.replace("{termin2}", "")
    
    footer = f"""
    <br><br>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top: 30px; border-top: 2px solid #f0f0f0; padding-top: 15px;">
        <tr>
            <td style="font-family: Arial, sans-serif; font-size: 13px; color: #555555; line-height: 1.6;">
                <strong style="font-size: 16px; color: #2c3e50;">{teacher.username}</strong><br>
                Ekspert ds. Rekrutacji | <strong style="color: #007bff;">Open UK Study</strong><br>
                ✉️ <a href="mailto:{teacher.smtp_email or BREVO_SENDER_EMAIL}" style="color: #007bff; text-decoration: none;">{teacher.smtp_email or BREVO_SENDER_EMAIL}</a><br>
                🌐 <a href="https://openukstudy.com" style="color: #007bff; text-decoration: none;">www.openukstudy.com</a>
            </td>
        </tr>
    </table>
    """
    body += footer
    
    subject = "Twój dostęp do platformy edukacyjnej Open UK Study"
    success, msg = send_email_api(sender_email, sender_name, student.email, subject, body, reply_to_email)
    return success, msg
# ---------------------------------------------------------------


# --- INITIAL DATA ---
def setup_database():
    db.create_all()
    queries = [
        'CREATE TABLE IF NOT EXISTS qa_majors (id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL)',
        'CREATE TABLE IF NOT EXISTS exam_topics (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, topic_full TEXT NOT NULL)',
        'ALTER TABLE student_v5 ADD COLUMN qa_major_id INTEGER REFERENCES qa_majors(id)',
        'ALTER TABLE materials ADD COLUMN qa_major_id INTEGER REFERENCES qa_majors(id)',
        'ALTER TABLE materials ADD COLUMN gbs_major_id INTEGER REFERENCES gbs_majors(id)'
    ]
    for q in queries:
        try: db.session.execute(text(q)); db.session.commit()
        except Exception: db.session.rollback()

    qa_uni = University.query.filter_by(name="QA Higher Education").first() or University(name="QA Higher Education")
    gbs_uni = University.query.filter_by(name="GBS").first() or University(name="GBS")
    lcca_uni = University.query.filter_by(name="LCCA").first() or University(name="LCCA")
    db.session.add_all([qa_uni, gbs_uni, lcca_uni])
    
    if not ExamTopic.query.first():
        db.session.add(ExamTopic(title="Egzamin 1", topic_full="Some people think it is beneficial for old people to learn something new..."))
    
    db.session.commit()
            
    if not User.query.filter_by(username="Admin Open UK Study").first(): 
        db.session.add(User(username="Admin Open UK Study", password_hash=generate_password_hash("Open196!"), role="admin"))
    
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

@app.route('/panel', methods=['GET', 'POST'])
@login_required
def panel_dashboard():
    user = User.query.get(session['user_id'])
    
    universities = University.query.all() if user.role == 'admin' else user.universities
    uni_ids = [u.id for u in universities]
    
    has_gbs = any("GBS" in u.name for u in universities)
    has_qa = any("QA" in u.name for u in universities)
    has_lcca = any("LCCA" in u.name for u in universities)
    
    gbs_majors = GbsMajor.query.all()
    qa_majors = QaMajor.query.all()
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
    
    return render_template('panel_dashboard.html', qa_students=qa_students, gbs_students=gbs_students, lcca_students=lcca_students, universities=universities, gbs_majors=gbs_majors, qa_majors=qa_majors, intakes=intakes, teacher_name=user.username, notifications=notifications, user=user, sort_by=sort_by, search_query=search_query, has_gbs=has_gbs, has_qa=has_qa, has_lcca=has_lcca)

@app.route('/panel/student/add', methods=['POST'])
@login_required
def panel_add_student():
    user = User.query.get(session['user_id'])
    name = request.form.get('name')
    university_id = request.form.get('university_id')
    email = request.form.get('email')
    
    raw_t1 = request.form.get('termin1', '')
    raw_t2 = request.form.get('termin2', '')
    
    if not university_id and len(user.universities) == 1: university_id = user.universities[0].id
    if not name or not university_id: return redirect(url_for('panel_dashboard'))
        
    uni = University.query.get(int(university_id))
    new_student = Student(name=name, email=email, url_slug=f"{uuid.uuid4().hex[:4]}-{slugify(name)}", university_id=uni.id, creator_id=user.id)
    new_student.has_math_test = 'has_math_test' in request.form
    
    if "GBS" in uni.name:
        new_student.gbs_major_id = int(request.form.get('gbs_major_id')) if request.form.get('gbs_major_id') else None
        new_student.gbs_intake_id = int(request.form.get('intake_id')) if request.form.get('intake_id') else None
        db.session.add(new_student)
    elif "QA" in uni.name:
        new_student.qa_major_id = int(request.form.get('qa_major_id')) if request.form.get('qa_major_id') else None
        db.session.add(new_student)
        topics = QaTopic.query.order_by(QaTopic.order_index).all()
        for t in topics:
            db.session.add(Essay(title=t.title, topic_full=t.topic_full, is_exam=False, student=new_student))
        db.session.add(Essay(title="Egzamin", topic_full="[EGZAMIN] Tematy będą dostępne po wejściu.", is_exam=True, student=new_student))
        db.session.add(Essay(title="Egzamin Dodatkowy", topic_full="Wpisz temat nr 1...|||Wpisz temat nr 2...", is_exam=True, student=new_student))
    else: 
        db.session.add(new_student)
    
    db.session.commit()
    
    if email:
        email_sent, msg = trigger_welcome_email(user, new_student, request.host, raw_t1, raw_t2)
        if email_sent:
            flash(f"Student {name} dodany pomyślnie. E-mail w drodze.", "success")
        else:
            flash(f"Student dodany, ALE WYSYŁKA MAILA ZAWIODŁA! Powód: {msg}", "error")
    else:
        flash(f"Student {name} dodany pomyślnie! (Brak maila).", "success")
        
    return redirect(url_for('panel_dashboard'))

# ----------------- SUPER-PANEL: BAZA WIEDZY I PYTAŃ -----------------

@app.route('/panel/database', methods=['GET', 'POST'])
@login_required
def panel_database():
    user = User.query.get(session['user_id'])
    universities = University.query.all() if user.role == 'admin' else user.universities
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_teacher_template':
            user.email_template = request.form.get('email_template')
            db.session.commit()
            flash("Twój szablon e-mail został zapisany!", "success")
            return redirect(url_for('panel_database'))
            
        elif action == 'add_material':
            title = request.form.get('title')
            uni_id = request.form.get('university_id')
            category = request.form.get('category', 'interview') 
            gbs_major_id = request.form.get('gbs_major_id')
            qa_major_id = request.form.get('qa_major_id')
            link_url = request.form.get('link_url')
            file = request.files.get('pdf_file')
            if not uni_id and len(universities) == 1: uni_id = universities[0].id
            
            content_url = ""
            if file and file.filename != '':
                ext = file.filename.split('.')[-1].lower()
                if ext in ['pdf', 'html', 'mp4', 'mov', 'avi', 'jpg', 'jpeg', 'png']:
                    unique_filename = f"{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                    content_url = url_for('download_file', name=unique_filename)
                else:
                    flash("Niedozwolony format pliku.", "error")
                    return redirect(url_for('panel_database'))
            elif link_url: content_url = link_url
            
            if title and content_url and uni_id:
                m = Material(title=title, content_url=content_url, category=category, university_id=int(uni_id))
                if gbs_major_id: m.gbs_major_id = int(gbs_major_id)
                if qa_major_id: m.qa_major_id = int(qa_major_id)
                db.session.add(m)
                db.session.commit()
                flash("Materiał dodany!", "success")
                
        elif action == 'del_material':
            m = Material.query.get(request.form.get('material_id'))
            if m: db.session.delete(m); db.session.commit(); flash("Materiał usunięty.", "success")
            
        elif action == 'add_qa_major':
            db.session.add(QaMajor(name=request.form.get('name')))
            db.session.commit(); flash("Kierunek QA dodany.", "success")
        elif action == 'del_qa_major':
            qm = QaMajor.query.get(request.form.get('major_id'))
            if qm: db.session.delete(qm); db.session.commit(); flash("Kierunek QA usunięty.", "success")
            
        elif action == 'add_gbs_major':
            db.session.add(GbsMajor(name=request.form.get('name')))
            db.session.commit(); flash("Kierunek GBS dodany.", "success")
        elif action == 'del_gbs_major':
            gm = GbsMajor.query.get(request.form.get('major_id'))
            if gm: db.session.delete(gm); db.session.commit(); flash("Kierunek GBS usunięty.", "success")
            
        elif action == 'add_qa_topic':
            order_val = request.form.get('order_index', 0)
            db.session.add(QaTopic(title=request.form.get('title'), topic_full=request.form.get('topic_full'), order_index=int(order_val)))
            db.session.commit(); flash("Temat rozprawki zapisany.", "success")
            
        elif action == 'edit_qa_topic':
            t = QaTopic.query.get(request.form.get('topic_id'))
            if t: 
                t.title = request.form.get('title')
                t.topic_full = request.form.get('topic_full')
                db.session.commit(); flash("Temat zaktualizowany.", "success")
                
        elif action == 'del_qa_topic':
            t = QaTopic.query.get(request.form.get('topic_id'))
            if t: db.session.delete(t); db.session.commit(); flash("Temat usunięty.", "success")

        elif action == 'add_exam_topic':
            db.session.add(ExamTopic(title=request.form.get('title'), topic_full=request.form.get('topic_full')))
            db.session.commit(); flash("Temat egzaminu zapisany.", "success")
        elif action == 'del_exam_topic':
            t = ExamTopic.query.get(request.form.get('topic_id'))
            if t: db.session.delete(t); db.session.commit(); flash("Temat usunięty.", "success")
            
        elif action == 'add_math_q':
            uni_id = request.form.get('university_id')
            if not uni_id and len(universities) == 1: uni_id = universities[0].id
            db.session.add(MathQuestion(text=request.form.get('text'), opt_a=request.form.get('opt_a'), opt_b=request.form.get('opt_b'), opt_c=request.form.get('opt_c'), opt_d=request.form.get('opt_d'), answer=request.form.get('answer'), university_id=int(uni_id)))
            db.session.commit(); flash("Pytanie matematyczne dodane.", "success")
            
        elif action == 'del_math_q':
            mq = MathQuestion.query.get(request.form.get('question_id'))
            if mq: db.session.delete(mq); db.session.commit(); flash("Pytanie z matematyki usunięte.", "success")

        return redirect(url_for('panel_database'))

    qa_topics = QaTopic.query.order_by(QaTopic.order_index).all()
    exam_topics = ExamTopic.query.all()
    math_questions = MathQuestion.query.all()
    gbs_majors = GbsMajor.query.all()
    qa_majors = QaMajor.query.all()
    
    archived_students = Student.query.filter_by(is_archived=True).filter(Student.university_id.in_([u.id for u in universities])).order_by(Student.name.asc()).all()
    
    return render_template('panel_database.html', universities=universities, qa_topics=qa_topics, exam_topics=exam_topics, math_questions=math_questions, gbs_majors=gbs_majors, qa_majors=qa_majors, archived_students=archived_students, user=user)

@app.route('/api/reorder_qa', methods=['POST'])
@login_required
def reorder_qa():
    data = request.get_json()
    for index, topic_id in enumerate(data.get('order', [])):
        t = QaTopic.query.get(topic_id)
        if t: t.order_index = index
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/uploads/<name>')
def download_file(name):
    return send_from_directory(app.config['UPLOAD_FOLDER'], name, as_attachment=False)


# ----------------- WIDOKI I AKCJE STUDENTA -----------------

@app.route('/student/<url_slug>')
def student_dashboard(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    archived_view = check_archived(student)
    if archived_view: return archived_view
    
    all_uni_materials = student.university.materials if student.university else []
    materials = []
    for m in all_uni_materials:
        if m.qa_major_id is None and m.gbs_major_id is None:
            materials.append(m)
        elif m.qa_major_id and student.qa_major_id and m.qa_major_id == student.qa_major_id:
            materials.append(m)
        elif m.gbs_major_id and student.gbs_major_id and m.gbs_major_id == student.gbs_major_id:
            materials.append(m)
            
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
    if check_archived(student): return check_archived(student)
    return render_template('qa/student_essays.html', student=student)

@app.route('/qa/grades/<url_slug>')
def qa_grades(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    if check_archived(student): return check_archived(student)
    return render_template('qa/student_grades.html', student=student)

@app.route('/gbs/task/<url_slug>')
def gbs_task(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    if check_archived(student): return check_archived(student)
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
    if check_archived(student): return check_archived(student)
    if not student.has_math_test: return "Brak dostępu do testu z matematyki", 403
    
    all_uni_materials = student.university.materials if student.university else []
    study_materials = [m for m in all_uni_materials if m.category == 'math_test']
    questions = MathQuestion.query.filter_by(university_id=student.university_id).all()
    
    return render_template('gbs/math_test.html', student=student, questions=questions, study_materials=study_materials)

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


# ----------------- PANEL MASTER Z ZAAWANSOWANYMI STATYSTYKAMI -----------------

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
                    smtp_email=request.form.get('smtp_email')
                )
                for uid in request.form.getlist('universities'): 
                    new_t.universities.append(University.query.get(int(uid)))
                db.session.add(new_t)
                db.session.commit()
                flash("Nauczyciel pomyślnie dodany do systemu!", "success")
                
        elif action == 'edit_teacher':
            t = User.query.get(request.form.get('teacher_id'))
            if t:
                t.username = request.form.get('username')
                t.smtp_email = request.form.get('smtp_email')
                new_pass = request.form.get('password')
                if new_pass:
                    t.password_hash = generate_password_hash(new_pass)
                t.universities = []
                for uid in request.form.getlist('universities'): 
                    t.universities.append(University.query.get(int(uid)))
                db.session.commit()
                flash("Konto nauczyciela zaktualizowane!", "success")
                
        elif action == 'delete_teacher':
            t = User.query.get(request.form.get('teacher_id'))
            if t: 
                try:
                    db.session.execute(text("DELETE FROM teacher_university WHERE teacher_id = :tid"), {'tid': t.id})
                    Student.query.filter_by(creator_id=t.id).update({'creator_id': None})
                    Notification.query.filter_by(recipient_id=t.id).delete()
                    
                    db.session.delete(t)
                    db.session.commit()
                    flash(f"Konto {t.username} zostało usunięte.", "success")
                except Exception as e:
                    db.session.rollback()
                    flash(f"Błąd podczas usuwania: {str(e)}", "error")
                    
        elif action == 'delete_file':
            m = Material.query.get(request.form.get('material_id'))
            if m: 
                filename = m.content_url.split('/')[-1]
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(filepath): os.remove(filepath)
                db.session.delete(m)
                db.session.commit()
                flash("Plik usunięty z serwera.", "success")
                
        return redirect(url_for('panel_master'))
    
    teachers = User.query.filter_by(role='teacher').all()
    teacher_stats = {}
    for t in teachers:
        t_students = Student.query.filter_by(creator_id=t.id).all()
        student_ids = [s.id for s in t_students]
        
        tot = len(t_students)
        act = sum(1 for s in t_students if not s.is_archived)
        arc = sum(1 for s in t_students if s.is_archived)
        
        if student_ids:
            tot_essays = Essay.query.filter(Essay.student_id.in_(student_ids), Essay.is_completed == True).count()
            to_check = Essay.query.filter(Essay.student_id.in_(student_ids), Essay.is_completed == True, Essay.feedback == None).count()
        else:
            tot_essays = 0
            to_check = 0
            
        teacher_stats[t.id] = {
            'total_students': tot,
            'active_students': act,
            'archived_students': arc,
            'total_essays': tot_essays,
            'essays_to_check': to_check
        }

    size_bytes = get_dir_size(app.config['UPLOAD_FOLDER'])
    folder_size_mb = round(size_bytes / (1024 * 1024), 2)
    folder_size_gb = round(size_bytes / (1024 * 1024 * 1024), 4)
    all_materials = Material.query.filter(Material.content_url.contains('/uploads/')).all()

    return render_template('panel_master.html', 
                           teachers=teachers, 
                           teacher_stats=teacher_stats,
                           all_unis=University.query.all(), 
                           qa_majors=QaMajor.query.all(),
                           gbs_majors=GbsMajor.query.all(),
                           folder_size_mb=folder_size_mb, 
                           folder_size_gb=folder_size_gb, 
                           all_materials=all_materials)


# ----------------- FUNKCJE ROZPRAWEK (QA) I ADMIN ROUTING -----------------

@app.route('/admin')
@login_required
def admin(): return redirect(url_for('panel_dashboard'))

@app.route('/admin/student/<int:student_id>/restore', methods=['POST'])
@login_required
def restore_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_archived = False; db.session.commit()
    return redirect(url_for('panel_database'))

@app.route('/admin/student/<int:student_id>/delete_forever', methods=['POST'])
@admin_required
def delete_student_forever(student_id):
    student = Student.query.get_or_404(student_id)
    Essay.query.filter_by(student_id=student.id).delete()
    db.session.delete(student); db.session.commit()
    return redirect(url_for('panel_database'))

@app.route('/admin/student/<int:student_id>')
@login_required
def admin_student_detail(student_id):
    student = Student.query.get_or_404(student_id)
    essays_sorted = sorted(student.essays, key=lambda x: x.last_edited_at or datetime.min, reverse=True)
    gbs_attempts = sorted(student.gbs_attempts, key=lambda x: x.submitted_at, reverse=True)
    math_results = sorted(student.math_results, key=lambda x: x.submitted_at, reverse=True)

    extra_exam = next((e for e in student.essays if e.title == "Egzamin Dodatkowy"), None)
    extra_topics = extra_exam.topic_full.split('|||') if extra_exam and extra_exam.topic_full else ["", ""]
    extra_topic1 = extra_topics[0] if len(extra_topics) > 0 else ""
    extra_topic2 = extra_topics[1] if len(extra_topics) > 1 else ""

    return render_template('qa/student_detail.html', student=student, essays_sorted=essays_sorted, gbs_attempts=gbs_attempts, math_results=math_results, extra_topic1=extra_topic1, extra_topic2=extra_topic2)

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
    if check_archived(student): return check_archived(student)
    exam_essay = Essay.query.filter_by(student_id=student.id, title="Egzamin").first_or_404()
    db_topics = ExamTopic.query.order_by(ExamTopic.id).all()
    topics = [t.topic_full for t in db_topics]
    return render_template('qa/write.html', essay=exam_essay, exam_topics=topics)

@app.route('/exam_extra/<url_slug>')
def exam_extra_direct_link(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    if check_archived(student): return check_archived(student)
    exam_essay = Essay.query.filter_by(student_id=student.id, title="Egzamin Dodatkowy").first()
    topics = exam_essay.topic_full.split('|||') if exam_essay and exam_essay.topic_full else ["Brak tematu 1", "Brak tematu 2"]
    return render_template('qa/write.html', essay=exam_essay, exam_topics=topics)

@app.route('/write/<int:essay_id>')
def write_essay(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    student = Student.query.get(essay.student_id)
    if check_archived(student): return check_archived(student)
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


# =========================================================================
# LCCA EXAM MODULE (READING & LISTENING)
# =========================================================================

ANSWER_KEY_LISTENING = {
    "q1": ["keep-fit", "keep-fit studio", "keep fit", "keep fit studio", "a keep-fit studio"],
    "q2": ["swimming"],
    "q3": ["yoga", "yoga classes"],
    "q4": ["salad bar", "a salad bar"],
    "q5": ["500"], "q6": ["1"],
    "q7": ["10/10:00 am, 4:30 pm", "10, 4:30", "10am, 4:30pm", "10:00, 4:30", "10.00, 4.30"],
    "q8": ["180"], "q9": ["assessment"], "q10": ["kynchley"],
    "q11": ["b"], "q12": ["g"], "q13": ["c"], "q14": ["a"], "q15": ["e"], "q16": ["d"],
    "q17": ["19th", "october 19th", "the 19th", "october the 19th"],
    "q18": ["7", "7:00"],
    "q19": ["monday, thursday", "monday and thursday", "monday thursday"],
    "q20": ["18"], "q21": ["a"], "q22": ["in advance"], "q23": ["nursery"], "q24": ["annual fee"],
    "q25": ["tutor"], "q26": ["laptops", "printers"], "q27": ["printers", "laptops"], 
    "q28": ["report writing"], "q29": ["marketing"], "q30": ["individual"],
    "q31": ["feed"], "q32": ["metal", "leather", "metal / leather", "leather / metal", "metal and leather"],
    "q33": ["restrictions"], "q34": ["ships"], "q35": ["england"], "q36": ["built"], "q37": ["poverty"]
}

ANSWER_KEY_READING = {
    "r_q1": ["d"], "r_q2": ["b"], "r_q3": ["e"],
    "r_q4": ["sensors"],
    "r_q7": ["old ships", "old"], "r_q8": ["freight rates"], "r_q9": ["security"], "r_q10": ["delayed"], 
    "r_q11": ["disruption"], "r_q12": ["carry everything"],
    "r_q13": ["ii"], "r_q14": ["viii"], "r_q15": ["xi"], "r_q16": ["xiii"],
    "r_q17": ["vi"], "r_q18": ["i"], "r_q19": ["ix"], "r_q20": ["iv"],
    "r_q21": ["false"], "r_q22": ["not given"], "r_q23": ["true"],
    "r_q24": ["true"], "r_q25": ["not given"], "r_q26": ["false"]
}

@app.get("/lcca/exam")
def lcca_exam_page():
    return render_template("lcca/lcca_exam.html")

@app.post("/api/lcca/submit-reading")
def evaluate_reading():
    payload = request.get_json()
    score = 0
    total_questions = 40
    user_results = {}
    for key, correct_options in ANSWER_KEY_READING.items():
        user_ans = str(payload.get(key, "")).lower().strip()
        is_correct = any(opt in user_ans or user_ans == opt for opt in correct_options)
        if is_correct: score += 1
        user_results[key] = {"user_answer": user_ans, "correct": is_correct}
    c1_2 = set(payload.get("r_q1_2", []))
    if "B" in c1_2: score += 1
    if "C" in c1_2: score += 1
    c3_4 = set(payload.get("r_q3_4", []))
    if "A" in c3_4: score += 1
    if "C" in c3_4: score += 1
    c5_6 = set(payload.get("r_q5_6", []))
    if "A" in c5_6: score += 1
    if "E" in c5_6: score += 1
    return jsonify({"status": "success", "score": score, "max_score": total_questions, "details": user_results})

@app.post("/api/lcca/submit-listening")
def evaluate_listening():
    payload = request.get_json()
    score = 0
    total_questions = 40
    user_results = {}
    for key, correct_options in ANSWER_KEY_LISTENING.items():
        user_ans = str(payload.get(key, "")).lower().strip()
        is_correct = any(opt in user_ans or user_ans == opt for opt in correct_options)
        if is_correct: score += 1
        user_results[key] = {"user_answer": user_ans, "correct": is_correct}
    user_checkboxes = set(payload.get("q38_40", []))
    for val in {"C", "E", "F"}:
        if val in user_checkboxes: score += 1
    return jsonify({"status": "success", "score": score, "max_score": total_questions, "details": user_results})

if __name__ == '__main__':
    app.run(debug=True)

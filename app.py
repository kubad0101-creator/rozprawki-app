import os
import re
import unicodedata
import uuid
import json
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = "Open196!_System_Rozprawek_2024"

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
    universities = db.relationship('University', secondary=teacher_university, backref='teachers')

class University(db.Model):
    __tablename__ = 'universities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    materials = db.relationship('Material', backref='university', lazy=True, cascade="all, delete-orphan")
    students = db.relationship('Student', backref='university', lazy=True)

class Material(db.Model):
    __tablename__ = 'materials'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content_url = db.Column(db.String(500), nullable=False)
    university_id = db.Column(db.Integer, db.ForeignKey('universities.id', ondelete='CASCADE'), nullable=False)

# ----------------- NOWE MODELE GBS -----------------

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

# ----------------- STUDENT I WYPRACOWANIA (QA) -----------------

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

# ----------------- DANE TESTU Z MATEMATYKI GBS -----------------
MATH_QUESTIONS = [
    {"id": 1, "text": "Evaluate 3 to the power of 2:", "options": {"a": "8", "b": "15", "c": "20", "d": "9"}, "answer": "d", "exp": "3 * 3 = 9"},
    {"id": 2, "text": "A shop made £100,000 profit last year and expects a 10% decline this year. Calculate the expected profit for this year.", "options": {"a": "£105,000", "b": "£90,000", "c": "£101,000", "d": "£95,000"}, "answer": "b", "exp": "10% of 100,000 is 10,000. 100,000 - 10,000 = 90,000"},
    {"id": 3, "text": "The cost has increased from £80 to £100. What is the percentage increase in this cost?", "options": {"a": "15%", "b": "17%", "c": "20%", "d": "25%"}, "answer": "d", "exp": "Increase is 20. 20 / 80 = 0.25 = 25%"},
    {"id": 4, "text": "Add the two fractions together: 1/2 + 1/4 = ?", "options": {"a": "3/4", "b": "1", "c": "5%", "d": "3/8"}, "answer": "a", "exp": "1/2 is 2/4. 2/4 + 1/4 = 3/4"},
    {"id": 5, "text": "Evaluate 100,000 multiplied by 0.6", "options": {"a": "60,000", "b": "106,000", "c": "600,000", "d": "-160,000"}, "answer": "a", "exp": "100,000 * 0.6 = 60,000"},
    {"id": 6, "text": "Determine x in the sequence of numbers 3, 8, 13, 18, x", "options": {"a": "24", "b": "23", "c": "25", "d": "-26"}, "answer": "b", "exp": "The sequence increases by 5 each time. 18 + 5 = 23"},
    {"id": 7, "text": "Calculate 37,500 divided by 50:", "options": {"a": "750", "b": "800", "c": "850", "d": "900"}, "answer": "a", "exp": "37500 / 50 = 750"},
    {"id": 8, "text": "Multiply 650 by 9. (650 x 9 = ?)", "options": {"a": "6500", "b": "5850", "c": "6250", "d": "6000"}, "answer": "b", "exp": "650 * 10 = 6500, minus 650 = 5850"},
    {"id": 9, "text": "Calculate the average number from 15, 25, 20", "options": {"a": "20", "b": "18", "c": "19", "d": "22"}, "answer": "a", "exp": "(15 + 25 + 20) / 3 = 60 / 3 = 20"},
    {"id": 10, "text": "Calculate (1 + r) * 5 when r = 5", "options": {"a": "40", "b": "30", "c": "35", "d": "36"}, "answer": "b", "exp": "(1 + 5) = 6. 6 * 5 = 30"},
    {"id": 11, "text": "Evaluate 5/15 as percentage:", "options": {"a": "0.33", "b": "33.33", "c": "66.66", "d": "3.33"}, "answer": "b", "exp": "5/15 = 1/3, which is approximately 33.33%"}
]

# ----------------- INICJALIZACJA BAZY DANYCH -----------------

def setup_database():
    db.create_all()
    
    queries = [
        'ALTER TABLE student_v5 ADD COLUMN university_id INTEGER REFERENCES universities(id)',
        'ALTER TABLE student_v5 ADD COLUMN creator_id INTEGER REFERENCES users(id)',
        'ALTER TABLE student_v5 ADD COLUMN email VARCHAR(120)',
        'ALTER TABLE student_v5 ADD COLUMN gbs_major_id INTEGER REFERENCES gbs_majors(id)',
        'ALTER TABLE student_v5 ADD COLUMN gbs_intake_id INTEGER REFERENCES gbs_intakes(id)',
        'ALTER TABLE student_v5 ADD COLUMN has_math_test BOOLEAN DEFAULT FALSE',
        'ALTER TABLE student_v5 ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
        'ALTER TABLE notification_v5 ADD COLUMN recipient_id INTEGER REFERENCES users(id)',
        'ALTER TABLE notification_v5 ADD COLUMN student_id INTEGER REFERENCES student_v5(id)'
    ]

    for q in queries:
        try:
            db.session.execute(text(q))
            db.session.commit()
        except Exception:
            db.session.rollback()

    qa_uni = University.query.filter_by(name="QA Higher Education").first()
    if not qa_uni:
        qa_uni = University(name="QA Higher Education")
        db.session.add(qa_uni)
        
    gbs_uni = University.query.filter_by(name="GBS").first()
    if not gbs_uni:
        gbs_uni = University(name="GBS")
        db.session.add(gbs_uni)
    db.session.commit()

    gbs_majors_data = [
        ("Business and Tourism Management with FY", True),
        ("Accounting and Financial Management with FY", True),
        ("Psychology with Councelling with FY", False),
        ("Construction Management with FY", False),
        ("Project Management with FY", False),
        ("Computing with FY", False),
        ("Health, Wellbeing and Social Care with FY", False),
        ("Global Business and Entrepreneurship with FY", False)
    ]
    for m_name, is_cccu in gbs_majors_data:
        if not GbsMajor.query.filter_by(name=m_name).first():
            db.session.add(GbsMajor(name=m_name, is_cccu=is_cccu))
    db.session.commit()

    unassigned_students = Student.query.filter_by(university_id=None).all()
    if unassigned_students:
        for student in unassigned_students:
            student.university_id = qa_uni.id
        db.session.commit()

    if not User.query.filter_by(username="Julia").first():
        db.session.add(User(username="Julia", password_hash=generate_password_hash("Open196!"), role="admin"))
    if not User.query.filter_by(username="Kuba").first():
        db.session.add(User(username="Kuba", password_hash=generate_password_hash("Open196!"), role="admin"))
    db.session.commit()

with app.app_context():
    setup_database()

# ----------------- DEKORATORY I POMOCNICZE -----------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def slugify(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')

def sort_students(students, sort_by):
    if sort_by == 'pending':
        students.sort(key=lambda s: sum(1 for e in s.essays if e.is_completed and not e.feedback), reverse=True)
    elif sort_by == 'alpha_desc':
        students.sort(key=lambda s: s.name.lower(), reverse=True)
    else: 
        students.sort(key=lambda s: s.name.lower())
    return students

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

# ----------------- ŚCIEŻKI AUTORYZACJI -----------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            if user.role == 'admin':
                return redirect(url_for('panel_master'))
            return redirect(url_for('panel_dashboard'))
            
        return render_template('login.html', error="Błędny login lub hasło")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ----------------- NOWY PANEL KOORDYNACJI SYSTEMU PŁATFORMY (/panel) -----------------

@app.route('/panel')
@login_required
def panel_dashboard():
    user = User.query.get(session['user_id'])
    teacher_name = user.username
    universities = University.query.all() if user.role == 'admin' else user.universities
    uni_ids = [u.id for u in universities]
    
    majors = GbsMajor.query.all()
    intakes = GbsIntake.query.all()
    
    search_query = request.args.get('q', '').lower()
    sort_by = request.args.get('sort', 'alpha')
    
    students_query = Student.query.filter_by(is_archived=False)
    
    if user.role != 'admin':
        students_query = students_query.filter(Student.university_id.in_(uni_ids))
        notifications = Notification.query.join(Student, Notification.student_id == Student.id).filter(
            Student.university_id.in_(uni_ids)
        ).order_by(Notification.created_at.desc()).limit(15).all()
    else:
        notifications = Notification.query.order_by(Notification.created_at.desc()).limit(15).all()
        
    if search_query:
        students_query = students_query.filter(db.func.lower(Student.name).contains(search_query))
        
    students = sort_students(students_query.all(), sort_by)
    
    qa_students = [s for s in students if s.university and 'QA' in s.university.name]
    gbs_students = [s for s in students if s.university and 'GBS' in s.university.name]
    
    return render_template('panel_dashboard.html', 
                           qa_students=qa_students, 
                           gbs_students=gbs_students, 
                           universities=universities, 
                           majors=majors, 
                           intakes=intakes, 
                           teacher_name=teacher_name,
                           notifications=notifications, 
                           user=user, 
                           sort_by=sort_by, 
                           search_query=search_query)

@app.route('/panel/student/add', methods=['POST'])
@login_required
def panel_add_student():
    user = User.query.get(session['user_id'])
    name = request.form.get('name')
    university_id = request.form.get('university_id')
    
    if not university_id and len(user.universities) == 1: 
        university_id = user.universities[0].id
        
    if not name or not university_id: 
        return redirect(url_for('panel_dashboard'))
        
    slug = f"{uuid.uuid4().hex[:4]}-{slugify(name)}"
    uni = University.query.get(int(university_id))
    
    new_student = Student(name=name, url_slug=slug, university_id=uni.id, creator_id=user.id)
    
    if "GBS" in uni.name:
        new_student.email = request.form.get('email')
        major_id = request.form.get('major_id')
        intake_id = request.form.get('intake_id')
        
        new_student.gbs_major_id = int(major_id) if major_id else None
        new_student.gbs_intake_id = int(intake_id) if intake_id else None
        new_student.has_math_test = 'has_math_test' in request.form
        db.session.add(new_student)
    else:
        db.session.add(new_student)
        for title, full_topic in PRACTICE_TOPICS:
            db.session.add(Essay(title=title, topic_full=full_topic, is_exam=False, student=new_student))
        db.session.add(Essay(title="Egzamin", topic_full="[EGZAMIN] Tematy będą dostępne po wejściu.", is_exam=True, student=new_student))
        db.session.add(Essay(title="Egzamin Dodatkowy", topic_full="Wpisz temat nr 1...|||Wpisz temat nr 2...", is_exam=True, student=new_student))
    
    db.session.commit()
    flash(f"Student {name} dodany pomyślnie!", "success")
    return redirect(url_for('panel_dashboard'))

@app.route('/panel/materials', methods=['GET', 'POST'])
@login_required
def panel_materials():
    user = User.query.get(session['user_id'])
    universities = University.query.all() if user.role == 'admin' else user.universities
    
    if request.method == 'POST':
        title = request.form.get('title')
        content_url = request.form.get('content_url')
        university_id = request.form.get('university_id')
        
        if not university_id and len(universities) == 1:
            university_id = universities[0].id
            
        if title and content_url and university_id:
            db.session.add(Material(title=title, content_url=content_url, university_id=int(university_id)))
            db.session.commit()
            flash("Materiał dodany!", "success")
        return redirect(url_for('panel_materials'))
        
    return render_template('panel_materials.html', universities=universities, user=user)

@app.route('/panel/material/delete/<int:material_id>', methods=['POST'])
@login_required
def panel_delete_material(material_id):
    material = Material.query.get_or_404(material_id)
    user = User.query.get(session['user_id'])
    if user.role == 'admin' or material.university in user.universities:
        db.session.delete(material)
        db.session.commit()
    return redirect(url_for('panel_materials'))

# ----------------- TRASY DLA MATERIAŁÓW HTML (GBS) -----------------

@app.route('/gbs/materials/writing_guide')
def gbs_writing_guide():
    return render_template('gbs/writing_guide.html')

@app.route('/gbs/materials/exam_info')
def gbs_exam_info():
    return render_template('gbs/exam_info.html')


# ----------------- PANEL GBS (KONFIGURACJA NABORÓW I PYTAŃ) -----------------

@app.route('/panel/gbs', methods=['GET', 'POST'])
@login_required
def panel_gbs():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_intake':
            db.session.add(GbsIntake(name=request.form.get('name'), color=request.form.get('color')))
            db.session.commit()
            flash("Nabór dodany!", "success")
        elif action == 'edit_intake':
            intake = GbsIntake.query.get(request.form.get('intake_id'))
            if intake:
                intake.name = request.form.get('name')
                intake.color = request.form.get('color')
                db.session.commit()
                flash("Zaktualizowano nabór!", "success")
        elif action == 'delete_intake':
            intake = GbsIntake.query.get(request.form.get('intake_id'))
            if intake:
                db.session.delete(intake)
                db.session.commit()
                flash("Usunięto nabór i wszystkie jego pytania.", "success")
        return redirect(url_for('panel_gbs'))

    intakes = GbsIntake.query.all()
    return render_template('gbs/panel_gbs.html', intakes=intakes)

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
        qset.q1 = request.form.get('q1', '')
        qset.q2 = request.form.get('q2', '')
        qset.q3 = request.form.get('q3', '')
        db.session.commit()
        flash("Pytania zapisane!", "success")
        return redirect(url_for('panel_gbs_intake', intake_id=intake.id))

    majors = GbsMajor.query.all()
    question_sets = {qs.major_id: qs for qs in intake.question_sets}
    return render_template('gbs/panel_gbs_intake.html', intake=intake, majors=majors, question_sets=question_sets)

# ----------------- WIDOKI I AKCJE STUDENTA -----------------

@app.route('/student/<url_slug>')
def student_dashboard(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    
    # WYMUSZAMY POBRANIE MATERIAŁÓW (Naprawa pustej listy)
    materials = student.university.materials if student.university else []
    
    if student.university and "GBS" in student.university.name:
        return render_template('gbs/student_gbs_dashboard.html', student=student, materials=materials)
    
    return render_template('qa/student.html', student=student, exam_topics=EXAM_TOPICS, materials=materials)

@app.route('/gbs/task/<url_slug>')
def gbs_task(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    is_exam = request.args.get('exam') == 'true'
    
    qset = GbsQuestionSet.query.filter_by(intake_id=student.gbs_intake_id, major_id=student.gbs_major_id).first()
    questions = [qset.q1, qset.q2, qset.q3] if qset else ["Pytanie 1 (Brak pytań w naborze)", "Pytanie 2 (Brak)", "Pytanie 3 (Brak)"]
    
    return render_template('gbs/gbs_task.html', student=student, questions=questions, is_exam=is_exam)

@app.route('/api/gbs/submit/<int:student_id>', methods=['POST'])
def gbs_submit(student_id):
    student = Student.query.get_or_404(student_id)
    data = request.get_json()
    attempt = GbsAttempt(
        student_id=student.id,
        q1_ans=data.get('q1', ''),
        q2_ans=data.get('q2', ''),
        q3_ans=data.get('q3', ''),
        is_exam=data.get('is_exam', False)
    )
    db.session.add(attempt)
    msg = f"<a href='/admin/student/{student.id}' class='notif-link'><b>{student.name}</b> oddał/a zadanie GBS.</a>"
    db.session.add(Notification(message=msg, recipient_id=student.creator_id, student_id=student.id))
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/gbs/math/<url_slug>')
def math_test(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    if not student.has_math_test: 
        return "Brak dostępu do testu z matematyki", 403
    return render_template('gbs/math_test.html', student=student, questions=MATH_QUESTIONS)

@app.route('/api/math/submit/<int:student_id>', methods=['POST'])
def math_submit(student_id):
    student = Student.query.get_or_404(student_id)
    data = request.get_json() 
    
    score = 0
    for q in MATH_QUESTIONS:
        q_id = str(q['id'])
        if data.get(q_id) == q['answer']:
            score += 1
            
    result = MathTestResult(student_id=student.id, score=score, total=len(MATH_QUESTIONS), answers_json=json.dumps(data))
    db.session.add(result)
    msg = f"<a href='/admin/student/{student.id}' class='notif-link'><b>{student.name}</b> ukończył/a test z matmy ({score}/{len(MATH_QUESTIONS)}).</a>"
    db.session.add(Notification(message=msg, recipient_id=student.creator_id, student_id=student.id))
    db.session.commit()
    return jsonify({"status": "success", "score": score})

# ----------------- PANEL MASTER DLA ADMINA -----------------

@app.route('/panel/master', methods=['GET', 'POST'])
@admin_required
def panel_master():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_teacher':
            username = request.form.get('username')
            password = request.form.get('password')
            uni_ids = request.form.getlist('universities')
            if username and password:
                if not User.query.filter_by(username=username).first():
                    hashed_pw = generate_password_hash(password)
                    new_teacher = User(username=username, password_hash=hashed_pw, role='teacher')
                    for uid in uni_ids:
                        uni = University.query.get(int(uid))
                        if uni:
                            new_teacher.universities.append(uni)
                    db.session.add(new_teacher)
                    db.session.commit()
                    flash(f"Konto dla nauczyciela '{username}' utworzone pomyślnie!", "success")
                else:
                    flash(f"BŁĄD: Login '{username}' jest już zajęty.", "error")
        elif action == 'edit_teacher':
            teacher_id = request.form.get('teacher_id')
            new_password = request.form.get('new_password')
            uni_ids = request.form.getlist('universities')
            teacher = User.query.get(teacher_id)
            if teacher:
                if new_password:
                    teacher.password_hash = generate_password_hash(new_password)
                teacher.universities = []
                for uid in uni_ids:
                    uni = University.query.get(int(uid))
                    if uni:
                        teacher.universities.append(uni)
                db.session.commit()
                flash(f"Zaktualizowano dane nauczyciela '{teacher.username}'.", "success")
        elif action == 'delete_teacher':
            teacher_id = request.form.get('teacher_id')
            teacher = User.query.get(teacher_id)
            if teacher:
                db.session.delete(teacher)
                db.session.commit()
                flash("Konto usunięte.", "success")
        return redirect(url_for('panel_master'))

    teachers = User.query.filter_by(role='teacher').all()
    all_unis = University.query.all()
    teacher_stats = {}
    for t in teachers:
        active_students = Student.query.filter_by(creator_id=t.id, is_archived=False).count()
        archived_students = Student.query.filter_by(creator_id=t.id, is_archived=True).count()
        teacher_stats[t.id] = {'active': active_students, 'archived': archived_students, 'total': active_students + archived_students}
    return render_template('panel_master.html', teachers=teachers, all_unis=all_unis, stats=teacher_stats)


# ----------------- STARE FUNKCJE ROZPRAWEK I ADMINA (QA) -----------------

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    return redirect(url_for('panel_dashboard'))

@app.route('/admin/archive')
@login_required
def admin_archive():
    user = User.query.get(session['user_id'])
    query = Student.query.filter_by(is_archived=True)
    if user.role != 'admin':
        uni_ids = [u.id for u in user.universities]
        query = query.filter(Student.university_id.in_(uni_ids))
    archived_students = query.order_by(Student.name.asc()).all()
    return render_template('qa/admin_archive.html', archived_students=archived_students)

@app.route('/admin/student/<int:student_id>/restore', methods=['POST'])
@login_required
def restore_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_archived = False
    db.session.commit()
    return redirect(url_for('admin_archive'))

@app.route('/admin/student/<int:student_id>/delete_forever', methods=['POST'])
@admin_required
def delete_student_forever(student_id):
    student = Student.query.get_or_404(student_id)
    Essay.query.filter_by(student_id=student.id).delete()
    db.session.delete(student)
    db.session.commit()
    return redirect(url_for('admin_archive'))

@app.route('/admin/student/<int:student_id>')
@login_required
def admin_student_detail(student_id):
    student = Student.query.get_or_404(student_id)
    user = User.query.get(session['user_id'])
    
    if user.role != 'admin':
        uni_ids = [u.id for u in user.universities]
        if student.university_id not in uni_ids:
            flash("Odmowa dostępu: Ten uczeń nie należy do przypisanej Ci uczelni.", "error")
            return redirect(url_for('panel_dashboard'))

    essays_sorted = sorted(student.essays, key=lambda x: x.last_edited_at or datetime.min, reverse=True)
    gbs_attempts = sorted(student.gbs_attempts, key=lambda x: x.submitted_at, reverse=True)
    math_results = sorted(student.math_results, key=lambda x: x.submitted_at, reverse=True)
    
    return render_template('qa/student_detail.html', student=student, essays_sorted=essays_sorted, gbs_attempts=gbs_attempts, math_results=math_results)

@app.route('/admin/student/<int:student_id>/archive', methods=['POST'])
@login_required
def toggle_archive(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_archived = True
    db.session.commit()
    return redirect(url_for('panel_dashboard'))

@app.route('/admin/student/<int:student_id>/extra_exam', methods=['POST'])
@login_required
def update_extra_exam(student_id):
    student = Student.query.get_or_404(student_id)
    extra_exam = Essay.query.filter_by(student_id=student.id, title="Egzamin Dodatkowy").first()
    if not extra_exam:
        extra_exam = Essay(title="Egzamin Dodatkowy", is_exam=True, student_id=student.id)
        db.session.add(extra_exam)
    t1 = request.form.get('topic1', 'Temat 1')
    t2 = request.form.get('topic2', 'Temat 2')
    extra_exam.topic_full = f"{t1}|||{t2}"
    db.session.commit()
    return redirect(url_for('admin_student_detail', student_id=student.id))

@app.route('/admin/essay/<int:essay_id>/return', methods=['POST'])
@login_required
def return_essay(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    essay.is_completed = False
    all_notifs = Notification.query.filter(Notification.message.contains(essay.student.name)).all()
    for n in all_notifs:
        db.session.delete(n)
    db.session.commit()
    return redirect(url_for('admin_student_detail', student_id=essay.student_id))

@app.route('/admin/essay/<int:essay_id>/feedback', methods=['POST'])
@login_required
def save_feedback(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    essay.feedback = request.form.get('feedback')
    essay.marked_content = request.form.get('marked_content')
    
    all_notifs = Notification.query.filter(Notification.message.contains(essay.student.name)).all()
    for n in all_notifs:
        db.session.delete(n)

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
    db.session.delete(notif)
    db.session.commit()
    return redirect(url_for('panel_dashboard'))

@app.route('/exam/<url_slug>')
def exam_direct_link(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    exam_essay = Essay.query.filter_by(student_id=student.id, title="Egzamin").first_or_404()
    return render_template('qa/write.html', essay=exam_essay, exam_topics=EXAM_TOPICS)

@app.route('/exam_extra/<url_slug>')
def exam_extra_direct_link(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    exam_essay = Essay.query.filter_by(student_id=student.id, title="Egzamin Dodatkowy").first()
    if not exam_essay:
        return "Egzamin Dodatkowy nie został jeszcze utworzony.", 404
    custom_topics = ["Brak tematu 1", "Brak tematu 2"]
    if exam_essay.topic_full and '|||' in exam_essay.topic_full:
        custom_topics = exam_essay.topic_full.split('|||')
    return render_template('qa/write.html', essay=exam_essay, exam_topics=custom_topics)

@app.route('/write/<int:essay_id>')
def write_essay(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    topics = EXAM_TOPICS
    if essay.title == "Egzamin Dodatkowy":
        topics = essay.topic_full.split('|||') if essay.topic_full and '|||' in essay.topic_full else ["Brak tematu 1", "Brak tematu 2"]
    return render_template('qa/write.html', essay=essay, exam_topics=topics)

@app.route('/api/save/<int:essay_id>', methods=['POST'])
def auto_save(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    data = request.get_json()
    essay.content = data.get('content', essay.content)
    essay.time_spent = data.get('time_spent', essay.time_spent)
    if 'chosen_topic' in data:
        essay.chosen_topic = data['chosen_topic']
    
    became_completed = False
    if data.get('is_completed') and not essay.is_completed:
        essay.is_completed = True
        became_completed = True
    
    now = datetime.now()
    if not essay.started_at: essay.started_at = now
    essay.last_edited_at = now
    db.session.commit()

    if became_completed:
        msg = f"<a href='/admin/student/{essay.student_id}' class='notif-link'><b>{essay.student.name}</b> ukończył/a: '{essay.title[:30]}'</a>"
        notif = Notification(message=msg, recipient_id=essay.student.creator_id, student_id=essay.student_id)
        db.session.add(notif)
        db.session.commit()
        
    return jsonify({"status": "success"})

@app.route('/api/reset/<int:essay_id>', methods=['POST'])
def reset_essay(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    if not essay.is_exam:
        essay.content = ""
        essay.marked_content = ""
        essay.time_spent = 0
        essay.is_completed = False
        db.session.commit()
    return jsonify({"status": "reset"})

if __name__ == '__main__':
    app.run(debug=True)

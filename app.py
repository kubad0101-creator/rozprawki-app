import os
import re
import unicodedata
import uuid
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

class Student(db.Model):
    __tablename__ = 'student_v5'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url_slug = db.Column(db.String(150), unique=True, nullable=False)
    exam_unlocked = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    
    university_id = db.Column(db.Integer, db.ForeignKey('universities.id'), nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    essays = db.relationship('Essay', backref='student', lazy=True, cascade="all, delete-orphan")

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
    # NOWE: Przypisanie powiadomienia do konkretnego nauczyciela
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

# ----------------- INICJALIZACJA BAZY DANYCH -----------------

def setup_database():
    db.create_all()
    try:
        db.session.execute(text('ALTER TABLE student_v5 ADD COLUMN university_id INTEGER REFERENCES universities(id)'))
        db.session.execute(text('ALTER TABLE student_v5 ADD COLUMN creator_id INTEGER REFERENCES users(id)'))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(text('ALTER TABLE notification_v5 ADD COLUMN recipient_id INTEGER REFERENCES users(id)'))
        db.session.commit()
    except Exception:
        db.session.rollback()

    if not User.query.filter_by(username="Julia").first():
        db.session.add(User(username="Julia", password_hash=generate_password_hash("Open196!"), role="admin"))
    if not User.query.filter_by(username="Kuba").first():
        db.session.add(User(username="Kuba", password_hash=generate_password_hash("Open196!"), role="admin"))
    db.session.commit()
    
    if not University.query.filter_by(name="QA Higher Education").first():
        db.session.add(University(name="QA Higher Education"))
    if not University.query.filter_by(name="GBS").first():
        db.session.add(University(name="GBS"))
    db.session.commit()

with app.app_context():
    setup_database()

# ----------------- DEKORATORY ZABEZPIECZEŃ -----------------

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
    universities = University.query.all() if user.role == 'admin' else user.universities
    uni_ids = [u.id for u in universities]
    
    search_query = request.args.get('q', '').lower()
    students_query = Student.query.filter_by(is_archived=False)
    
    if user.role != 'admin':
        students_query = students_query.filter(Student.university_id.in_(uni_ids))
        notifications = Notification.query.filter_by(recipient_id=user.id).order_by(Notification.created_at.desc()).limit(10).all()
    else:
        notifications = Notification.query.order_by(Notification.created_at.desc()).limit(10).all()
        
    if search_query:
        students_query = students_query.filter(db.func.lower(Student.name).contains(search_query))
        
    students = students_query.order_by(Student.name.asc()).all()
    
    return render_template('panel_dashboard.html', students=students, universities=universities, notifications=notifications, search_query=search_query, user=user)

@app.route('/panel/student/add', methods=['POST'])
@login_required
def panel_add_student():
    name = request.form.get('name')
    university_id = request.form.get('university_id')
    
    if not name or not university_id:
        return redirect(url_for('panel_dashboard'))
        
    slug = f"{uuid.uuid4().hex[:4]}-{slugify(name)}"
    new_student = Student(name=name, url_slug=slug, university_id=int(university_id), creator_id=session['user_id'])
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
                    flash(f"BŁĄD: Login '{username}' jest już zajęty. Wybierz inną nazwę.", "error")
                    
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
        teacher_stats[t.id] = {
            'active': active_students,
            'archived': archived_students,
            'total': active_students + archived_students
        }
        
    return render_template('panel_master.html', teachers=teachers, all_unis=all_unis, stats=teacher_stats)


# ----------------- MODUŁ SPRAWDZANIA ROZPRAWEK (/admin) -----------------

@app.route('/admin', methods=['GET', 'POST'])
@login_required # Zmiana! Teraz nauczyciele mają tu dostęp, ale widzą tylko swoich
def admin():
    user = User.query.get(session['user_id'])
    uni_ids = [u.id for u in user.universities]
    
    if request.method == 'POST':
        student_name = request.form.get('name')
        slug = f"{uuid.uuid4().hex[:4]}-{slugify(student_name)}"
        # Domyślnie przypisz pierwszą uczelnię z listy nauczyciela, jeśli dodaje ucznia z tego panelu
        uni_id = uni_ids[0] if uni_ids else None 
        new_student = Student(name=student_name, url_slug=slug, creator_id=user.id, university_id=uni_id)
        db.session.add(new_student)
        
        for title, full_topic in PRACTICE_TOPICS:
            db.session.add(Essay(title=title, topic_full=full_topic, is_exam=False, student=new_student))
        db.session.add(Essay(title="Egzamin", topic_full="[EGZAMIN] Tematy będą dostępne po wejściu.", is_exam=True, student=new_student))
        db.session.add(Essay(title="Egzamin Dodatkowy", topic_full="Wpisz temat nr 1...|||Wpisz temat nr 2...", is_exam=True, student=new_student))
        db.session.commit()
        return redirect(url_for('admin'))
        
    search_query = request.args.get('q', '').lower()
    active_students_query = Student.query.filter_by(is_archived=False)
    
    # IZOLACJA DANYCH NAUCZYCIELI
    if user.role != 'admin':
        active_students_query = active_students_query.filter(Student.university_id.in_(uni_ids))
        notifications = Notification.query.filter_by(recipient_id=user.id).order_by(Notification.created_at.desc()).limit(15).all()
    else:
        notifications = Notification.query.order_by(Notification.created_at.desc()).limit(15).all()

    if search_query:
        active_students_query = active_students_query.filter(db.func.lower(Student.name).contains(search_query))
    
    active_students = active_students_query.order_by(Student.name.asc()).all()
    return render_template('admin.html', active_students=active_students, notifications=notifications, search_query=search_query)

@app.route('/admin/archive')
@login_required
def admin_archive():
    user = User.query.get(session['user_id'])
    query = Student.query.filter_by(is_archived=True)
    if user.role != 'admin':
        uni_ids = [u.id for u in user.universities]
        query = query.filter(Student.university_id.in_(uni_ids))
    archived_students = query.order_by(Student.name.asc()).all()
    return render_template('admin_archive.html', archived_students=archived_students)

@app.route('/admin/student/<int:student_id>/restore', methods=['POST'])
@login_required
def restore_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_archived = False
    db.session.commit()
    return redirect(url_for('admin_archive'))

@app.route('/admin/student/<int:student_id>/delete_forever', methods=['POST'])
@admin_required # Tylko admin może całkowicie usunąć
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
    essays_sorted = sorted(student.essays, key=lambda x: x.last_edited_at or datetime.min, reverse=True)
    return render_template('student_detail.html', student=student, essays_sorted=essays_sorted)

@app.route('/admin/student/<int:student_id>/archive', methods=['POST'])
@login_required
def toggle_archive(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_archived = True
    db.session.commit()
    return redirect(url_for('admin'))

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
    
    # Usuwanie powiadomień po sprawdzeniu
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
    return redirect(url_for('admin'))

# ----------------- WIDOKI STUDENTA -----------------

@app.route('/student/<url_slug>')
def student_dashboard(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    materials = []
    if student.university:
        materials = student.university.materials
    return render_template('student.html', student=student, exam_topics=EXAM_TOPICS, materials=materials)

@app.route('/exam/<url_slug>')
def exam_direct_link(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    exam_essay = Essay.query.filter_by(student_id=student.id, title="Egzamin").first_or_404()
    return render_template('write.html', essay=exam_essay, exam_topics=EXAM_TOPICS)

@app.route('/exam_extra/<url_slug>')
def exam_extra_direct_link(url_slug):
    student = Student.query.filter_by(url_slug=url_slug).first_or_404()
    exam_essay = Essay.query.filter_by(student_id=student.id, title="Egzamin Dodatkowy").first()
    if not exam_essay:
        return "Egzamin Dodatkowy nie został jeszcze utworzony.", 404
    custom_topics = ["Brak tematu 1", "Brak tematu 2"]
    if exam_essay.topic_full and '|||' in exam_essay.topic_full:
        custom_topics = exam_essay.topic_full.split('|||')
    return render_template('write.html', essay=exam_essay, exam_topics=custom_topics)

@app.route('/write/<int:essay_id>')
def write_essay(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    topics = EXAM_TOPICS
    if essay.title == "Egzamin Dodatkowy":
        topics = essay.topic_full.split('|||') if essay.topic_full and '|||' in essay.topic_full else ["Brak tematu 1", "Brak tematu 2"]
    return render_template('write.html', essay=essay, exam_topics=topics)

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

    # Logika powiadomień po ukończeniu pracy
    if became_completed:
        msg = f"<a href='/admin/student/{essay.student_id}' class='notif-link'><b>{essay.student.name}</b> ukończył/a: '{essay.title[:30]}'</a>"
        notif = Notification(message=msg, recipient_id=essay.student.creator_id)
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

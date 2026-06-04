import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

database_url = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    token = db.Column(db.String(36), unique=True, nullable=False)
    essays = db.relationship('Essay', backref='student', lazy=True)

class Essay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, default="")
    is_exam = db.Column(db.Boolean, default=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

with app.app_context():
    db.create_all()

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        student_name = request.form.get('name')
        new_token = str(uuid.uuid4())
        new_student = Student(name=student_name, token=new_token)
        db.session.add(new_student)
        db.session.add(Essay(title="Ćwiczenie 1: Wolna wola", is_exam=False, student=new_student))
        db.session.add(Essay(title="Egzamin", is_exam=True, student=new_student))
        db.session.commit()
        return redirect(url_for('admin'))
    students = Student.query.all()
    return render_template('admin.html', students=students)

@app.route('/student/<token>')
def student_dashboard(token):
    student = Student.query.filter_by(token=token).first_or_404()
    return render_template('student.html', student=student)

@app.route('/write/<int:essay_id>')
def write_essay(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    return render_template('write.html', essay=essay)

@app.route('/api/save/<int:essay_id>', methods=['POST'])
def auto_save(essay_id):
    essay = Essay.query.get_or_404(essay_id)
    data = request.get_json()
    essay.content = data.get('content', '')
    db.session.commit()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)

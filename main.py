import os
from flask import Flask, render_template, request, redirect, session, flash
from datetime import datetime, timedelta
from collections import defaultdict
from werkzeug.utils import secure_filename
import requests
from firebase_admin import messaging
import uuid
import pandas as pd
from flask import send_file
from io import BytesIO   
import io
import pandas as pd
from flask import send_file
import firebase_admin
from firebase_admin import credentials, firestore, storage
from uuid import uuid4
from math import radians, cos, sin, sqrt, atan2


def calculate_distance_km(lat1, lon1, lat2, lon2):
    R = 6371  # Radius of Earth in KM
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

SCHOOL_LAT = 11.08756
SCHOOL_LON = 77.32061

import json

# Load Firebase service account from environment variable (Railway)
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore, storage

cred = credentials.Certificate("/Users/kaniskten/Downloads/erp4-main//67.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'school-erp-fc020.firebasestorage.app'  
})
db = firestore.client()
bucket = storage.bucket()


def send_push_notification(token, title, body):
    """Send a push notification using Firebase Cloud Messaging."""
    print(f"[DEBUG] Preparing to send notification to token: {token}")
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=token
    )
    try:
        response = messaging.send(message)
        print(f"✅ Notification sent: {response}")
    except Exception as e:
        print(f"❌ Failed to send notification: {e}")

def initialize_firebase():
    default_users = {
        'admin': {'password': 'admin123', 'role': 'admin'},
        'teacher1': {'password': 'teach123', 'role': 'teacher', 'board': 'Montessori', 'grade': 'KG'},
        'student1': {'password': 'stud123', 'role': 'student', 'board': 'CBSE', 'grade': 7},
        'correspondent': {'password': 'corr123', 'role': 'correspondent'},
        'prek_student': {'password': 'prek123', 'role': 'student', 'board': 'CBSE', 'grade': 'Pre.KG'},
        'jrkg_student': {'password': 'jrkg123', 'role': 'student', 'board': 'CBSE', 'grade': 'Jr.KG'},
        'srkg_student': {'password': 'srkg123', 'role': 'student', 'board': 'CBSE', 'grade': 'Sr.KG'},
    }

    for username, data in default_users.items():
        user_ref = db.collection('users').document(username)
        if not user_ref.get().exists:
            user_ref.set(data)
            print(f"✅ Created user: {username}")
    collections = ['attendance', 'fees', 'messages', 'results', 'timetable', 'nutriments', 'student_info', 'gallery']
    for collection in collections:
        if not db.collection(collection).get():
            print(f"✅ Initialized collection: {collection}")

initialize_firebase()

app = Flask(__name__)
app.secret_key = 'secret'

@app.route('/')
def index():
    return redirect('/login')

UPLOAD_FOLDER = 'C:/Users/kanis/login/static/gallery_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload_image', methods=['GET', 'POST'])
def upload_image():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')

    if request.method == 'POST':
        if 'image' not in request.files:
            return "No file part"
        file = request.files['image']
        if file.filename == '':
            return "No selected file"
        if file and allowed_file(file.filename):
            # Create a unique filename
            filename = f"{uuid4().hex}_{secure_filename(file.filename)}"
            blob = bucket.blob(f'gallery/{filename}')
            
            # Upload the file directly
            blob.upload_from_file(file, content_type=file.content_type)
            blob.make_public()  # Optional: make it accessible
            
            # Save public URL to Firestore
            image_url = blob.public_url
            db.collection('gallery').add({'url': image_url})
            
            return redirect('/gallery')
        else:
            return "Unsupported file type. Please upload PNG, JPG, JPEG, GIF, or BMP."
    return render_template('upload_image.html')

@app.route('/update_fcm_token', methods=['POST'])
def update_fcm_token():
    data = request.json
    username = data.get('username')
    token = data.get('token')
    print(f"[DEBUG] FCM token received: {username} => {token}")
    if username and token:
        db.collection('users').document(username).update({'fcm_token': token})
        return {'status': 'success'}
    return {'status': 'error', 'message': 'Missing username or token'}, 400

@app.route('/test_notification')
def test_notification():
    test_token = request.args.get('token')
    if not test_token:
        return "No token provided. Use /test_notification?token=YOUR_FCM_TOKEN", 400
    send_push_notification(test_token, "Test Notification", "This is a test message.")
    return "Notification attempted. Check your logs."

@app.route('/gallery')
def view_gallery():
    images = [doc.to_dict()['url'] for doc in db.collection('gallery').stream()]
    return render_template('gallery.html', images=images)

@app.route('/firebase-messaging-sw.js')
def firebase_sw():
    return send_file('templates/firebase-messaging-sw.js', mimetype='application/javascript')

# --- LOGIN ---



@app.route('/login', methods=['GET', 'POST'])
def login():
    # If the user is already logged in, redirect to home
    if 'username' in session:
        return redirect('/home')

    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_ref = db.collection('users').document(username)
        user = user_ref.get()
        if user.exists and user.to_dict()['password'] == password:
            session['username'] = username
            session['role'] = user.to_dict()['role']
            # --- Track last login ---
            user_ref.update({'last_login': datetime.now().strftime('%Y-%m-%d')})
            return redirect('/home')
        error = "Invalid username or password!"

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/home')
def home():
    username = session.get('username')
    if not username:
        return redirect('/login')

    # Fetch user info
    user_ref = db.collection('users').document(username)
    user_data = user_ref.get().to_dict()
    if not user_data:
        return "User not found!", 404

    grade = user_data.get('grade', 'N/A')
    role = user_data.get('role', 'N/A')
    school_name = "School"

    # Log homepage visit
    db.collection('usage_logs').add({
        'username': username,
        'role': role,
        'visited_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

    # Birthday popup logic
    birthday_popup = None
    profile_doc = db.collection('student_profile').document(username).get()
    if profile_doc.exists:
        profile = profile_doc.to_dict()
        dob = profile.get('dob', '')
        today = datetime.now().strftime('%m-%d')
        print(f"[DEBUG] Today's date: {today}")
        print(f"[DEBUG] DOB raw value: {dob}")

        dob_obj = None
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
            try:
                dob_obj = datetime.strptime(dob, fmt)
                break
            except Exception as e:
                continue  # Just skip to next format

        if dob_obj:
            dob_mmdd = dob_obj.strftime('%m-%d')
            print(f"[DEBUG] Parsed DOB MM-DD: {dob_mmdd}")
            if dob_mmdd == today:
                print(f"[DEBUG] Birthday matched for {username}")
                birthday_popup = {
                    'photo': profile.get('student_photo', ''),
                    'first_name': profile.get('first_name', ''),
                    'middle_name': profile.get('middle_name', ''),
                    'last_name': profile.get('last_name', '')
                }
        else:
            print(f"[DEBUG] DOB format not recognized for user {username}")

    return render_template(
        'home.html',
        username=username,
        grade=grade,
        role=role,
        school_name=school_name,
        birthday_popup=birthday_popup
    )
# --- ADD STUDENT (ADMIN) ---
@app.route('/add_student', methods=['GET', 'POST'])
def add_student():
    if session.get('role') != 'admin':
        return redirect('/home')
    student_grades = ['Pre.KG', 'Jr.KG', 'Sr.KG'] + [str(i) for i in range(1, 13)]
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        board = request.form['board']
        grade = request.form['grade']  # Always string!
        db.collection('users').document(username).set({
            'password': password,
            'role': 'student',
            'board': board,
            'grade': grade
        })
        return redirect('/home')
    return render_template('add_student.html', student_grades=student_grades)

@app.route('/add_teacher', methods=['GET', 'POST'])
def add_teacher():
    if session.get('role') not in ['admin', 'correspondent']:
        return redirect('/home')
    teacher_grades = ['KG'] + [str(i) for i in range(1, 13)]
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        board = request.form['board']
        grade = request.form['grade']  # Always string!
        db.collection('users').document(username).set({
            'password': password,
            'role': 'teacher',
            'board': board,
            'grade': grade
        })
        return redirect('/home')
    return render_template('add_teacher.html', teacher_grades=teacher_grades)

@app.route('/attendance', methods=['GET', 'POST'])
def attendance():
    if 'username' not in session or session.get('role') not in ['teacher', 'admin']:
        return redirect('/home')

    role = session.get('role')
    selected_grade = ''
    selected_board = ''
    students = []

    # Determine student list based on user role
    if role == 'teacher':
        user = db.collection('users').document(session['username']).get().to_dict()
        teacher_grade = user.get('grade')
        teacher_board = user.get('board')

        if teacher_grade == 'KG':
            student_docs = db.collection('users')\
                        .where('role', '==', 'student')\
                        .where('board', '==', teacher_board)\
                        .where('grade', 'in', ['Pre.KG', 'Jr.KG', 'Sr.KG'])\
                        .stream()
        else:
            student_docs = db.collection('users')\
                        .where('role', '==', 'student')\
                        .where('grade', '==', teacher_grade)\
                        .where('board', '==', teacher_board)\
                        .stream()
    else:  # Admin selects grade and board
        selected_grade = request.args.get('grade', '')
        selected_board = request.args.get('board', '')

        if selected_grade and selected_board:
            student_docs = db.collection('users')\
                        .where('role', '==', 'student')\
                        .where('grade', '==', selected_grade)\
                        .where('board', '==', selected_board)\
                        .stream()
        else:
            student_docs = []

    # Convert student documents to list of dictionaries with complete information
    students = []
    for doc in student_docs:
        student_data = doc.to_dict()
        students.append({
            'username': doc.id,
            'name': student_data.get('name', doc.id),  # fallback to username if name not set
            'grade': student_data.get('grade', 'N/A'),
            'board': student_data.get('board', 'N/A'),
            'status': 'present'  # default status
        })

    # If form submitted to mark attendance
    if request.method == 'POST':
        current_date = datetime.now().strftime('%Y-%m-%d')
        # Process each student's attendance
        for key, value in request.form.items():
            if key.startswith('attendance_'):
                username = key.replace('attendance_', '')
                student_doc = db.collection('users').document(username).get()
                if student_doc.exists:
                    student_data = student_doc.to_dict()
                    db.collection('attendance').add({
    'student': username,
    'student_name': student_data.get('name', username),
    'grade': student_data.get('grade', 'N/A'),
    'board': student_data.get('board', 'N/A'),
    'date': datetime.now().strftime('%Y-%m-%d'),
    'status': value.capitalize()
})

        
        flash('Attendance marked successfully!', 'success')
        return redirect('/attendance')

    # Fetch unique grades and boards (convert all to str to prevent sorting errors)
    grades = sorted(set(str(doc.to_dict().get('grade', '')).strip() for doc in db.collection('users').where('role', '==', 'student').stream()))
    boards = sorted(set(str(doc.to_dict().get('board', '')).strip() for doc in db.collection('users').where('role', '==', 'student').stream()))

    # Fetch attendance records for today
    current_date = datetime.now().strftime('%Y-%m-%d')
    records = [doc.to_dict() for doc in db.collection('attendance')
               .where('date', '==', current_date)
               .order_by('date', direction=firestore.Query.DESCENDING)
               .stream()]
    
    # Update student status based on today's attendance
    for student in students:
        for record in records:
            if record.get('student') == student['username']:
                student['status'] = record.get('status', 'present')

    return render_template('attendance.html',
                           students=students,
                           records=records,
                           grades=grades,
                           boards=boards,
                           selected_grade=selected_grade,
                           selected_board=selected_board,
                           role=role)


@app.route('/assets', methods=['GET', 'POST'])
def manage_assets():
    if session.get('role') != 'admin':
        return redirect('/home')

    classrooms = []
    selected_class = request.args.get('classroom')
    selected_assets = []

    # Fetch unique classrooms from assets collection
    asset_docs = db.collection('assets').stream()
    seen = set()
    for doc in asset_docs:
        data = doc.to_dict()
        classroom = data.get('classroom')
        if classroom and classroom not in seen:
            classrooms.append(classroom)
            seen.add(classroom)

    if selected_class:
        selected_assets = [doc.to_dict() | {'id': doc.id} for doc in db.collection('assets').where('classroom', '==', selected_class).stream()]

    # Add or update asset
    if request.method == 'POST':
        classroom = request.form['classroom']
        product_name = request.form['product_name']
        quantity = int(request.form['quantity'])
        mrp = float(request.form['mrp'])

        db.collection('assets').add({
            'classroom': classroom,
            'product_name': product_name,
            'quantity': quantity,
            'mrp': mrp,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        return redirect(f'/assets?classroom={classroom}')

    return render_template('assets.html', classrooms=classrooms, selected_class=selected_class, assets=selected_assets)

# Route: Edit specific asset
@app.route('/edit_asset/<asset_id>', methods=['GET', 'POST'])
def edit_asset(asset_id):
    if session.get('role') != 'admin':
        return redirect('/home')

    doc_ref = db.collection('assets').document(asset_id)
    doc = doc_ref.get()
    if not doc.exists:
        return "Asset not found", 404

    asset = doc.to_dict()

    if request.method == 'POST':
        new_product_name = request.form['product_name']
        new_quantity = int(request.form['quantity'])
        new_mrp = float(request.form['mrp'])

        doc_ref.update({
            'product_name': new_product_name,
            'quantity': new_quantity,
            'mrp': new_mrp,
        })
        return redirect(f"/assets?classroom={asset['classroom']}")

    return render_template('edit_asset.html', asset=asset, asset_id=asset_id)

# Route: Add and view visitor logs
@app.route('/security', methods=['GET', 'POST'])
def security():
    if session.get('role') != 'admin':
        return redirect('/home')

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        purpose = request.form['purpose']
        in_time = request.form['in_time']
        out_time = request.form['out_time']
        date = request.form['date']

        db.collection('visitors').add({
            'name': name,
            'phone': phone,
            'purpose': purpose,
            'in_time': in_time,
            'out_time': out_time,
            'date': date,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        return redirect('/security')

    visitors = [doc.to_dict() | {'id': doc.id} for doc in db.collection('visitors').order_by('date', direction=firestore.Query.DESCENDING).stream()]
    return render_template('security.html', visitors=visitors)

# Route: Edit a visitor entry
@app.route('/edit_visitor/<visitor_id>', methods=['GET', 'POST'])
def edit_visitor(visitor_id):
    if session.get('role') != 'admin':
        return redirect('/home')

    doc_ref = db.collection('visitors').document(visitor_id)
    doc = doc_ref.get()
    if not doc.exists:
        return "Visitor not found", 404

    visitor = doc.to_dict()

    if request.method == 'POST':
        updated_data = {
            'name': request.form['name'],
            'phone': request.form['phone'],
            'purpose': request.form['purpose'],
            'in_time': request.form['in_time'],
            'out_time': request.form['out_time'],
            'date': request.form['date']
        }
        doc_ref.update(updated_data)
        return redirect('/security')

    return render_template('edit_visitor.html', visitor=visitor, visitor_id=visitor_id)

# Route: Library dashboard for admin
@app.route('/library', methods=['GET', 'POST'])
def library():
    if session.get('role') != 'admin':
        return redirect('/home')

    search_query = request.args.get('search', '').lower()
    books = []

    for doc in db.collection('library_books').stream():
        book = doc.to_dict()
        book['id'] = doc.id
        if search_query in book.get('book_name', '').lower():
            books.append(book)
        elif not search_query:
            books.append(book)

    total_books = sum(book.get('total_count', 0) for book in books)
    books_taken = sum(book.get('taken_count', 0) for book in books)

    if request.method == 'POST':
        book_name = request.form['book_name']
        total_count = int(request.form['total_count'])

        db.collection('library_books').add({
            'book_name': book_name,
            'total_count': total_count,
            'taken_count': 0,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        return redirect('/library')

    return render_template('library.html', books=books, total_books=total_books, books_taken=books_taken)

# Route: Book history per book
@app.route('/book_history/<book_id>')
def book_history(book_id):
    if session.get('role') != 'admin':
        return redirect('/home')

    history = [doc.to_dict() for doc in db.collection('library_history')
               .where('book_id', '==', book_id)
               .order_by('taken_date', direction=firestore.Query.DESCENDING).stream()]

    book = db.collection('library_books').document(book_id).get().to_dict()
    return render_template('book_history.html', history=history, book_name=book.get('book_name'))

# Route: Student borrows or returns a book
@app.route('/borrow_book/<book_id>', methods=['POST'])
def borrow_book(book_id):
    if session.get('role') != 'student':
        return redirect('/home')

    student = session['username']
    action = request.form['action']  # "borrow" or "return"

    book_ref = db.collection('library_books').document(book_id)
    book = book_ref.get().to_dict()
    if not book:
        return "Book not found", 404

    now = datetime.now().strftime('%Y-%m-%d')

    if action == 'borrow' and book['taken_count'] < book['total_count']:
        db.collection('library_history').add({
            'student': student,
            'book_id': book_id,
            'book_name': book['book_name'],
            'taken_date': now,
            'return_date': '',
            'status': 'Taken'
        })
        book_ref.update({'taken_count': firestore.Increment(1)})

    elif action == 'return':
        # Find last not-returned entry
        docs = db.collection('library_history').where('book_id', '==', book_id).where('student', '==', student).where('status', '==', 'Taken').stream()
        for doc in docs:
            db.collection('library_history').document(doc.id).update({
                'return_date': now,
                'status': 'Returned'
            })
            book_ref.update({'taken_count': firestore.Increment(-1)})
            break

    return redirect('/my_library')

# Route: Student views their library records
@app.route('/my_library')
def my_library():
    if session.get('role') != 'student':
        return redirect('/home')

    student = session['username']
    records = [doc.to_dict() for doc in db.collection('library_history')
               .where('student', '==', student)
               .order_by('taken_date', direction=firestore.Query.DESCENDING).stream()]

    return render_template('my_library.html', records=records)



# --- STUDENT: VIEW OWN ATTENDANCE ---
@app.route('/my_attendance')
def my_attendance():
    if 'username' not in session or session.get('role') != 'student':
        return redirect('/home')
    username = session['username']
    records = [doc.to_dict() for doc in db.collection('attendance').where('student', '==', username).stream()]
    # Monthly summary
    monthly_data = defaultdict(lambda: {'Present': 0, 'Absent': 0})
    for record in records:
        try:
            month = datetime.strptime(record['date'], "%d-%m-%Y").strftime('%B %Y')
            if record['status'] in ['Present', 'Absent']:
                monthly_data[month][record['status']] += 1
        except:
            continue
    monthly_percentages = {}
    for month, data in monthly_data.items():
        total = data['Present'] + data['Absent']
        if total > 0:
            monthly_percentages[month] = {
                'present_pct': round((data['Present'] / total) * 100, 2),
                'absent_pct': round((data['Absent'] / total) * 100, 2),
                'total_days': total
            }
    return render_template('my_attendance.html', records=records, monthly_percentages=monthly_percentages)

@app.route('/view_fees')
def view_fees():
    if session.get('role') != 'student':
        return redirect('/home')

    username = session['username']
    fee_doc = db.collection('fees').document(username).get()

    if not fee_doc.exists:
        flash('No fee record found.', 'danger')
        return redirect('/home')

    fee_data = fee_doc.to_dict()

    # Get all individual components (use 0 as default if missing)
    academic_fee = fee_data.get('academic_fee', 0)
    transport_fee = fee_data.get('transport_fee', 0)
    late_fee = fee_data.get('late_fee', 0)
    advance_fee = fee_data.get('advance_fee', 0)
    concession = fee_data.get('concession', 0)

    # Calculate transport_fee by distance if not manually set
    profile_doc = db.collection('student_profile').document(username).get()
    if profile_doc.exists:
        profile_data = profile_doc.to_dict()
        if 'lat' in profile_data and 'lon' in profile_data:
            lat = profile_data['lat']
            lon = profile_data['lon']
            distance = calculate_distance_km(SCHOOL_LAT, SCHOOL_LON, lat, lon)
            transport_fee = round(distance * 10000)

    # Payments
    payments = fee_data.get('payments', [])
    paid = sum(p.get('amount', 0) for p in payments)

    # Total fee is all components added together
    total = academic_fee + transport_fee + late_fee + advance_fee
    balance = total - paid - concession

    return render_template('view_fees.html',
                           total=total,
                           balance=balance,
                           paid=paid,
                           payments=payments,
                           academic_fee=academic_fee,
                           transport_fee=transport_fee,
                           late_fee=late_fee,
                           advance_fee=advance_fee,
                           concession=concession)


@app.route('/edit_fees', methods=['GET', 'POST'])
def edit_fees():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')

    def safe_float(val):
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    # Get all student IDs
    students = [doc.id for doc in db.collection('users').where('role', '==', 'student').stream()]
    selected_student = request.args.get('student')
    fee_details = None
    payments = []
    outstanding = 0
    concession = 0

    # Load fee details if a student is selected
    if selected_student:
        fee_doc = db.collection('fees').document(selected_student).get()
        if fee_doc.exists:
            fee_details = fee_doc.to_dict()
            fee_details['student'] = selected_student  # Pass to template
            payments = fee_details.get('payments', [])
            concession = safe_float(fee_details.get('concession', 0))
            academic_fee = safe_float(fee_details.get('academic_fee', 0))
            transport_fee = safe_float(fee_details.get('transport_fee', 0))
            late_fee = safe_float(fee_details.get('late_fee', 0))
            advance_fee = safe_float(fee_details.get('advance_fee', 0))
            paid = sum(safe_float(p.get('amount', 0)) for p in payments)
            total = academic_fee + transport_fee + late_fee + advance_fee
            outstanding = total - paid - concession

    # Handle form submission
    if request.method == 'POST':
        action = request.form.get('action')
        student = request.form.get('student')

        if not student:
            flash('Please select a student first.', 'error')
            return redirect('/edit_fees')

        # DELETE action
        if action == 'delete':
            try:
                fee_ref = db.collection('fees').document(student)
                if fee_ref.get().exists:
                    fee_ref.delete()
                    flash(f"Fee details for {student} deleted successfully.", "success")
                else:
                    flash("No fee record found to delete.", "warning")
            except Exception as e:
                flash(f"Error deleting fee document: {str(e)}", "error")
            return redirect('/add_fees')

        # SAVE or UPDATE action
        academic_fee = safe_float(request.form.get('academic_fee', 0))
        transport_fee = safe_float(request.form.get('transport_fee', 0))
        late_fee = safe_float(request.form.get('late_fee', 0))
        advance_fee = safe_float(request.form.get('advance_fee', 0))
        concession = safe_float(request.form.get('concession', 0))

        # Get existing payments
        fee_doc = db.collection('fees').document(student).get()
        payments = fee_doc.to_dict().get('payments', []) if fee_doc.exists else []

        # Add a payment if provided
        if request.form.get('payment_amount') and request.form.get('payment_date'):
            payments.append({
                'amount': safe_float(request.form['payment_amount']),
                'date': request.form['payment_date'],
                'method': request.form.get('payment_method', 'Unknown')
            })

        # Save fee data
        db.collection('fees').document(student).set({
            'academic_fee': academic_fee,
            'transport_fee': transport_fee,
            'late_fee': late_fee,
            'advance_fee': advance_fee,
            'concession': concession,
            'payments': payments
        })

        flash(f"Fee details for {student} saved successfully.", "success")
        return redirect(f'/edit_fees?student={student}')

    return render_template(
        'edit_fees.html',
        students=students,
        selected_student=selected_student,
        fee_details=fee_details,
        payments=payments,
        outstanding=outstanding,
        concession=concession
    )
from flask import send_file
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime

@app.route('/download_fee_receipt')
def download_fee_receipt():
    if session.get('role') != 'student':
        return redirect('/home')

    username = session['username']

    user_doc = db.collection('student_profile').document(username).get()
    fees_doc = db.collection('fees').document(username).get()

    if not user_doc.exists or not fees_doc.exists:
        return "Student record not found", 404

    user = user_doc.to_dict()
    fees = fees_doc.to_dict()

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Header
    p.setFont("Helvetica-Bold", 14)
    p.drawCentredString(width / 2, height - 50, "Advaita International School")
    p.setFont("Helvetica", 10)
    p.drawCentredString(width / 2, height - 65, "65/1A3A, Subash School Road, Andipalyam, Tirupur")
    p.drawString(40, height - 90, f"Fee Receipt for Session 2024-25")

    y = height - 120
    p.setFont("Helvetica", 10)
    p.drawString(40, y, f"Name: {user.get('name', username)}")
    y -= 15
    p.drawString(40, y, f"Class: {user.get('class', 'N/A')}")
    y -= 15
    p.drawString(40, y, f"Mobile No: {user.get('phone', 'N/A')}")

    y -= 30
    p.setFont("Helvetica-Bold", 10)
    p.drawString(40, y, "Particular")
    p.drawRightString(280, y, "Payable")
    p.drawRightString(400, y, "Paid")
    y -= 15
    p.line(40, y, 450, y)
    y -= 15
    p.setFont("Helvetica", 10)

    def draw_fee(label, amount):
        nonlocal y
        p.drawString(40, y, label)
        p.drawRightString(280, y, str(amount))
        p.drawRightString(400, y, str(amount))
        y -= 15

    draw_fee("Academic Fee", fees.get('academic_fee', 0))
    draw_fee("Transport Fee", fees.get('transport_fee', 0))
    draw_fee("Late Fee", fees.get('late_fee', 0))
    draw_fee("Advance Fee", fees.get('advance_fee', 0))

    y -= 10
    p.line(40, y, 450, y)
    y -= 20
    p.setFont("Helvetica-Bold", 10)
    total_paid = sum(pmt['amount'] for pmt in fees.get('payments', []))
    total = fees.get('academic_fee', 0) + fees.get('transport_fee', 0) + fees.get('late_fee', 0) + fees.get('advance_fee', 0)

    p.drawString(40, y, "Total")
    p.drawRightString(280, y, str(total))
    p.drawRightString(400, y, str(total_paid))

    y -= 40
    p.setFont("Helvetica", 9)
    p.drawString(40, y, f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    p.drawString(300, y, "Received by: Admin")

    p.showPage()
    p.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name='FeeReceipt.pdf', mimetype='application/pdf')

@app.route('/manage_home_locations')
def manage_home_locations():
    if session.get('role') not in ['admin', 'teacher', 'correspondent']:
        return redirect('/home')

    profiles = db.collection('student_profile').stream()
    students = []

    SCHOOL_LAT = 11.08756
    SCHOOL_LON = 77.32061

    for doc in profiles:
        data = doc.to_dict()
        if 'lat' in data and 'lon' in data:
            lat, lon = data['lat'], data['lon']
            distance = calculate_distance_km(SCHOOL_LAT, SCHOOL_LON, lat, lon)
            transport_fee = round(distance * 10000)

            students.append({
                'username': doc.id,
                'name': data.get('name', doc.id),
                'bus_no': data.get('bus_no', 'N/A'),
                'transport_fee': transport_fee,
                'lat': lat,
                'lon': lon
            })

    return render_template('manage_home_locations.html', students=students)


def generate_admission_number(student_class):
    from datetime import datetime

    # Year based on current academic year (e.g., 2025 -> 25-26)
    now = datetime.now()
    start_year = now.year % 100
    end_year = (now.year + 1) % 100
    academic_year = f"{start_year:02}-{end_year:02}"

    # Class format
    class_map = {
        "I": "1", "II": "2", "III": "3", "IV": "4", "V": "5",
        "VI": "6", "VII": "7", "VIII": "8"
    }
    grade_number = class_map.get(student_class.upper(), "0")
    grade_code = f"G{grade_number}"

    # Count how many students already have admission numbers in this academic year
    students = db.collection('student_profile').stream()
    count = sum(1 for s in students if s.to_dict().get('admission_no', '').startswith(academic_year))

    serial = f"{count + 1:03}"  # Total count across all classes

    return f"{academic_year}/AIST/{grade_code}/{serial}"

@app.route('/generate_admission_numbers')
def generate_admission_numbers():
    if session.get('role') != 'admin':
        return redirect('/home')

    students = list(db.collection('student_profile').stream())
    updated = 0

    for doc in students:
        data = doc.to_dict()
        if not data.get('admission_no'):
            student_class = data.get('class', '').upper()
            new_adm_no = generate_admission_number(student_class)
            db.collection('student_profile').document(doc.id).update({
                'admission_no': new_adm_no
            })
            updated += 1

    return f"{updated} admission numbers generated!"


@app.route('/delete_home_location', methods=['POST'])
def delete_home_location():
    if session.get('role') not in ['admin', 'teacher', 'correspondent']:
        return redirect('/home')

    username = request.form['username']
    student_ref = db.collection('student_profile').document(username)
    student_ref.update({
        'lat': firestore.DELETE_FIELD,
        'lon': firestore.DELETE_FIELD
    })

    flash('Home location deleted successfully.', 'success')
    return redirect('/manage_home_locations')

@app.route('/fees_history')
def fees_history():
    if session.get('role') not in ['admin']:
        return redirect('/home')

    # Fetch all students' fee records
    fees_docs = db.collection('fees').stream()
    history = []
    for doc in fees_docs:
        data = doc.to_dict()
        username = doc.id
        payments = data.get('payments', [])
        for payment in payments:
            history.append({
                'username': username,
                'amount': payment.get('amount'),
                'method': payment.get('method', 'Unknown'),
                'date': payment.get('date')
            })
    # Sort by date descending
    history.sort(key=lambda x: x['date'], reverse=True)
    return render_template('fees_history.html', history=history)

# --- ADD MESSAGE ---
@app.route('/add_message/<message_type>', methods=['GET', 'POST'])
def add_message(message_type):
    if session.get('role') != ['correspondent', 'teacher']:
        return redirect('/home')

    teacher_data = db.collection('users').document(session['username']).get().to_dict()
    if request.method == 'POST':
        title = request.form['title']  # Add title
        message = request.form['message']
        db.collection('messages').add({
            'sender': session['username'],
            'message_type': message_type,
            'title': title,  # Add title
            'message': message,
            'timestamp': datetime.now().strftime('%d-%m-%Y %H:%M'),
            'recipient_role': 'student',
            'grade': teacher_data['grade'],
            'board': teacher_data['board']
        })
        return redirect('/home')
    return render_template('add_message.html', message_type=message_type)


# --- VIEW MESSAGES ---
@app.route('/view/<message_type>')
def view_messages(message_type):
    if 'username' not in session:
        return redirect('/')

    user_data = db.collection('users').document(session['username']).get().to_dict()

    messages = []
    for doc in db.collection('messages') \
        .where('message_type', '==', message_type) \
        .where('recipient_role', '==', session['role']) \
        .where('grade', '==', user_data['grade']) \
        .where('board', '==', user_data['board']) \
        .order_by('timestamp', direction=firestore.Query.DESCENDING) \
        .stream():
        message = doc.to_dict()
        message['id'] = doc.id
        messages.append(message)

    # Add the header_title variable
    header_title = f"{message_type.capitalize()} Messages"

    return render_template('view_messages.html', messages=messages, message_type=message_type, header_title=header_title)

@app.route('/circular/<id>')
def circular_detail(id):
    if 'username' not in session or session['role'] != 'student':
        return redirect('/home')

    username = session['username']

    # Fetch from the correct collection: 'circulars'
    circular_ref = db.collection('circulars').document(id)
    circular = circular_ref.get().to_dict()

    if not circular:
        return "Circular not found", 404

    # Update the read_by field
    if 'read_by' not in circular:
        circular['read_by'] = []

    if username not in circular['read_by']:
        circular['read_by'].append(username)
        circular_ref.update({'read_by': circular['read_by']})

    return render_template('circular_detail.html', circular=circular)

@app.route('/add_menu', methods=['GET', 'POST'])
def add_menu():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    if request.method == 'POST':
        for day in days:
            date = request.form.get(f'{day}_date', '')
            morning = request.form.get(f'{day}_morning_snacks', '')
            lunch = request.form.get(f'{day}_lunch', '')
            evening = request.form.get(f'{day}_evening_snacks', '')
            if date:
                db.collection('menus').document(date).set({
                    'date': date,
                    'morning_snacks': morning,
                    'lunch': lunch,
                    'evening_snacks': evening
                })
        return redirect('/view_menu')
    return render_template('add_menu.html')

# ...existing code...
@app.route('/view_menu', methods=['GET'])
def view_menu():
    if session.get('role') != 'student':
        return redirect('/home')

    today = datetime.today().date()
    weekday = today.weekday()  # Monday=0, Sunday=6

    # Find the Monday of the current week
    monday = today - timedelta(days=weekday)
    week_dates = [(monday + timedelta(days=i)) for i in range(6)]  # Mon-Sat

    # If today is Sunday, allow next week's menu
    if weekday == 6:
        next_monday = monday + timedelta(days=7)
        week_dates = [(next_monday + timedelta(days=i)) for i in range(6)]  # Next Mon-Sat

    # Prepare day names
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

    # Fetch menus for these dates and pair with day names
    weekly_menus = []
    for i, d in enumerate(week_dates):
        date_str = d.strftime('%Y-%m-%d')
        doc = db.collection('menus').document(date_str).get()
        if doc.exists:
            weekly_menus.append((day_names[i], doc.to_dict()))

    return render_template('view_menu.html', weekly_menus=weekly_menus)
# ...existing code...
@app.route('/pay_nutriment', methods=['GET', 'POST'])
def pay_nutriment():
    if 'username' not in session or session['role'] != 'student':
        return redirect('/home')
    
    if request.method == 'POST':
        student = session['username']
        morning_snacks = 35 if 'morning_snacks' in request.form else 0
        lunch = 80 if 'lunch' in request.form else 0
        evening_snacks = 35 if 'evening_snacks' in request.form else 0
        total = morning_snacks + lunch + evening_snacks
        date = datetime.now().strftime('%Y-%m-%d')
        
        db.collection('nutriments').add({
            'student': student,
            'morning_snacks': morning_snacks,
            'lunch': lunch,
            'evening_snacks': evening_snacks,
            'total': total,
            'date': date
        })
        return redirect('/home')

    return render_template('pay_nutriment.html')

@app.route('/view_nutriment_orders')
def view_nutriment_orders():
    if session.get('role') != 'admin':
        return redirect('/home')

    from collections import defaultdict
    from datetime import datetime, timedelta

    # Fetch all nutriment orders
    orders = [doc.to_dict() for doc in db.collection('nutriments').order_by('date', direction=firestore.Query.DESCENDING).stream()]

    # Total orders per day
    orders_per_day = defaultdict(int)
    for order in orders:
        orders_per_day[order.get('date', 'N/A')] += 1

    # Payment and cancellation details
    total_paid = sum(o.get('payment_amount', 0) for o in orders if o.get('payment_status') == 'paid' and not o.get('cancelled'))
    total_pending = sum(o.get('payment_amount', 0) for o in orders if o.get('payment_status') == 'pending' and not o.get('cancelled'))
    total_cancelled = sum(1 for o in orders if o.get('cancelled'))

    # Snacks/lunch stats for previous day, week, month
    today = datetime.today().date()
    prev_day = (today - timedelta(days=1)).isoformat()
    prev_week = (today - timedelta(days=7)).isoformat()
    prev_month = (today - timedelta(days=30)).isoformat()

    snacks_prev_day = len([o for o in orders if o.get('order_type') == 'snacks' and o.get('date') == prev_day and not o.get('cancelled')])
    lunch_prev_day = len([o for o in orders if o.get('order_type') == 'lunch' and o.get('date') == prev_day and not o.get('cancelled')])

    snacks_prev_week = len([o for o in orders if o.get('order_type') == 'snacks' and o.get('date', '') >= prev_week and not o.get('cancelled')])
    lunch_prev_week = len([o for o in orders if o.get('order_type') == 'lunch' and o.get('date', '') >= prev_week and not o.get('cancelled')])

    snacks_prev_month = len([o for o in orders if o.get('order_type') == 'snacks' and o.get('date', '') >= prev_month and not o.get('cancelled')])
    lunch_prev_month = len([o for o in orders if o.get('order_type') == 'lunch' and o.get('date', '') >= prev_month and not o.get('cancelled')])

    return render_template(
        'view_nutriment_orders.html',
        orders=orders,
        orders_per_day=orders_per_day,
        total_paid=total_paid,
        total_pending=total_pending,
        total_cancelled=total_cancelled,
        snacks_prev_day=snacks_prev_day,
        lunch_prev_day=lunch_prev_day,
        snacks_prev_week=snacks_prev_week,
        lunch_prev_week=lunch_prev_week,
        snacks_prev_month=snacks_prev_month,
        lunch_prev_month=lunch_prev_month
    )

@app.route('/add_info/<category>', methods=['GET', 'POST'])
def add_info(category):
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')
    
    user = db.collection('users').document(session['username']).get().to_dict()
    teacher_grade = user.get('grade')
    teacher_board = user.get('board')

    # Filter students matching teacher's grade and board
    students = [doc.id for doc in db.collection('users')
                .where('role', '==', 'student')
                .where('grade', '==', teacher_grade)
                .where('board', '==', teacher_board)
                .stream()]
    
    if request.method == 'POST':
        student = request.form['student']
        content = request.form['content']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        # Add info with teacher's grade & board
        db.collection('student_info').add({
            'student': student,
            'category': category,
            'content': content,
            'timestamp': timestamp,
            'grade': teacher_grade,
            'board': teacher_board
        })
        
        return redirect('/home')
    
    return render_template('add_info.html', category=category, students=students)


@app.route('/view_info/<category>')
def view_info(category):
    if session.get('role') != 'student':
        return redirect('/home')

    student = session['username']
    student_data = db.collection('users').document(student).get().to_dict()

    info = [doc.to_dict() for doc in db.collection('student_info')
            .where('student', '==', student)
            .where('category', '==', category)
            .where('grade', '==', student_data['grade'])
            .where('board', '==', student_data['board'])
            .order_by('timestamp', direction=firestore.Query.DESCENDING).stream()]

    return render_template('view_info.html', category=category, info=info)

@app.route('/add_results', methods=['GET', 'POST'])
def add_results():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')
    
    students = [doc.id for doc in db.collection('users').where('role', '==', 'student').stream()]
    
    if request.method == 'POST':
        student = request.form['student']
        exam_name = request.form['exam_name']
        grade = request.form['grade']
        remarks = request.form.get('remarks', '')
        subjects = []
        # Assume up to 8 subjects for flexibility
        for i in range(1, 9):
            subject = request.form.get(f'subject_{i}')
            marks = request.form.get(f'marks_{i}')
            if subject and marks:
                subjects.append({'subject': subject, 'marks': marks})
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        db.collection('results').add({
            'student': student,
            'exam_name': exam_name,
            'grade': grade,
            'subjects': subjects,
            'remarks': remarks,
            'timestamp': timestamp
        })
        return redirect('/home')
    
    return render_template('add_results.html', students=students)

@app.route('/view_results')
def view_results():
    if session.get('role') != 'student':
        return redirect('/home')
    student = session['username']
    results = [doc.to_dict() for doc in db.collection('results')
               .where('student', '==', student)
               .order_by('timestamp', direction=firestore.Query.DESCENDING).stream()]
    return render_template('view_results.html', results=results)

@app.route('/add_timetable', methods=['GET', 'POST'])
def add_timetable():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')

    # Fetch unique grades & boards safely
    grades = sorted(
        {str(doc.to_dict().get('grade'))
         for doc in db.collection('users').where('role', '==', 'student').stream()
         if doc.to_dict().get('grade') is not None}
    )

    boards = sorted(
        {doc.to_dict().get('board')
         for doc in db.collection('users').where('role', '==', 'student').stream()
         if doc.to_dict().get('board')}
    )

    if request.method == 'POST':
        grade = request.form['grade']
        board = request.form['board']

        timetable = {}
        for day in ['mon', 'tue', 'wed', 'thu', 'fri']:
            periods = [
                request.form.get(f'{day}_period{n}') for n in range(1, 9)
            ]
            timetable[day] = periods

        db.collection('class_timetables').document(f"{grade}_{board}").set({
            'grade': grade,
            'board': board,
            'timetable': timetable,
            'timestamp': datetime.now().strftime('%d-%m-%Y %H:%M')
        })

        return redirect('/view_timetable')

    return render_template('add_timetable.html', grades=grades, boards=boards)

@app.route('/view_timetable')
def view_timetable():
    if session.get('role') != 'student':
        return redirect('/home')
    user = db.collection('users').document(session['username']).get().to_dict()
    grade = user.get('grade')
    board = user.get('board')
    doc = db.collection('class_timetables').document(f"{grade}_{board}").get()
    timetable = doc.to_dict()['timetable'] if doc.exists else {}
    return render_template('view_timetable.html', timetable=timetable, grade=grade, board=board)

@app.route('/add_extra_timetable', methods=['GET', 'POST'])
def add_extra_timetable():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')
    grades = sorted(set(doc.to_dict().get('grade') for doc in db.collection('users').where('role', '==', 'student').stream()))
    boards = sorted(set(doc.to_dict().get('board') for doc in db.collection('users').where('role', '==', 'student').stream()))
    if request.method == 'POST':
        grade = request.form['grade']
        board = request.form['board']
        timetable = {}
        for day in ['mon', 'tue', 'wed', 'thu', 'fri']:
            activities = [request.form.get(f'{day}_activity{n}') for n in range(1, 5)]
            timetable[day] = activities
        db.collection('extra_timetables').document(f"{grade}_{board}").set({
            'grade': grade,
            'board': board,
            'timetable': timetable,
            'timestamp': datetime.now().strftime('%d-%m-%y %H:%M')
        })
        return redirect('/view_extra_timetable')
    return render_template('add_extra_timetable.html', grades=grades, boards=boards)

@app.route('/view_extra_timetable')
def view_extra_timetable():
    if session.get('role') != 'student':
        return redirect('/home')
    user = db.collection('users').document(session['username']).get().to_dict()
    grade = user.get('grade')
    board = user.get('board')
    doc = db.collection('extra_timetables').document(f"{grade}_{board}").get()
    timetable = doc.to_dict()['timetable'] if doc.exists else {}
    return render_template('view_extra_timetable.html', timetable=timetable, grade=grade, board=board)

@app.route('/add_exam_timetable', methods=['GET', 'POST'])
def add_exam_timetable():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')

    grades = sorted(
        {str(doc.to_dict().get('grade'))
         for doc in db.collection('users').where('role', '==', 'student').stream()
         if doc.to_dict().get('grade') is not None}
    )

    boards = sorted(
        {doc.to_dict().get('board')
         for doc in db.collection('users').where('role', '==', 'student').stream()
         if doc.to_dict().get('board')}
    )

    if request.method == 'POST':
        grade = request.form['grade']
        board = request.form['board']

        exam_timetable = []
        for i in range(1, 8):
            date = request.form.get(f'exam_date_{i}')
            subject = request.form.get(f'exam_subject_{i}')
            if date and subject:
                exam_timetable.append({'date': date, 'subject': subject})

        db.collection('exam_timetables').document(f"{grade}_{board}").set({
            'grade': grade,
            'board': board,
            'exam_timetable': exam_timetable,
            'timestamp': datetime.now().strftime('%d-%m-%Y %H:%M')
        })

        return redirect('/view_exam_timetable')

    return render_template('add_exam_timetable.html', grades=grades, boards=boards)

@app.route('/view_exam_timetable')
def view_exam_timetable():
    if session.get('role') != 'student':
        return redirect('/home')
    user = db.collection('users').document(session['username']).get().to_dict()
    grade = user.get('grade')
    board = user.get('board')
    doc = db.collection('exam_timetables').document(f"{grade}_{board}").get()
    exam_timetable = doc.to_dict()['exam_timetable'] if doc.exists else []
    return render_template('view_exam_timetable.html', exam_timetable=exam_timetable, grade=grade, board=board)

# --- EDIT PROFILE ---
@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'username' not in session:
        return redirect('/')

    username = session['username']
    user_ref = db.collection('users').document(username)
    user_data = user_ref.get().to_dict()

    if request.method == 'POST':
        new_password = request.form.get('password', user_data.get('password'))
        new_board = request.form.get('board', user_data.get('board'))
        new_grade = request.form.get('grade', user_data.get('grade'))
        admission_no = request.form.get('admission_no', user_data.get('admission_no'))

        user_ref.update({
            'password': new_password,
            'board': new_board,
            'grade': int(new_grade),
            'admission_no': admission_no
        })
        return redirect('/view_profile')

    return render_template('edit_profile.html', user_data=user_data)


# --- VIEW PROFILE ---
@app.route('/view_profile')
def view_profile():
    username = session.get('username')
    user_data = db.collection('users').document(username).get().to_dict()
    user_username = user_data['username']  # or user_data.username depending on your structure

    return render_template('view_profile.html',
                           user_username=user_username,
                           user_data=user_data)

# --- APPLY LEAVE (STUDENT) ---
@app.route('/apply_leave', methods=['GET', 'POST'])
def apply_leave():
    if 'username' not in session or session['role'] != 'student':
        return redirect('/home')

    username = session['username']
    user_data = db.collection('users').document(username).get().to_dict()
    grade = user_data.get('grade')

    if request.method == 'POST':
        leave_date = request.form['leave_date']
        reason = request.form['reason']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

        # Add leave request to Firestore
        db.collection('leaves').add({
            'student': username,
            'grade': grade,  # Include grade
            'leave_date': leave_date,
            'reason': reason,
            'status': 'Pending',  # Default status
            'timestamp': timestamp
        })
        return redirect('/apply_leave')

    # Fetch leave requests for the student
    leaves = [doc.to_dict() for doc in db.collection('leaves').where('student', '==', username).order_by('timestamp', direction=firestore.Query.DESCENDING).stream()]
    return render_template('apply_leave.html', leaves=leaves)

# --- VIEW LEAVES (TEACHER/ADMIN) ---
@app.route('/view_leaves', methods=['GET', 'POST'])
def view_leaves():
    if 'username' not in session or session['role'] not in ['teacher', 'admin']:
        return redirect('/home')

    # Fetch all leave requests
    leaves = [doc.to_dict() | {'id': doc.id} for doc in db.collection('leaves').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()]

    if request.method == 'POST':
        leave_id = request.form['leave_id']
        action = request.form['action']  # Accept or Reject

        # Update leave status in Firestore
        db.collection('leaves').document(leave_id).update({
            'status': 'Accepted' if action == 'accept' else 'Rejected'
        })
        return redirect('/view_leaves')

    return render_template('view_leaves.html', leaves=leaves)

# --- STUDENT: SEND MESSAGE ---
@app.route('/send_message', methods=['GET', 'POST'])
def send_message():
    if 'username' not in session:
        return redirect('/home')

    username = session['username']
    role = session['role']

    recipients = []
    grades = []
    boards = []

    if role == 'student':
        # Students can send messages to teachers, admins, and correspondents
        recipients = [
            {'id': doc.id, 'name': doc.to_dict().get('name', doc.id)}  # Use doc.id as fallback if name is missing
            for doc in db.collection('users')
            .where('role', 'in', ['teacher', 'admin', 'correspondent'])
            .stream()
        ]
    else:
        # Admins, teachers, and correspondents can select a grade and board to fetch students
        grades = db.collection('users').where('role', '==', 'student').select('grade').stream()
        boards = db.collection('users').where('role', '==', 'student').select('board').stream()
        grades = sorted(set(doc.to_dict().get('grade') for doc in grades))
        boards = sorted(set(doc.to_dict().get('board') for doc in boards))

        if request.method == 'POST' and 'grade' in request.form and 'board' in request.form:
            grade = request.form['grade']
            board = request.form['board']
            recipients = [
                {'id': doc.id, 'name': doc.to_dict().get('name', doc.id)}  # Use doc.id as fallback if name is missing
                for doc in db.collection('users')
                .where('role', '==', 'student')
                .where('grade', '==', int(grade))
                .where('board', '==', board)
                .stream()
            ]

    if request.method == 'POST' and 'recipient' in request.form:
        recipient = request.form['recipient']
        message = request.form['message']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

        # Save the message to Firestore
        db.collection('chats').add({
            'sender': username,
            'recipient': recipient,
            'message': message,
            'timestamp': timestamp
        })
        return redirect('/view_chat')

    return render_template('send_message.html', role=role, recipients=recipients, grades=grades, boards=boards)

# --- TEACHER/ADMIN: VIEW MESSAGES ---
@app.route('/view_chat', methods=['GET', 'POST'])
def view_chat():
    if 'username' not in session:
        return redirect('/home')

    username = session['username']

    # Fetch messages where the user is either the sender or the recipient
    messages = [doc.to_dict() for doc in db.collection('chats')
                .where('sender', '==', username)
                .stream()] + \
               [doc.to_dict() for doc in db.collection('chats')
                .where('recipient', '==', username)
                .stream()]

    # Sort messages by timestamp
    messages.sort(key=lambda x: x['timestamp'])

    return render_template('view_chat.html', messages=messages, username=username)

# --- TEACHER/ADMIN: SEND MESSAGE TO STUDENT ---
@app.route('/send_message_to_student', methods=['GET', 'POST'])
def send_message_to_student():
    if 'username' not in session or session['role'] not in ['teacher', 'admin', 'correspondent']:
        return redirect('/home')

    username = session['username']
    role = session['role']

    # Fetch the teacher/admin/correspondent's grade and board if applicable
    user_data = db.collection('users').document(username).get().to_dict()
    grade = user_data.get('grade')
    board = user_data.get('board')

    # Fetch students matching the grade and board
    students = [doc.id for doc in db.collection('users')
                .where('role', '==', 'student')
                .where('grade', '==', grade)
                .where('board', '==', board)
                .stream()]

    if request.method == 'POST':
        student_id = request.form['student_id']  # Selected student ID
        message = request.form['message']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

        # Send message to the selected student
        db.collection('chats').add({
            'sender': username,
            'recipient': student_id,
            'message': message,
            'timestamp': timestamp
        })

        return redirect('/send_message_to_student')

    # Fetch messages where the user is the sender or recipient
    messages = [doc.to_dict() for doc in db.collection('chats')
                .where('sender', '==', username)
                .stream()] + \
               [doc.to_dict() for doc in db.collection('chats')
                .where('recipient', '==', username)
                .stream()]

    # Sort messages by timestamp
    messages.sort(key=lambda x: x['timestamp'])

    return render_template('send_message_to_student.html', messages=messages, students=students, username=username)

# --- TEACHER: CREATE QUIZ ---
@app.route('/create_quiz', methods=['GET', 'POST'])
def create_quiz():
    if 'username' not in session or session['role'] != 'teacher':
        return redirect('/home')

    if request.method == 'POST':
        question = request.form['question']
        options = {
            'A': request.form['option_a'],
            'B': request.form['option_b'],
            'C': request.form['option_c'],
            'D': request.form['option_d']
        }
        correct_option = request.form['correct_option']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

        db.collection('quizzes').add({
            'question': question,
            'options': options,
            'correct_option': correct_option,
            'timestamp': timestamp
        })
        return redirect('/create_quiz')

    return render_template('create_quiz.html')

# --- STUDENT: ANSWER QUIZ ---
@app.route('/answer_quiz', methods=['GET', 'POST'])
def answer_quiz():
    if 'username' not in session or session['role'] != 'student':
        return redirect('/home')

    quizzes = [doc.to_dict() | {'id': doc.id} for doc in db.collection('quizzes').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()]
    
    # Prepare quiz data for the template
    quiz_data = [
        {
            'id': quiz['id'],
            'question': quiz['question'],
            'options': quiz['options'],
            'answer': quiz['correct_option']
        }
        for quiz in quizzes
    ]

    return render_template('answer_quiz.html', quiz_data=quiz_data)

@app.route('/start_live', methods=['GET', 'POST'])
def start_live():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')

    if request.method == 'POST':
        live_url = request.form['live_url']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

        # Save live stream details to Firestore
        db.collection('live_stream').document('current').set({
            'url': live_url,
            'status': 'active',
            'started_by': session['username'],
            'timestamp': timestamp
        })
        return redirect('/home')

    return render_template('start_live.html')


@app.route('/watch_live')
def watch_live():
    if session.get('role') != 'student':
        return redirect('/home')

    # Fetch live stream details from Firestore
    live_stream = db.collection('live_stream').document('current').get().to_dict()

    if not live_stream or live_stream.get('status') != 'active':
        return render_template('watch_live.html', live_stream=None)

    return render_template('watch_live.html', live_stream=live_stream)
@app.route('/submit_feedback', methods=['GET', 'POST'])
def submit_feedback():
    if session.get('role') != 'student':
        return redirect('/home')

    if request.method == 'POST':
        feedback = request.form['feedback']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        db.collection('feedback').add({
            'student': session['username'],
            'feedback': feedback,
            'timestamp': timestamp
        })
        return redirect('/home')

    return render_template('submit_feedback.html')


@app.route('/view_feedback')
def view_feedback():
    if session.get('role') not in ['admin', 'teacher','correspondent']:
        return redirect('/home')

    feedbacks = [doc.to_dict() for doc in db.collection('feedback').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()]
    return render_template('view_feedback.html', feedbacks=feedbacks)

@app.route('/add_admission', methods=['GET', 'POST'])
def add_admission():
    if request.method == 'POST':
        student_name = request.form.get('student_name')
        parent_name = request.form.get('parent_name')
        contact = request.form.get('contact')
        stage = request.form.get('stage')
        grade = request.form.get('grade')
        board = request.form.get('board')
        remarks = request.form.get('remarks')
        admission_date = request.form.get('admission_date')

        # Validate the form data
        if not all([student_name, parent_name, contact, stage, grade, board, admission_date]):
            return "All fields except remarks are required!", 400

        # Save the admission data to the database (example using Firestore)
        admission_ref = db.collection('admissions').add({
            'student_name': student_name,
            'parent_name': parent_name,
            'contact': contact,
            'stage': stage,
            'grade': grade,
            'board': board,
            'remarks': remarks,
            'admission_date': admission_date,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        # --- Automatically create user if stage is Confirmation ---
        if stage == "Confirmation":
            # Use student_name or contact as username (ensure uniqueness as needed)
            username = student_name.replace(" ", "_").lower()
            # Check if user already exists
            user_ref = db.collection('users').document(username)
            if not user_ref.get().exists:
                user_ref.set({
                    'password': '123456',  # Set a default password, can be changed later
                    'role': 'student',
                    'board': board,
                    'grade': grade
                })

        return redirect('/add_admission')


    # --- Filtering logic ---
    search = request.args.get('search', '').strip().lower()
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')

    admissions_query = db.collection('admissions')
    admissions = admissions_query.stream()
    admissions_list = []
    for doc in admissions:
        data = doc.to_dict()
        data['id'] = doc.id

        # Filter by search
        if search:
            if not (
                search in data.get('student_name', '').lower() or
                search in data.get('parent_name', '').lower() or
                search in data.get('grade', '').lower() or
                search in data.get('board', '').lower()
            ):
                continue

        # Filter by date range
        ad_date = data.get('admission_date', '')
        if from_date and ad_date < from_date:
            continue
        if to_date and ad_date > to_date:
            continue

        admissions_list.append(data)

    # Prepare summary data for the summary table and chart
    summary = {}
    for admission in admissions_list:
        stage = admission.get('stage', 'Unknown')
        summary[stage] = summary.get(stage, 0) + 1
    summary_combined = summary.items()
    summary_labels = list(summary.keys())
    summary_values = list(summary.values())

    return render_template(
        'add_admission.html',
        admissions_list=admissions_list,
        summary_combined=summary_combined,
        summary_labels=summary_labels,
        summary_values=summary_values
    )

@app.route('/edit_admission/<admission_id>', methods=['GET', 'POST'])
def edit_admission(admission_id):
    doc_ref = db.collection('admissions').document(admission_id)
    doc = doc_ref.get()
    if not doc.exists:
        return "Admission not found", 404
    admission = doc.to_dict()

    if request.method == 'POST':
        # Update fields from form
        updated_data = {
            'student_name': request.form.get('student_name'),
            'parent_name': request.form.get('parent_name'),
            'contact': request.form.get('contact'),
            'stage': request.form.get('stage'),
            'grade': request.form.get('grade'),
            'board': request.form.get('board'),
            'remarks': request.form.get('remarks'),
            'admission_date': request.form.get('admission_date'),
        }
        doc_ref.update(updated_data)
        return redirect('/add_admission')

    return render_template('edit_admission.html', admission=admission, admission_id=admission_id)

@app.route('/delete_admission/<admission_id>', methods=['POST'])
def delete_admission(admission_id):
    db.collection('admissions').document(admission_id).delete()
    return redirect('/add_admission')

@app.route('/add_circular', methods=['GET', 'POST'])
def add_circular():
    if session.get('role') not in ['correspondent', 'teacher', 'admin']:
        return redirect('/home')

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        timestamp = datetime.now().strftime('%d-%m-%Y %H:%M')
        grade = request.form['grade']
        board = request.form['board']

        db.collection('circulars').add({
            'title': title,
            'content': content,
            'timestamp': timestamp,
            'grade': grade,
            'board': board,
            'read_by': []
        })

        students = [doc.id for doc in db.collection('users')
                    .where('role', '==', 'student')
                    .where('grade', '==', grade)
                    .where('board', '==', board)
                    .stream()]

        for student in students:
            db.collection('notifications').add({
                'recipient': student,
                'message': f"New circular: {title}",
                'timestamp': timestamp,
                'read': False
            })
            user_doc = db.collection('users').document(student).get()
            fcm_token = user_doc.to_dict().get('fcm_token')
            if fcm_token:
                send_push_notification(fcm_token, "New Circular", title)

        return redirect('/add_circular')

    # Only render the form for GET requests
    return render_template('add_circular.html')

@app.route('/add_homework', methods=['GET', 'POST'])
def add_homework():
    if session.get('role') not in ['correspondent', 'teacher', 'admin']:
        return redirect('/home')

    if request.method == 'POST':
        title = request.form['title']
        subject = request.form['subject']
        description = request.form['description']
        due_date = request.form['due_date']
        timestamp = datetime.now().strftime('%d-%m-%Y %H:%M')

        user_data = db.collection('users').document(session['username']).get().to_dict()
        grade = user_data.get('grade')
        board = user_data.get('board')

        db.collection('homework').add({
            'title': title,
            'subject': subject,
            'description': description,
            'due_date': due_date,
            'timestamp': timestamp,
            'grade': grade,
            'board': board,
            'read_by': []
        })

        # Only define and use students here, inside POST
        students = [doc.id for doc in db.collection('users')
                    .where('role', '==', 'student')
                    .where('grade', '==', grade)
                    .where('board', '==', board)
                    .stream()]

        for student in students:
            db.collection('notifications').add({
                'recipient': student,
                'message': f"New homework: {title}",
                'timestamp': timestamp,
                'read': False
            })
            user_doc = db.collection('users').document(student).get()
            fcm_token = user_doc.to_dict().get('fcm_token')
            if fcm_token:
                send_push_notification(fcm_token, "New Homework", title)

        return redirect('/add_homework')

    # For GET, just render the form
    return render_template('add_homework.html')

@app.route('/homework/<id>')
def homework_detail(id):
    if 'username' not in session or session['role'] != 'student':
        return redirect('/home')

    username = session['username']
    homework_ref = db.collection('homework').document(id)
    homework = homework_ref.get().to_dict()

    if not homework:
        return "Homework not found", 404

    # Update the read_by field
    if 'read_by' not in homework:
        homework['read_by'] = []
    if username not in homework['read_by']:
        homework['read_by'].append(username)
        homework_ref.update({'read_by': homework['read_by']})

    return render_template('homework_detail.html', homework=homework)

@app.route('/admin_read_status/<id>', methods=['GET'])
def admin_read_status(id):
    if session.get('role') != 'admin':
        return redirect('/home')

    # Fetch the specific document by ID
    circular_ref = db.collection('messages').document(id)
    doc = circular_ref.get()

    if not doc.exists:
        return "Circular not found", 404

    circular = doc.to_dict()

    # Add the `read_by` field if it doesn't exist
    circular['read_by'] = circular.get('read_by', [])

    return render_template('admin_read_status.html', circular=circular)


@app.route('/teacher_read_status/<id>', methods=['GET'])
def teacher_read_status(id):
    if session.get('role') not in ['correspondent', 'teacher', 'admin']:
        return redirect('/home')

    # Get the teacher's grade and board
    teacher_data = db.collection('users').document(session['username']).get().to_dict()
    grade = teacher_data.get('grade', 'N/A')  # Default to 'N/A' if grade is missing
    board = teacher_data.get('board', 'N/A')  # Default to 'N/A' if board is missing

    # Fetch the specific document by ID
    circular_ref = db.collection('messages').document(id)
    doc = circular_ref.get()

    if not doc.exists:
        return "Circular not found", 404

    circular = doc.to_dict()


    # Add the `read_by` field if it doesn't exist
    circular['read_by'] = circular.get('read_by', [])

    # Pass the `type` variable to the template
    return render_template('teacher_read_status.html', circular=circular, grade=grade, type='circular')

@app.route('/admin_view_all')
def admin_view_all():
    if session.get('role') != 'admin':
        return redirect('/home')

    # Fetch all circulars
    circulars = [doc.to_dict() | {'id': doc.id} for doc in db.collection('circulars')
                 .order_by('timestamp', direction=firestore.Query.DESCENDING).stream()]

    # Fetch all homework
    homework = [doc.to_dict() | {'id': doc.id} for doc in db.collection('homework')
                .order_by('timestamp', direction=firestore.Query.DESCENDING).stream()]

    return render_template('admin_view_all.html', circulars=circulars, homework=homework)

@app.route('/manage_students', methods=['GET', 'POST'])
def manage_students():
    if session.get('role') not in ['admin', 'correspondent']:
        return redirect('/home')

    if request.method == 'POST':
        student_id = request.form.get('student_id')
        if student_id:
            db.collection('users').document(student_id).delete()
            db.collection('student_profile').document(student_id).delete()
            flash('Student removed successfully!', 'success')
            return redirect('/manage_students')

    selected_grade = request.args.get('grade', '')
    selected_board = request.args.get('board', '')

    # Only get users with role == 'student'
    user_docs = db.collection('users').where('role', '==', 'student').stream()

    students = []
    grades = set()
    boards = set()

    for user_doc in user_docs:
        user_data = user_doc.to_dict()
        username = user_doc.id
        grade = str(user_data.get('grade', '')).strip()
        board = str(user_data.get('board', '')).strip()

        grades.add(grade)
        boards.add(board)

        if selected_grade and grade != selected_grade:
            continue
        if selected_board and board != selected_board:
            continue

        profile_ref = db.collection('student_profile').document(username)
        profile_doc = profile_ref.get()
        profile_data = profile_doc.to_dict() if profile_doc.exists else {}

        student = {
            'id': username,
            'grade': grade,
            'board': board,
            'father_name': profile_data.get('father_name', ''),
            'mother_name': profile_data.get('mother_name', ''),
            'phone': profile_data.get('phone', ''),
            'address': profile_data.get('address', ''),
            'student_photo': profile_data.get('student_photo', ''),
            'father_photo': profile_data.get('father_photo', '')
        }

        students.append(student)

    grades = sorted(grades)
    boards = sorted(boards)

    return render_template(
        'manage_students.html',
        students=students,
        grades=grades,
        boards=boards,
        selected_grade=selected_grade,
        selected_board=selected_board
    )

@app.route('/download_students')
def download_students():

    selected_grade = request.args.get('grade', '')
    selected_board = request.args.get('board', '')

    user_docs = db.collection('users').where('role', '==', 'student').stream()

    data = []

    for user_doc in user_docs:
        user_data = user_doc.to_dict()
        username = user_doc.id
        grade = str(user_data.get('grade', '')).strip()
        board = str(user_data.get('board', '')).strip()

        # Apply grade and board filters
        if selected_grade and grade != selected_grade:
            continue
        if selected_board and board != selected_board:
            continue

        profile_doc = db.collection('student_profile').document(username).get()
        profile_data = profile_doc.to_dict() if profile_doc.exists else {}

        data.append({
            "Username": username,
            "Grade": grade,
            "Board": board,
            "Father's Name": profile_data.get('father_name', ''),
            "Mother's Name": profile_data.get('mother_name', ''),
            "Phone": profile_data.get('phone', ''),
            "Address": profile_data.get('address', ''),
            "Student Photo URL": profile_data.get('student_photo', ''),
            "Father Photo URL": profile_data.get('father_photo', '')
        })

    # Convert to Excel
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Students')

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="students.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/add_student_details', methods=['GET', 'POST'])
def add_student_details():
    if session.get('role') != 'admin':
        return redirect('/home')

    student_id = request.args.get('student')
    students = [doc.id for doc in db.collection('users').where('role', '==', 'student').stream()]

    existing_details = None
    if student_id:
        doc = db.collection('student_profile').document(student_id).get()
        if doc.exists:
            existing_details = doc.to_dict()

    if request.method == 'POST':
        student = request.form.get('student') if not student_id else student_id

        # Handle file uploads
        student_photo_file = request.files.get('student_photo')
        father_photo_file = request.files.get('father_photo')
        mother_photo_file = request.files.get('mother_photo')

        student_photo_url = existing_details.get('student_photo') if existing_details else ''
        father_photo_url = existing_details.get('father_photo') if existing_details else ''
        mother_photo_url = existing_details.get('mother_photo') if existing_details else ''

        def upload_to_storage(file_obj, filename):
            blob = bucket.blob(f'student_photos/{filename}')
            blob.upload_from_file(file_obj, content_type=file_obj.content_type)
            blob.make_public()
            return blob.public_url

        # Upload student photo if provided
        if student_photo_file and student_photo_file.filename:
            filename = f"{student}_student_{uuid.uuid4().hex}.jpg"
            student_photo_url = upload_to_storage(student_photo_file, filename)

        # Upload father photo if provided
        if father_photo_file and father_photo_file.filename:
            filename = f"{student}_father_{uuid.uuid4().hex}.jpg"
            father_photo_url = upload_to_storage(father_photo_file, filename)

        # Upload mother photo if provided
        if mother_photo_file and mother_photo_file.filename:
            filename = f"{student}_mother_{uuid.uuid4().hex}.jpg"
            mother_photo_url = upload_to_storage(mother_photo_file, filename)

        # Build student details dictionary
        student_details = {
            # Personal Information
            'first_name': request.form.get('first_name', ''),
            'middle_name': request.form.get('middle_name', ''),
            'last_name': request.form.get('last_name', ''),
            'dob': request.form.get('dob', ''),
            'phone': request.form.get('phone', ''),
            'gender': request.form.get('gender', ''),
            'nationality': request.form.get('nationality', ''),
            'religion': request.form.get('religion', ''),
            'address': request.form.get('address', ''),
            'city': request.form.get('city', ''),
            'state': request.form.get('state', ''),
            'pincode': request.form.get('pincode', ''),
            'aadhaar_student': request.form.get('aadhaar_student', ''),
            'email_student': request.form.get('email_student', ''),
            # Academic Information
            'admission_number': existing_details.get('admission_number') if existing_details else generate_admission_number(request.form.get('class', '')),
            'admission_date': request.form.get('admission_date', ''),
            'roll_number': request.form.get('roll_number', ''),
            'class': request.form.get('class', ''),
            'section': request.form.get('section', ''),
            'language': request.form.get('language', ''),
            'previous_school': request.form.get('previous_school', ''),
            'previous_board': request.form.get('previous_board', ''),
            'previous_class': request.form.get('previous_class', ''),
            'previous_performance': request.form.get('previous_performance', ''),
            # Contact Information
            'email': request.form.get('email', ''),
            'mobile': request.form.get('mobile', ''),
            # Guardian Information
            'father_name': request.form.get('father_name', ''),
            'father_contact': request.form.get('father_contact', ''),
            'father_aadhaar': request.form.get('father_aadhaar', ''),
            'father_email': request.form.get('father_email', ''),
            'mother_name': request.form.get('mother_name', ''),
            'mother_contact': request.form.get('mother_contact', ''),
            'mother_aadhaar': request.form.get('mother_aadhaar', ''),
            'mother_email': request.form.get('mother_email', ''),
            # Other Information
            'medical_info': request.form.get('medical_info', ''),
            'disability_info': request.form.get('disability_info', ''),
            'sibling_info': request.form.get('sibling_info', ''),
            # Uploaded Image URLs
            'student_photo': student_photo_url,
            'father_photo': father_photo_url,
            'mother_photo': mother_photo_url,
        }

        db.collection('student_profile').document(student).set(student_details)
        return redirect('/manage_students')

    return render_template(
        'add_student_details.html',
        students=students,
        selected_student=student_id,
        existing_details=existing_details
    )

@app.route('/view_student_details')
def view_student_details():
    if 'username' not in session or session.get('role') != 'student':
        return redirect('/home')

    username = session['username']

    # Fetch user data from Firestore
    user_ref = db.collection('users').document(username)
    user_data = user_ref.get().to_dict()

    if not user_data:
        return "User data not found!", 404

    grade = user_data.get('grade', 'N/A')  # Fetch grade from Firestore
    board = user_data.get('board', 'N/A')  # Fetch board from Firestore
    school_name = "Advaita"  # Replace with your school name or fetch dynamically

    # Fetch student profile details
    details_doc = db.collection('student_profile').document(username).get()

    if not details_doc.exists:
        return "No details found."

    details = details_doc.to_dict()
    details['grade'] = grade  # Add grade to details
    details['board'] = board  # Add board to details

    return render_template('view_student_details.html', details=details, school_name=school_name, username=username)

@app.route('/edit_credentials', methods=['GET', 'POST'])
def edit_credentials():
    if 'username' not in session:
        return redirect('/')

    username = session['username']
    user_ref = db.collection('users').document(username)
    user_data = user_ref.get().to_dict()

    if request.method == 'POST':
        # Step 1: Verify current password
        if 'current_password' in request.form:
            current_password = request.form['current_password']
            if current_password != user_data.get('password'):
                return "Incorrect current password!", 400
            session['verified'] = True
            return redirect('/edit_credentials')

        # Step 2: Update username or password
        if session.get('verified'):
            new_username = request.form.get('new_username', username)
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            if new_password and new_password != confirm_password:
                return "Passwords do not match!", 400

            # Update username and/or password
            updates = {}
            if new_username != username:
                updates['username'] = new_username
                session['username'] = new_username
            if new_password:
                updates['password'] = new_password

            if updates:
                user_ref.update(updates)
                return redirect('/home')

    return render_template('edit_credentials.html', username=username, verified=session.get('verified', False))


@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/view_school_contacts')
def view_school_contacts():
    return render_template('view_school_contacts.html')

@app.route('/reader', methods=['GET'])
def reader():
    if 'username' not in session:
        return redirect('/')

    # Fetch all unique grades and boards for dropdowns
    grades = sorted(set(
        str(doc.to_dict().get('grade'))
        for doc in db.collection('users').where('role', '==', 'student').stream()
        if doc.to_dict().get('grade')
    ))
    boards = sorted(set(
        doc.to_dict().get('board')
        for doc in db.collection('users').where('role', '==', 'student').stream()
        if doc.to_dict().get('board')
    ))

    selected_grade = request.args.get('grade', '')
    selected_board = request.args.get('board', '')

@app.route('/edit_menu', methods=['GET', 'POST'])
def edit_menu():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')

    date = request.args.get('date')
    existing_menu = None

    if date:
        doc = db.collection('menus').document(date).get()
        if doc.exists:
            existing_menu = doc.to_dict()

    if request.method == 'POST':
        date = request.form.get('date')
        morning = request.form.get('morning_snacks', '')
        lunch = request.form.get('lunch', '')
        evening = request.form.get('evening_snacks', '')

        db.collection('menus').document(date).set({
            'date': date,
            'morning_snacks': morning,
            'lunch': lunch,
            'evening_snacks': evening
        })
        return redirect('/view_menu')

    return render_template('edit_menu.html', menu=existing_menu, date=date)

@app.route('/admission_stage/<stage>')
def admission_stage(stage):
    students = [
        doc.to_dict() | {'id': doc.id}
        for doc in db.collection('admissions').where('stage', '==', stage).stream()
    ]
    # Pass session role and username to template
    role = session.get('role')
    username = session.get('username')
    return render_template('admission_stage.html', stage=stage, students=students, role=role, username=username)

@app.route('/admission_detail/<admission_id>')
def admission_detail(admission_id):
    doc = db.collection('admissions').document(admission_id).get()
    if not doc.exists:
        return "Admission not found", 404
    admission = doc.to_dict()
    return render_template('admission_detail.html', admission=admission)

@app.route('/add_nutriment_order', methods=['GET', 'POST'])
def add_nutriment_order():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')
    students = [doc.id for doc in db.collection('users').where('role', '==', 'student').stream()]
    if request.method == 'POST':
        student = request.form['student']
        order_date = request.form['order_date']
        order_type = request.form['order_type']  # 'snacks' or 'lunch'
        payment_status = request.form['payment_status']
        payment_amount = float(request.form.get('payment_amount', 0))
        cancelled = request.form.get('cancelled', 'no') == 'yes'
        db.collection('nutriments').add({
            'student': student,
            'order_date': order_date,
            'order_type': order_type,
            'payment_status': payment_status,
            'payment_amount': payment_amount,
            'cancelled': cancelled,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        return redirect('/view_nutriment_orders')
    return render_template('add_nutriment_order.html', students=students)

@app.route('/manage_nutriment', methods=['GET', 'POST'])
def manage_nutriment():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')

    
    students = [doc.to_dict() | {'username': doc.id} for doc in db.collection('users').where('role', '==', 'student').stream()]
    grades = sorted(set(str(doc.get('grade', '')) for doc in students))


    # Handle add nutriment POST
    message = None
    if request.method == 'POST':
        student_username = request.form.get('student_username')
        morning_snacks = request.form.get('morning_snacks') == 'yes'
        lunch = request.form.get('lunch') == 'yes'
        date = datetime.now().strftime('%Y-%m-%d')

        # Get student grade
        student_doc = db.collection('users').document(student_username).get()
        student_data = student_doc.to_dict()
        grade = student_data.get('grade', 'N/A')

        db.collection('nutriments').add({
            'student': student_username,
            'grade': grade,
            'morning_snacks': 35 if morning_snacks else 0,
            'lunch': 80 if lunch else 0,
            'date': date,
            'total': (35 if morning_snacks else 0) + (80 if lunch else 0)
        })
        message = f"Nutriment added for {student_username}."

    # Fetch all nutriment records for management
    nutriments = [doc.to_dict() | {'id': doc.id} for doc in db.collection('nutriments').order_by('date', direction=firestore.Query.DESCENDING).stream()]

    return render_template(
        'manage_nutriment.html',
        students=students,
        grades=grades,
        nutriments=nutriments,
        message=message
    )


@app.route('/add_fees', methods=['GET', 'POST'])
def add_fees():
    if session.get('role') not in ['admin', 'teacher']:
        return redirect('/home')

    students = [doc.id for doc in db.collection('users').where('role', '==', 'student').stream()]
    message = None

    if request.method == 'POST':
        student = request.form['student']
        # Check if fee entry already exists
        fee_doc = db.collection('fees').document(student).get()
        if fee_doc.exists:
            message = f"Fee entry already exists for {student}. Please edit or delete it from the Edit Fee section."
        else:
            total = float(request.form['total'])
            concession = float(request.form.get('concession', 0))
            db.collection('fees').document(student).set({
                'total': total,
                'concession': concession,
                'payments': []
            }, merge=True)
            return redirect('/edit_fees?student=' + student)

    return render_template('add_fees.html', students=students, message=message)

@app.route('/manage_teachers', methods=['GET', 'POST'])
def manage_teachers():
    if session.get('role') not in ['admin', 'correspondent']:
        return redirect('/home')

    # Fetch all teachers
    teachers = [doc.to_dict() | {'id': doc.id} for doc in db.collection('users').where('role', '==', 'teacher').stream()]

    if request.method == 'POST':
        # Remove a teacher
        teacher_id = request.form['teacher_id']
        db.collection('users').document(teacher_id).delete()
        return redirect('/manage_teachers')

    return render_template('manage_teachers.html', teachers=teachers)

@app.route('/edit_teacher/<teacher_id>', methods=['GET', 'POST'])
def edit_teacher(teacher_id):
    if session.get('role') not in ['admin', 'correspondent']:
        return redirect('/home')

    teacher_ref = db.collection('users').document(teacher_id)
    teacher = teacher_ref.get().to_dict()
    if not teacher or teacher.get('role') != 'teacher':
        return "Teacher not found", 404

    if request.method == 'POST':
        new_board = request.form.get('board', teacher.get('board'))
        new_grade = request.form.get('grade', teacher.get('grade'))
        teacher_ref.update({
            'board': new_board,
            'grade': new_grade
        })
        return redirect('/manage_teachers')

    boards = ['CBSE', 'Montessori']
    grades = ['KG', 'Pre.KG', 'Jr.KG', 'Sr.KG'] + [str(i) for i in range(1, 13)]  # <-- Add KG levels

    return render_template('edit_teacher.html', teacher=teacher, teacher_id=teacher_id, boards=boards, grades=grades)


@app.route('/transport')
def transport():
    if session.get('role') != 'student':
        return redirect('/home')

    student = session['username']
    user_doc = db.collection('users').document(student).get().to_dict()
    home_location = user_doc.get('home_location', {})

    # 🔁 Get fingerprint IN/OUT status
    status_doc = db.collection('bus_fingerprint').document(student).get()
    status = status_doc.to_dict().get('status') if status_doc.exists else 'OUT'

    return render_template(

        'transport.html',
        home_lat=home_location.get('latitude'),
        home_lon=home_location.get('longitude'),
        fingerprint_status=status
    )



@app.route('/location')
def gps_location():
    try:
        # Retrieve the latest location from Firestore (if stored there)
        doc = db.collection("gps").document("current").get()
        if doc.exists:
            data = doc.to_dict()
            return {"lat": data.get("latitude"), "lon": data.get("longitude")}
    except Exception as e:
        print("GPS fetch error:", e)
    return {"lat": None, "lon": None}

@app.route('/mark_home_location', methods=['GET', 'POST'])
def mark_home_location():
    if session.get('role') not in ['admin', 'correspondent']:
        return redirect('/home')

    students = [doc.id for doc in db.collection('users').where('role', '==', 'student').stream()]

    if request.method == 'POST':
        student = request.form['student']
        lat = float(request.form['latitude'])
        lon = float(request.form['longitude'])

        # Save lat/lon
        db.collection('student_profile').document(student).set({
            'lat': lat,
            'lon': lon
        }, merge=True)

        # Distance & Fee Calculation
        SCHOOL_LAT = 11.08756
        SCHOOL_LON = 77.32061
        distance = calculate_distance_km(SCHOOL_LAT, SCHOOL_LON, lat, lon)
        fee = round(distance * 10000)

        # Update fees
        fee_ref = db.collection('fees').document(student)
        fee_doc = fee_ref.get()
        payments = fee_doc.to_dict().get('payments', []) if fee_doc.exists else []

        fee_ref.set({
            'total': fee,
            'concession': 0,
            'payments': payments
        }, merge=True)

        flash(f"🏠 Location saved. Transport Fee: ₹{fee}", 'success')
        return redirect('/home')

    return render_template('mark_home_location.html', students=students)

@app.route('/bus_status')
def bus_status():
    if 'username' not in session:
        return redirect('/login')

    user = session['username']
    role = session['role']

    if role not in ['admin', 'teacher', 'correspondent']:
        return "Access denied", 403

    # Get all student bus statuses
    docs = db.collection('bus_fingerprint').stream()
    bus_data = {doc.id: doc.to_dict() for doc in docs}

    return render_template('bus_status.html', user=user, bus_data=bus_data)

@app.route('/my_bus_status')
def my_bus_status():
    if 'username' not in session:
        return redirect('/login')

    username = session['username']
    role = session['role']

    # Only students can view this page
    if role != 'student':
        return "Access denied", 403

    # Get their fingerprint bus status
    doc = db.collection('bus_fingerprint').document(username).get()
    status = doc.to_dict() if doc.exists else None

    return render_template('my_bus_status.html', username=username, status=status)


# --- CODE CHANGE ---
student_grades = ['Pre.KG', 'Jr.KG', 'Sr.KG'] + [str(i) for i in range(1, 13)]
teacher_grades = ['KG'] + [str(i) for i in range(1, 13)]

@app.route('/edit_admission', methods=['GET'])
def list_admissions_for_edit():
    # List all admissions with edit links
    admissions = [
        doc.to_dict() | {'id': doc.id}
        for doc in db.collection('admissions').stream()
    ]
    return render_template('list_edit_admissions.html', admissions=admissions)

@app.route('/edit_student/<student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    if session.get('role') != 'admin':
        return redirect('/home')

    user_ref = db.collection('users').document(student_id)
    user = user_ref.get().to_dict()
    if not user or user.get('role') != 'student':
        return "Student not found", 404

    grades = ['Pre.KG', 'Jr.KG', 'Sr.KG'] + [str(i) for i in range(1, 13)]

    if request.method == 'POST':
        new_password = request.form.get('password', user.get('password'))
        new_grade = request.form.get('grade', user.get('grade'))
        user_ref.update({
            'password': new_password,
            'grade': new_grade
        })
        return redirect('/manage_students')

    return render_template('edit_student.html', student=user, student_id=student_id, grades=grades)

@app.route('/transports')
def transports_map():
    if session.get('role') not in ['admin', 'teacher', 'correspondent']:
        return redirect('/home')

    # Get bus (vehicle) location from Firestore
    gps_doc = db.collection('gps').document('current').get()
    bus_lat = gps_doc.to_dict().get('latitude') if gps_doc.exists else None
    bus_lon = gps_doc.to_dict().get('longitude') if gps_doc.exists else None

    # Get all students with bus_fingerprint status "IN"
    students = []
    for doc in db.collection('bus_fingerprint').stream():
        data = doc.to_dict()
        if data.get('status') == 'IN':
            username = doc.id
            user_doc = db.collection('users').document(username).get()
            user_data = user_doc.to_dict()
            home_location = user_data.get('home_location', {})
            if home_location and 'latitude' in home_location and 'longitude' in home_location:
                students.append({
                    'username': username,
                    'lat': home_location['latitude'],
                    'lon': home_location['longitude']
                })

    return render_template(
        'transports.html',
        bus_lat=bus_lat,
        bus_lon=bus_lon,
        students=students
    )

@app.route('/register_token', methods=['POST'])
def register_token():
    if not request.json or 'username' not in request.json or 'fcm_token' not in request.json:
        return {'status': 'error', 'message': 'Missing data'}, 400

    username = request.json['username']

    fcm_token = request.json['fcm_token']

    try:
        db.collection('users').document(username).update({
            'fcm_token': fcm_token
        })
        return {'status': 'success', 'message': 'Token registered'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500
    
@app.route('/view_usage')
def view_usage():
    from datetime import datetime

    # Get current month and year
    now = datetime.now()
    current_month = now.strftime('%Y-%m')

    # Fetch usage logs for current month
    logs = [
        doc.to_dict()
        for doc in db.collection('usage_logs')
        .order_by('visited_at', direction=firestore.Query.DESCENDING)
        .stream()
    ]
    # Filter logs for current month
    logs = [log for log in logs if log['visited_at'].startswith(current_month)]

    # Prepare unique users who visited home page
    users_visited = {}
    for log in logs:
        users_visited[log['username']] = log['visited_at']

    student_users = [{'username': u, 'last_visit': t} for u, t in users_visited.items() if db.collection('users').document(u).get().to_dict().get('role') == 'student']
    teacher_users = [{'username': u, 'last_visit': t} for u, t in users_visited.items() if db.collection('users').document(u).get().to_dict().get('role') == 'teacher']

    student_count = len(student_users)
    teacher_count = len(teacher_users)

    return render_template(
        'view_usage.html',
        student_count=student_count,
        teacher_count=teacher_count,
        student_users=student_users,
        teacher_users=teacher_users
    )

@app.route('/view_circulars')
def view_circulars():
    if 'username' not in session or session.get('role') != 'student':
        return redirect('/home')

    user = db.collection('users').document(session['username']).get().to_dict()
    grade = user.get('grade')
    board = user.get('board')

    # Fetch circulars for the student's grade and board
    circulars = [
        doc.to_dict() | {'id': doc.id}
        for doc in db.collection('circulars')
        .where('grade', '==', grade)
        .where('board', '==', board)
        .order_by('timestamp', direction=firestore.Query.DESCENDING)
        .stream()
    ]
    return render_template('view_circulars.html', circulars=circulars)

@app.route('/view_homeworks')
def view_homeworks():
    if 'username' not in session or session.get('role') != 'student':
        return redirect('/home')

    user = db.collection('users').document(session['username']).get().to_dict()
    grade = user.get('grade')
    board = user.get('board')

    # Fetch homeworks for the student's grade and board
    homeworks = [
        doc.to_dict() | {'id': doc.id}
        for doc in db.collection('homework')
        .where('grade', '==', grade)
        .where('board', '==', board)
        .order_by('timestamp', direction=firestore.Query.DESCENDING)
        .stream()
    ]
    return render_template('view_homeworks.html', homeworks=homeworks)

@app.route('/manage_homework', methods=['GET', 'POST'])
def manage_homework():
    if session.get('role') not in ['teacher', 'correspondent', 'admin']:
        return redirect('/home')

    user_data = db.collection('users').document(session['username']).get().to_dict()
    grade = user_data.get('grade')
    board = user_data.get('board')

    # Admin can see all, teachers/correspondents see only their grade/board
    if session.get('role') == 'admin':
        homeworks = [
            doc.to_dict() | {'id': doc.id}
            for doc in db.collection('homework')
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .stream()
        ]
    else:
        homeworks = [
            doc.to_dict() | {'id': doc.id}
            for doc in db.collection('homework')
            .where('grade', '==', grade)
            .where('board', '==', board)
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .stream()
        ]

    # Handle delete
    if request.method == 'POST':
        if 'delete' in request.form:
            homework_id = request.form.get('homework_id')
            if homework_id:
                db.collection('homework').document(homework_id).delete()
                return redirect('/manage_homework')

    return render_template('manage_homework.html', homeworks=homeworks)
    

@app.route('/edit_homework/<homework_id>', methods=['GET', 'POST'])
def edit_homework(homework_id):
    if session.get('role') not in ['teacher', 'correspondent', 'admin']:
        return redirect('/home')

    doc_ref = db.collection('homework').document(homework_id)
    doc = doc_ref.get()
    if not doc.exists:
        return "Homework not found", 404
    homework = doc.to_dict()

    if request.method == 'POST':
        title = request.form['title']
        subject = request.form['subject']
        description = request.form['description']
        due_date = request.form['due_date']
        doc_ref.update({
            'title': title,
            'subject': subject,
            'description': description,
            'due_date': due_date
        })
        return redirect('/manage_homework')

    return render_template('edit_homework.html', homework=homework, homework_id=homework_id)

@app.route('/manage_circulars', methods=['GET', 'POST'])
def manage_circulars():
    if session.get('role') not in ['teacher', 'correspondent', 'admin']:
        return redirect('/home')

    # Admin can see all, teachers/correspondents see only their grade/board
    user_data = db.collection('users').document(session['username']).get().to_dict()
    grade = user_data.get('grade')
    board = user_data.get('board')

    if session.get('role') == 'admin':
        circulars = [
            doc.to_dict() | {'id': doc.id}
            for doc in db.collection('circulars')
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .stream()
        ]
    else:
        circulars = [
            doc.to_dict() | {'id': doc.id}
            for doc in db.collection('circulars')
            .where('grade', '==', grade)
            .where('board', '==', board)
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .stream()
        ]

    # Handle delete
    if request.method == 'POST':
        if 'delete' in request.form:
            circular_id = request.form.get('circular_id')
            if circular_id:
                db.collection('circulars').document(circular_id).delete()
                return redirect('/manage_circulars')

    return render_template('manage_circulars.html', circulars=circulars)


@app.route('/edit_circular/<circular_id>', methods=['GET', 'POST'])
def edit_circular(circular_id):
    if session.get('role') not in ['teacher', 'correspondent', 'admin']:
        return redirect('/home')

    doc_ref = db.collection('circulars').document(circular_id)
    doc = doc_ref.get()
    if not doc.exists:
        return "Circular not found", 404
    circular = doc.to_dict()

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        doc_ref.update({
            'title': title,
            'content': content
        })
        return redirect('/manage_circulars')

    return render_template('edit_circular.html', circular=circular, circular_id=circular_id)

@app.route('/upload_students_excel', methods=['GET', 'POST'])
def upload_students_excel():
    if session.get('role') != 'admin':
        return redirect('/home')

    if request.method == 'POST':
        file = request.files.get('excel_file')
        if file and file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
            for _, row in df.iterrows():
                username = str(row.get('Username')).strip()
                password = str(row.get('Password')).strip() or 'default123'
                board = str(row.get('Board')).strip()
                grade = str(row.get('Grade')).strip()

                # Create user in Firestore
                db.collection('users').document(username).set({
                    'password': password,
                    'role': 'student',
                    'board': board,
                    'grade': grade
                })

                # Optional: Add student profile data
                profile_fields = ['father_name', 'mother_name', 'phone', 'address']
                profile_data = {field: row.get(field, '') for field in profile_fields}
                db.collection('student_profile').document(username).set(profile_data, merge=True)

            flash('Students uploaded successfully!', 'success')
            return redirect('/manage_students')

        flash('Invalid file. Please upload a valid Excel file.', 'danger')
        return redirect('/upload_students_excel')

    return render_template('upload_students_excel.html')


print("Starting Flask server...")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

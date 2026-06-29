from collections import defaultdict
import datetime
import io
import json
import math
import os
import random
import re
import secrets
import traceback
import uuid

from bson import ObjectId
import cloudinary
from flask import Blueprint, abort, current_app, flash, jsonify, make_response, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from app import ALLOWED_EXTENSIONS, google
from app.extensions import mongo
from datetime import datetime, timedelta
from xhtml2pdf import pisa
from flask import Response
import dns.resolver  # Ku dar kor faylkaaga

from app.modal import Account, Category, Saving, SavingTransaction, Transaction, User, UserRole


bp = Blueprint('main', __name__)

#------------------------------------------
#---- Function: 1 | Func Allowed Files  ---
#------------------------------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
 
def create_guest_session(mongo):
    if not session.get("guest_token"):

        token = secrets.token_hex(24)

        session["guest_token"] = token

        mongo.db.sessions.insert_one({
            "session_token": token,
            "user_id": None,   # guest
            "ip": request.remote_addr,
            "device": request.user_agent.string,
            "created_at": datetime.utcnow(),
            "expires_at": None,
            "routes": []   # store visited pages
        })



# 1. Index route: Wuxuu soo bandhigayaa page-ka iyo data-da projects-ka
from bson import ObjectId

@bp.route("/")
def index():

    slides = [
        {
            "title": "Manage Your Expenses",
            "description": "Track income, expenses, savings and budgets easily.",
            "image": "images/slider1.jpg"
        },
        {
            "title": "Control Your Money",
            "description": "Know where every dollar goes.",
            "image": "images/slider2.jpg"
        },
        {
            "title": "Save More",
            "description": "Create savings goals and monitor your progress.",
            "image": "images/slider3.jpg"
        }
    ]

    features = [
        {
            "icon": "fa-wallet",
            "title": "Accounts",
            "text": "Manage multiple bank and cash accounts."
        },
        {
            "icon": "fa-money-bill-wave",
            "title": "Expenses",
            "text": "Record every expense instantly."
        },
        {
            "icon": "fa-piggy-bank",
            "title": "Savings",
            "text": "Track savings goals."
        },
        {
            "icon": "fa-chart-line",
            "title": "Reports",
            "text": "Powerful financial reports."
        }
    ]

    # Total Users (excluding Super Admin)
    total_users = mongo.db.users.count_documents({
        "role": {
            "$in": ["admin", "user"]
        },
        "status": True
    })

    # Total Admins
    total_admins = mongo.db.users.count_documents({
        "role": "admin",
        "status": True
    })

    # Total Normal Users
    total_members = mongo.db.users.count_documents({
        "role": "user",
        "status": True
    })

    # Latest Registered Users
    latest_users = list(
        mongo.db.users.find(
            {
                "role": {
                    "$in": ["admin", "user"]
                }
            },
            {
                "password": 0
            }
        )
        .sort("created_at", -1)
        .limit(8)
    )

    return render_template(
        "frontend/home/index.html",
        slides=slides,
        features=features,

        total_users=total_users,
        total_admins=total_admins,
        total_members=total_members,
        latest_users=latest_users,

        login_url="https://maareye.vercel.app/login",
        app_url="https://appsgeyser.io/19942993/Maareeye Expense"
    )





@bp.route('/check-username', methods=['POST'])
def check_username():
    username = request.json.get('username')
    user = mongo.db.users.find_one({"username": username})
    
    if user:
        # Soo saar 3 magac oo kale
        suggestions = [f"{username}{random.randint(10,99)}" for _ in range(3)]
        return jsonify({"taken": True, "suggestions": suggestions})
    
    return jsonify({"taken": False})


def is_valid_email_domain(email):
    try:
        domain = email.split('@')[1]
        # Waxaan hubineynaa in domain-ku leeyahay MX record (Mail Exchange)
        records = dns.resolver.resolve(domain, 'MX')
        return True if records else False
    except:
        return False

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('password_confirmation')
        
         # 1. Hubi in format-ku sax yahay (Regex)
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("Fadlan geli email sax ah!", "danger")
            return redirect(url_for('main.register'))

        # 2. Hubi in domain-ku dhab ahaan u jiro (MX check)
        if not is_valid_email_domain(email):
            flash("Email-kan domain-kiisu ma jiro (Email does not exist)!", "danger")
            return redirect(url_for('main.register'))
        
        # 3. Hubi haddii user-ku horey u jiray
        if mongo.db.users.find_one({"email": email}):
            flash("Email-kan horey ayaa loo isticmaalay!", "danger")
            return redirect(url_for('main.register'))

        # 4. Hubi username-ka inuu database-ka ku jiro mar kale
        if mongo.db.users.find_one({"username": username}):
            flash("Username-kan horey ayaa loo qaatay, fadlan mid kale dooro!", "danger")
            return redirect(url_for('main.register'))
        
        # 5. Hubi xoogga password-ka (8 xaraf, 1 xaraf weyn, 1 lambar, 1 calaamad)
        if not re.match(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$", password):
            flash("Password-ku waa inuu ka koobnaadaa ugu yaraan 8 xaraf, lambar, iyo calaamad!", "danger")
            return redirect(url_for('main.register'))
        
        # 6. Hubi haddii passwords-ku isku mid yihiin
        if password != confirm_password:
            flash("Passwords-ka isma laha!", "danger")
            return redirect(url_for('main.register'))

        # 7. Role Logic
        user_count = mongo.db.users.count_documents({})
        role = UserRole.superadmin.value if user_count == 0 else UserRole.admin.value

        # 8. Save
        new_user = {
            "fullname": fullname,
            "username": username,
            "email": email,
            "password": generate_password_hash(password),
            "role": role,
            "status": True,
            "created_at": datetime.utcnow()
        }
        mongo.db.users.insert_one(new_user)
        
        flash("Diiwaangelinta way guulaysatay!", "success")
        return redirect(url_for('main.login'))

    # Wadada saxda ah ee faylkaaga:
    return render_template("backend/auth/auth-register.html")


@bp.route('/login', methods=['GET', 'POST'])
def login():
    # Haddi uu user-ku horay u soo galay, u dir dashboard-ka
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remembr_me') else False

        # 1. Ka raadi user-ka database-ka
        user_data = mongo.db.users.find_one({"email": email})

        # 2. Hubi haddii password-ku sax yahay
        if user_data and check_password_hash(user_data.get('password'), password):
            # Samee User object
            user = User(user_data) 
            
            # 3. Login u samee
            login_user(user, remember=remember)
            
            flash("Si guul leh ayaad u gashay dashboard-ka!", "success")
            return redirect(url_for('main.dashboard')) 
        else:
            flash("Email ama Password khaldan!", "danger")
            # Waxaan u beddelay 'auth.login' si uu ugu laabto isla boggaas
            return redirect(url_for('main.login')) 

    return render_template("backend/auth/auth-login.html")


@bp.app_errorhandler(403)
def forbidden(error):
    return render_template('frontend/errors/403.html'), 403

@bp.route("/login/google")
def login_google():
    redirect_uri = url_for("main.google_callback", _external=True)
    print("REDIRECT URI:", redirect_uri)
    return google.authorize_redirect(redirect_uri)



@bp.route("/google/callback")
def google_callback():
    token = google.authorize_access_token()
    user_info = token.get("userinfo")
    email = user_info.get("email")

    # 1. Check if the user exists in your database
    raw_user = mongo.db.users.find_one({"email": email})

    # 2. If the user does not exist, block the login
    if not raw_user:
        flash("You do not have an account. Please register first.", "danger")
        return redirect(url_for("main.login"))

    # 3. Optional: Check if the account was registered via Google previously
    # This prevents users from trying to log in with Google to an email 
    # that was registered via standard email/password (if you prefer).
    if raw_user.get("auth_provider") != "google":
        # You could also choose to update their profile here instead of blocking
        pass

    # 4. Proceed with Login
    user_obj = User(raw_user)
    login_user(user_obj, remember=True)
    
    flash("Successfully logged in with Google!", "success")
    return redirect(url_for("main.dashboard"))



@bp.route("/dashboard")
@login_required
def dashboard():

    # =========================
    # ROLE PROTECTION
    # =========================
    if current_user.role not in ["superadmin", "admin"]:
        abort(403)

    # =========================
    # USER FILTER LOGIC
    # =========================
    try:
        user_id = ObjectId(current_user.id)
    except:
        user_id = current_user.id

    if current_user.role == "superadmin":
        user_filter = {}
    else:
        user_filter = {"user_id": user_id}

    # =========================
    # DATA
    # =========================
    accounts = list(mongo.db.accounts.find({**user_filter, "status": True}))
    transactions = list(mongo.db.transactions.find(user_filter))
    savings = list(mongo.db.savings.find(user_filter))
    categories = list(mongo.db.categories.find({**user_filter, "status": True}))

    # =========================
    # SAFE FLOAT
    # =========================
    def safe_float(v):
        try:
            return float(v)
        except:
            return 0.0

    # =========================
    # CATEGORY CHART (FIXED LOGIC)
    # =========================
    category_totals = defaultdict(float)

    
    for t in transactions:
        # ❌ ONLY EXPENSE
        if t.get("transaction_type") != "expense":
            continue

        amount = float(t.get("amount", 0))
        category = t.get("category")

        if not category:
            category = "Unknown"

        category_totals[category] += amount


    # REMOVE ZERO VALUES (IMPORTANT FIX)
    category_totals = {
        k: v for k, v in category_totals.items() if v > 0
    }

    category_labels = list(category_totals.keys())
    category_values = list(category_totals.values())

    # =========================
    # TOTALS
    # =========================
    total_balance = sum(safe_float(a.get("balance")) for a in accounts)

    total_income = sum(
        safe_float(t.get("amount"))
        for t in transactions
        if t.get("transaction_type") == "income"
    )

    total_expense = sum(
        safe_float(t.get("amount"))
        for t in transactions
        if t.get("transaction_type") == "expense"
    )

    total_savings = sum(safe_float(s.get("current_balance")) for s in savings)

    # =========================
    # RECENT
    # =========================
    recent_transactions = sorted(
        transactions,
        key=lambda x: x.get("date") or datetime.utcnow(),
        reverse=True
    )[:10]

    active_savings = [s for s in savings if s.get("status") == "active"]

    dashboard = {
        "balance": total_balance,
        "income": total_income,
        "expense": total_expense,
        "savings": total_savings,
        "accounts": len(accounts),
        "categories": len(categories),
        "transactions": len(transactions),
    }

    return render_template(
        "backend/home/dashboard.html",
        dashboard=dashboard,
        accounts=accounts,
        categories=categories,
        transactions=recent_transactions,
        savings=active_savings,
        user=current_user,
        category_labels=category_labels,
        category_values=category_values
    )



@bp.route("/profile")
@login_required
def profile():
    return render_template(
        "backend/pages/components/users/profile.html",
        user=current_user
    )


@bp.route("/account-settings", methods=["GET", "POST"])
@login_required
def account_settings():

    if request.method == "POST":

        data = {
            "fullname": request.form.get("fullname"),
            "username": request.form.get("username"),
            "phone": request.form.get("phone"),
            "country": request.form.get("country"),
            "state": request.form.get("state"),
            "city": request.form.get("city"),
            "address": request.form.get("address"),
            "bio": request.form.get("bio"),
            "updated_at": datetime.utcnow()
        }

        file = request.files.get("photo")

        if file and file.filename:

            upload_result = cloudinary.uploader.upload(file, folder="users")

            data["photo"] = upload_result["secure_url"]  # 🔥 IMPORTANT

        mongo.db.users.update_one(
            {"_id": ObjectId(current_user.id)},
            {"$set": data}
        )

        flash("Account updated successfully.", "success")
        return redirect(url_for("main.account_settings"))

    return render_template(
        "backend/pages/components/users/account_settings.html",
        user=current_user
    )



@bp.route('/add-user', methods=['GET', 'POST'])
@login_required
def add_user():

    if current_user.role not in ['superadmin', 'admin']:
        return abort(403)

    countries = [
        {"code": "SO", "name": "Somalia", "flag_url": "https://flagcdn.com/so.svg"},
        {"code": "KE", "name": "Kenya", "flag_url": "https://flagcdn.com/ke.svg"},
    ]

    if request.method == 'POST':

        fullname = request.form.get('fullname')
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role') or "user"
        country = request.form.get('country')
        phone = request.form.get('phone')
        state = request.form.get('state')
        city = request.form.get('city')
        address = request.form.get('address')
        status = True if request.form.get('status') == '1' else False

        # ================= VALIDATION =================
        if not email or not username or not fullname:
            flash("Fadlan buuxi fields-ka muhiimka ah!", "danger")
            return redirect(url_for('main.add_user'))

        if password != confirm_password:
            flash("Passwords-ka isma laha!", "danger")
            return redirect(url_for('main.add_user'))

        if mongo.db.users.find_one({"email": email}):
            flash("Email-kan horey ayaa loo isticmaalay!", "danger")
            return redirect(url_for('main.add_user'))

        if mongo.db.users.find_one({"username": username}):
            flash("Username-kan horey ayaa loo isticmaalay!", "danger")
            return redirect(url_for('main.add_user'))

        # ================= PHOTO UPLOAD =================
        photo_path = None

        file = request.files.get('photo')

        if file and file.filename:

            project_root = os.path.abspath(os.getcwd())

            upload_dir = os.path.join(
                project_root,
                'static',
                'backend',
                'uploads',
                'users'
            )

            os.makedirs(upload_dir, exist_ok=True)

            filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
            file_path = os.path.join(upload_dir, filename)

            file.save(file_path)

            photo_path = f"backend/uploads/users/{filename}"

        # ================= CREATE USER =================
        new_user = {
            "fullname": fullname,
            "username": username,
            "email": email,
            "password": generate_password_hash(password),
            "role": role,
            "country": country,
            "phone": phone,
            "state": state,
            "city": city,
            "address": address,
            "status": status,
            "photo": photo_path,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        mongo.db.users.insert_one(new_user)

        flash(f"User {username} si guul leh ayaa loo diiwaangeliyey!", "success")
        return redirect(url_for('main.add_user'))

    return render_template(
        "backend/pages/components/users/add_user.html",
        countries=countries
    )


@bp.route('/edit-user/<user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):

    if current_user.role not in ['superadmin', 'admin']:
        return abort(403)

    try:
        raw_user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        flash("Invalid user ID!", "danger")
        return redirect(url_for('main.index'))

    if not raw_user:
        flash("User-ka lama helin!", "danger")
        return redirect(url_for('main.index'))

    user = User(raw_user)

    if request.method == 'POST':

        fullname = request.form.get('fullname')
        username = request.form.get('username')
        email = request.form.get('email')
        role = request.form.get('role')
        country = request.form.get('country')
        phone = request.form.get('phone')
        address = request.form.get('address')
        bio = request.form.get('bio')
        status = True if request.form.get('status') == '1' else False

        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # ================= VALIDATION =================
        if mongo.db.users.find_one({
            "username": username,
            "_id": {"$ne": ObjectId(user_id)}
        }):
            flash("Username-kan horey ayaa loo isticmaalay!", "danger")
            return redirect(url_for('main.edit_user', user_id=user_id))

        if mongo.db.users.find_one({
            "email": email,
            "_id": {"$ne": ObjectId(user_id)}
        }):
            flash("Email-kan horey ayaa loo isticmaalay!", "danger")
            return redirect(url_for('main.edit_user', user_id=user_id))

        updated_data = {
            "fullname": fullname,
            "username": username,
            "email": email,
            "role": role,
            "country": country,
            "phone": phone,
            "address": address,
            "bio": bio,
            "status": status,
            "updated_at": datetime.utcnow()
        }

        # ================= PASSWORD =================
        if password:
            if password != confirm_password:
                flash("Passwords-ka isma laha!", "danger")
                return redirect(url_for('main.edit_user', user_id=user_id))

            updated_data["password"] = generate_password_hash(password)

        # ================= CLOUDINARY PHOTO =================
        file = request.files.get('photo')

        if file and file.filename:

            old_public_id = raw_user.get("photo_public_id")

            # delete old image
            if old_public_id:
                try:
                    cloudinary.uploader.destroy(old_public_id)
                except Exception:
                    pass

            # upload new image
            result = cloudinary.uploader.upload(
                file,
                folder="users"
            )

            updated_data["photo"] = result["secure_url"]
            updated_data["photo_public_id"] = result["public_id"]

        # ================= UPDATE DB =================
        mongo.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": updated_data}
        )

        flash("User si guul leh ayaa loo cusbooneysiiyey!", "success")
        return redirect(url_for('main.edit_user', user_id=user_id))

    return render_template(
        "backend/pages/components/users/edit_user.html",
        user=user
    )


@bp.route('/delete-user/<user_id>', methods=['POST'])
@login_required
def delete_user(user_id):

    if current_user.role not in ['superadmin', 'admin']:
        return abort(403)

    try:
        user = mongo.db.users.find_one({
            "_id": ObjectId(user_id)
        })
    except Exception:
        flash("Invalid user ID!", "danger")
        return redirect(url_for('main.all_users'))

    if not user:
        flash("User-ka lama helin!", "danger")
        return redirect(url_for('main.all_users'))

    # ==========================================
    # DELETE USER PHOTO FROM CLOUDINARY
    # ==========================================

    photo_public_id = user.get("photo_public_id")

    if photo_public_id:
        try:
            cloudinary.uploader.destroy(photo_public_id)
        except Exception:
            pass

    # ==========================================
    # FIND ALL USER ORDERS
    # ==========================================

    orders = list(
        mongo.db.orders.find({
            "user_id": ObjectId(user_id)
        })
    )

    # ==========================================
    # RESTORE PRODUCT STOCK
    # ==========================================

    for order in orders:

        for item in order.get("items", []):

            try:
                mongo.db.products.update_one(
                    {
                        "_id": ObjectId(item["product_id"])
                    },
                    {
                        "$inc": {
                            "stock": int(item["qty"])
                        }
                    }
                )
            except Exception:
                pass

    # ==========================================
    # DELETE ALL CUSTOMER ORDERS
    # ==========================================

    mongo.db.orders.delete_many({
        "user_id": ObjectId(user_id)
    })

    # ==========================================
    # DELETE USER
    # ==========================================

    mongo.db.users.delete_one({
        "_id": ObjectId(user_id)
    })

    flash(
        "Customer, orders-kiisii iyo payments-kiisii si guul leh ayaa loo tirtiray!",
        "success"
    )

    return redirect(url_for('main.all_users'))



@bp.route('/all-users', methods=['GET'])
@login_required
def all_users():

    if current_user.role not in ['superadmin', 'admin']:
        return abort(403)

    if current_user.role == 'superadmin':
        # Superadmin sees everyone
        users_cursor = mongo.db.users.find().sort('created_at', -1)

    else:  # admin
        # Admin cannot see superadmins
        users_cursor = mongo.db.users.find(
            {"role": {"$ne": "superadmin"}}
        ).sort('created_at', -1)

    users = [User(user_data) for user_data in users_cursor]

    return render_template(
        'backend/pages/components/users/all_users.html',
        users=users
    )



@bp.route('/add-category', methods=['GET', 'POST'])
@login_required
def add_category():

    if request.method == "POST":

        # 🧼 CLEAN INPUT PROPERLY
        name = request.form.get("name", "").strip()
        category_type = request.form.get("type", "expense").strip()

        if not name:
            flash("Category name is required", "danger")
            return redirect(url_for("main.add_category"))

        # 🔥 NORMALIZE NAME (VERY IMPORTANT)
        normalized_name = re.sub(r'\s+', ' ', name).lower()

        # 🔒 HARD DUPLICATE CHECK
        existing = mongo.db.categories.find_one({
            "user_id": ObjectId(current_user.id),
            "type": category_type,
            "name_normalized": normalized_name
        })

        if existing:
            flash("Category already exists.", "danger")
            return redirect(url_for("main.add_category"))

        # 🧠 ITEMS SAFE
        items_raw = request.form.get("items", "").strip()

        items = []
        if items_raw and items_raw.lower() not in ["no items", "none", "-"]:
            items = [
                i.strip()
                for i in items_raw.split(",")
                if i.strip()
            ]

        items = list(dict.fromkeys(items))

        # 💾 SAVE WITH NORMALIZED FIELD
        data = {
            "user_id": ObjectId(current_user.id),
            "name": name,
            "name_normalized": normalized_name,   # 🔥 KEY FIX
            "slug": name.lower().replace(" ", "-"),
            "items": items,
            "type": category_type,
            "status": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        mongo.db.categories.insert_one(data)

        flash("Category added successfully.", "success")
        return redirect(url_for("main.category_list"))

    return render_template("backend/pages/components/categories/add_category.html")



@bp.route('/categories')
@login_required
def category_list():

    # 🔥 GET DATA BASED ON ROLE
    if current_user.role == UserRole.superadmin.value:
        raw_categories = list(mongo.db.categories.find())
    else:
        raw_categories = list(mongo.db.categories.find({
            "user_id": ObjectId(current_user.id)
        }))

    categories = []

    for c in raw_categories:

        # 🧹 CLEAN ITEMS SAFELY
        items = c.get("items", [])

        fixed_items = []

        if isinstance(items, list):
            for i in items:
                if isinstance(i, str):
                    i = i.strip()

                    # fix broken cases like: '"Cumar"' or 'Cumar hhg'
                    i = i.replace('"', "")

                    # split if badly stored
                    parts = i.split()
                    fixed_items.extend(parts)
                else:
                    fixed_items.append(str(i))

        # remove duplicates + empty
        c["items"] = list(dict.fromkeys([x for x in fixed_items if x]))

        # 🧱 WRAP CLASS
        categories.append(Category(c))

    return render_template(
        "backend/pages/components/categories/all_categories.html",
        categories=categories
    )


def normalize_name(name):
    return re.sub(r'\s+', ' ', name).strip().lower()


@bp.route("/edit-category/<id>", methods=["GET", "POST"])
@login_required
def edit_category(id):

    # 🔒 Validate ObjectId
    try:
        category_id = ObjectId(id)
    except:
        flash("Invalid category ID", "danger")
        return redirect(url_for("main.category_list"))

    # 🔎 Get category
    category = mongo.db.categories.find_one({"_id": category_id})

    if not category:
        flash("Category not found", "danger")
        return redirect(url_for("main.category_list"))

    # 🔐 SECURITY CHECK
    if current_user.role != "superadmin":
        if str(category.get("user_id")) != str(current_user.id):
            flash("Not allowed", "danger")
            return redirect(url_for("main.category_list"))

    # 🧹 CLEAN ITEMS FOR DISPLAY
    raw_items = category.get("items", [])
    cleaned_items = []

    if isinstance(raw_items, list):
        for i in raw_items:
            if isinstance(i, str):
                try:
                    decoded = json.loads(i)
                    if isinstance(decoded, list):
                        cleaned_items.extend(decoded)
                    else:
                        cleaned_items.append(str(decoded))
                except:
                    cleaned_items.append(i)
            else:
                cleaned_items.append(str(i))

    category["items"] = list(dict.fromkeys(cleaned_items))

    # POST UPDATE
    if request.method == "POST":

        name = request.form.get("name", "").strip()
        category_type = request.form.get("type", "").strip()

        if not name:
            flash("Category name is required", "danger")
            return redirect(request.url)

        # 🔥 NORMALIZE NAME
        normalized_name = normalize_name(name)

        # 🔒 DUPLICATE CHECK (IMPORTANT FIX)
        existing = mongo.db.categories.find_one({
            "_id": {"$ne": category_id},
            "user_id": ObjectId(current_user.id),
            "type": category_type,
            "name_normalized": normalized_name
        })

        if existing:
            flash("Category already exists.", "danger")
            return redirect(request.url)

        # 🧠 SAFE ITEMS PARSING
        items_raw = request.form.get("items", "")

        items = []

        if items_raw and items_raw.lower() not in ["no items", "none", "-"]:
            items = [
                i.strip()
                for i in items_raw.split(",")
                if i.strip() and i.lower() != "no items"
            ]

        # 🧼 CLEAN + REMOVE DUPLICATES
        items = list(dict.fromkeys(items))

        # 💾 UPDATE DB
        mongo.db.categories.update_one(
            {"_id": category_id},
            {"$set": {
                "name": name,
                "name_normalized": normalized_name,  # 🔥 IMPORTANT FIX
                "slug": name.lower().replace(" ", "-"),
                "type": category_type,
                "items": items,
                "updated_at": datetime.utcnow()
            }}
        )

        flash("Category updated successfully", "success")
        return redirect(url_for("main.category_list"))

    return render_template(
        "backend/pages/components/categories/edit_category.html",
        category=category
    )


@bp.route("/delete-category/<id>", methods=["GET", "POST"])
@login_required
def delete_category(id):

    category = mongo.db.categories.find_one({"_id": ObjectId(id)})

    if not category:
        flash("Category not found", "danger")
        return redirect(url_for("main.category_list"))

    # ADMIN SECURITY CHECK
    if current_user.role != "superadmin" and str(category["user_id"]) != str(current_user.id):
        flash("Not allowed", "danger")
        return redirect(url_for("main.category_list"))

    mongo.db.categories.delete_one({"_id": ObjectId(id)})

    flash("Category deleted successfully", "success")
    return redirect(url_for("main.category_list"))


@bp.route("/export-categories")
@login_required
def export_categories():

    # 🔎 GET DATA BASED ON ROLE
    if current_user.role == UserRole.superadmin.value:
        categories = list(mongo.db.categories.find())
    else:
        categories = list(mongo.db.categories.find({
            "user_id": ObjectId(current_user.id)
        }))

    # 🧼 CLEAN FOR JSON EXPORT
    clean_data = []

    for c in categories:
        clean_data.append({
            "name": c.get("name"),
            "name_normalized": c.get("name_normalized"),
            "slug": c.get("slug"),
            "type": c.get("type"),
            "items": c.get("items", []),
            "status": c.get("status"),
            "created_at": str(c.get("created_at")),
            "updated_at": str(c.get("updated_at")),
        })

    return Response(
        json.dumps(clean_data, indent=4),
        mimetype="application/json",
        headers={
            "Content-Disposition": "attachment; filename=categories.json"
        }
    )



@bp.route("/import-categories", methods=["POST"])
@login_required
def import_categories():

    file = request.files.get("file")

    if not file:
        flash("Please upload a file", "danger")
        return redirect(url_for("main.category_list"))

    try:
        data = json.load(file)
    except:
        flash("Invalid JSON file", "danger")
        return redirect(url_for("main.category_list"))

    if not isinstance(data, list):
        flash("Invalid data format (must be list)", "danger")
        return redirect(url_for("main.category_list"))

    imported = 0
    skipped = 0

    for item in data:

        if not isinstance(item, dict):
            continue

        name = (item.get("name") or "").strip()
        category_type = (item.get("type") or "expense").strip()

        if not name:
            continue

        normalized = normalize_name(name)

        # 🔒 DUPLICATE CHECK (USER + TYPE + NAME)
        existing = mongo.db.categories.find_one({
            "user_id": ObjectId(current_user.id),
            "type": category_type,
            "name_normalized": normalized
        })

        if existing:
            skipped += 1
            continue

        # 🧠 SAFE ITEMS PARSE
        items = item.get("items") or []

        if not isinstance(items, list):
            items = []

        # remove duplicates inside items
        items = list(dict.fromkeys([i.strip() for i in items if isinstance(i, str) and i.strip()]))

        # 💾 INSERT
        mongo.db.categories.insert_one({
            "user_id": ObjectId(current_user.id),
            "name": name,
            "name_normalized": normalized,
            "slug": name.lower().replace(" ", "-"),
            "items": items,
            "type": category_type,
            "status": bool(item.get("status", True)),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })

        imported += 1

    flash(f"Imported: {imported}, Skipped: {skipped}", "success")
    return redirect(url_for("main.category_list"))


# ==============================
# ACCOUNT LIST
# ==============================
@bp.route("/accounts")
@login_required
def account_list():

    # 🔥 ROLE-BASED FILTER (optional future scaling)
    query = {}

    if current_user.role != UserRole.superadmin.value:
        query["user_id"] = ObjectId(current_user.id)

    accounts = list(
        mongo.db.accounts.find(query).sort("created_at", -1)
    )

    return render_template(
        "backend/pages/components/accounts/all_accounts.html",
        accounts=accounts
    )


@bp.route('/add-account', methods=['GET', 'POST'])
@login_required
def add_account():

    if request.method == "POST":

        # Form Data
        name = request.form.get("name", "").strip()
        account_type = request.form.get("type", "cash").strip()
        balance = request.form.get("balance", 0)
        currency = request.form.get("currency", "USD").strip()

        # Validation
        if not name:
            flash("Account name is required.", "danger")
            return redirect(url_for("main.add_account"))

        try:
            balance = float(balance)
        except ValueError:
            flash("Invalid balance amount.", "danger")
            return redirect(url_for("main.add_account"))

        # Duplicate Check
        existing = mongo.db.accounts.find_one({
            "user_id": ObjectId(current_user.id),
            "name": {
                "$regex": f"^{name}$",
                "$options": "i"
            }
        })

        if existing:
            flash("Account already exists.", "danger")
            return redirect(url_for("main.add_account"))

        # Save
        account = Account()

        data = account.add(
            user_id=current_user.id,
            name=name,
            account_type=account_type,
            balance=balance,
            currency=currency,
            status=True
        )

        data["user_id"] = ObjectId(current_user.id)

        mongo.db.accounts.insert_one(data)

        flash("Account created successfully.", "success")
        return redirect(url_for("main.account_list"))

    return render_template(
        "backend/pages/components/accounts/add_account.html"
    )


@bp.route("/edit-account/<id>", methods=["GET", "POST"])
@login_required
def edit_account(id):

    account = mongo.db.accounts.find_one({
        "_id": ObjectId(id),
        "user_id": ObjectId(current_user.id)
    })

    if not account:
        flash("Account not found.", "danger")
        return redirect(url_for("main.account_list"))

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        account_type = request.form.get("type")
        currency = request.form.get("currency")
        balance = request.form.get("balance", 0)

        if not name:
            flash("Account name is required.", "danger")
            return redirect(url_for("main.edit_account", id=id))

        try:
            balance = float(balance)
        except ValueError:
            balance = 0

        mongo.db.accounts.update_one(
            {"_id": ObjectId(id)},
            {
                "$set": {
                    "name": name,
                    "type": account_type,
                    "currency": currency,
                    "balance": balance,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        flash("Account updated successfully.", "success")
        return redirect(url_for("main.account_list"))

    return render_template(
        "backend/pages/components/accounts/edit_account.html",
        account=account
    )


@bp.route("/delete-account/<id>")
@login_required
def delete_account(id):

    account = mongo.db.accounts.find_one({
        "_id": ObjectId(id),
        "user_id": ObjectId(current_user.id)
    })

    if not account:
        flash("Account not found.", "danger")
        return redirect(url_for("main.account_list"))

    # 🔥 SAFETY CHECK (IMPORTANT)
    has_transactions = mongo.db.transactions.find_one({
        "account_id": id
    })

    has_savings = mongo.db.savings.find_one({
        "account_id": id
    })

    if has_transactions or has_savings:
        flash("This account cannot be deleted because it is in use.", "warning")
        return redirect(url_for("main.account_list"))

    mongo.db.accounts.delete_one({
        "_id": ObjectId(id)
    })

    flash("Account deleted successfully.", "success")
    return redirect(url_for("main.account_list"))


@bp.route("/saving-topup", methods=["POST"])
@login_required
def saving_topup():

    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    saving_id = data.get("saving_id")
    account_id = data.get("account_id")
    amount = data.get("amount")

    # validate amount safely
    try:
        amount = float(amount)
    except:
        return jsonify({"error": "Invalid amount"}), 400

    if amount <= 0:
        return jsonify({"error": "Amount must be greater than 0"}), 400

    # validate IDs
    try:
        saving_obj_id = ObjectId(saving_id)
        account_obj_id = ObjectId(account_id)
    except:
        return jsonify({"error": "Invalid ID format"}), 400

    saving = mongo.db.savings.find_one({"_id": saving_obj_id})
    account = mongo.db.accounts.find_one({"_id": account_obj_id})

    if not saving:
        return jsonify({"error": "Saving not found"}), 404

    if not account:
        return jsonify({"error": "Account not found"}), 404

    if account.get("balance", 0) < amount:
        return jsonify({"error": "Insufficient account balance"}), 400

    # deduct from account
    mongo.db.accounts.update_one(
        {"_id": account_obj_id},
        {"$inc": {"balance": -amount}}
    )

    # add to saving
    mongo.db.savings.update_one(
        {"_id": saving_obj_id},
        {"$inc": {"current_balance": amount}}
    )

    return jsonify({"message": "Money moved from Account → Saving"})


@bp.route("/saving-withdraw", methods=["POST"])
@login_required
def saving_withdraw():

    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    saving_id = data.get("saving_id")
    account_id = data.get("account_id")
    amount = data.get("amount")

    # validate amount safely
    try:
        amount = float(amount)
    except:
        return jsonify({"error": "Invalid amount"}), 400

    if amount <= 0:
        return jsonify({"error": "Amount must be greater than 0"}), 400

    # validate IDs
    try:
        saving_obj_id = ObjectId(saving_id)
        account_obj_id = ObjectId(account_id)
    except:
        return jsonify({"error": "Invalid ID format"}), 400

    saving = mongo.db.savings.find_one({"_id": saving_obj_id})
    account = mongo.db.accounts.find_one({"_id": account_obj_id})

    if not saving:
        return jsonify({"error": "Saving not found"}), 404

    if not account:
        return jsonify({"error": "Account not found"}), 404

    if saving.get("current_balance", 0) < amount:
        return jsonify({"error": "Insufficient saving balance"}), 400

    # deduct from saving
    mongo.db.savings.update_one(
        {"_id": saving_obj_id},
        {"$inc": {"current_balance": -amount}}
    )

    # add to account
    mongo.db.accounts.update_one(
        {"_id": account_obj_id},
        {"$inc": {"balance": amount}}
    )

    return jsonify({"message": "Money moved from Saving → Account"})




def clean_category(cat):
    return {
        "_id": str(cat["_id"]),
        "name": cat.get("name", ""),
        "type": cat.get("type", ""),
        "items": [str(i) for i in (cat.get("items") or []) if i]
    }


@bp.route("/transactions")
@login_required
def transaction_list():

    transaction_type = request.args.get("type")
    account_id = request.args.get("account_id")
    category = request.args.get("category")
    item = request.args.get("item")

    query = {
        "user_id": ObjectId(current_user.id)
    }

    # TYPE FILTER
    if transaction_type:
        query["transaction_type"] = transaction_type

    # ACCOUNT FILTER
    if account_id:
        query["account_id"] = ObjectId(account_id)

    # CATEGORY FILTER
    if category:
        query["category"] = category

    # ITEM FILTER
    if item:
        query["item"] = item

    transactions = list(
        mongo.db.transactions.find(query).sort("created_at", -1)
    )

    accounts = list(mongo.db.accounts.find({
        "user_id": ObjectId(current_user.id)
    }))

    categories_raw = list(mongo.db.categories.find({
        "user_id": ObjectId(current_user.id)
    }))

    categories = [clean_category(c) for c in categories_raw]

    account_map = {str(a["_id"]): a["name"] for a in accounts}

    for t in transactions:
        t["account_name"] = account_map.get(str(t.get("account_id")), "Unknown")

    return render_template(
        "backend/pages/components/transactions/all_transactions.html",
        transactions=transactions,
        accounts=accounts,
        categories=categories,
        selected_type=transaction_type,
        selected_account=account_id,
        selected_category=category,
        selected_item=item
    )




@bp.route("/add-transaction", methods=["GET", "POST"])
@login_required
def add_transaction():
    user_oid = ObjectId(current_user.id)

    if request.method == "POST":
        account_id = request.form.get("account_id")
        transaction_type = request.form.get("transaction_type")
        category_id = request.form.get("category")
        item = request.form.get("item")
        amount = request.form.get("amount")
        description = request.form.get("description", "")
        note = request.form.get("note", "")
        reference_no = request.form.get("reference_no")

        if not account_id or not category_id or not amount:
            flash("Account, Category and Amount are required.", "danger")
            return redirect(url_for("main.add_transaction"))
        
        # Gudaha POST
        cat_doc = mongo.db.categories.find_one({"_id": ObjectId(category_id)})
        if cat_doc.get("type") != transaction_type:
            flash("Category-gan kuma haboona Type-ka aad dooratay!", "danger")
            return redirect(url_for("main.add_transaction"))

        try:
            amount = float(amount)
        except ValueError:
            flash("Invalid amount", "danger")
            return redirect(url_for("main.add_transaction"))

        # 🔥 CATEGORY VALIDATION
        category_doc = mongo.db.categories.find_one({
            "_id": ObjectId(category_id),
            "user_id": user_oid
        })

        if not category_doc:
            flash("Invalid category", "danger")
            return redirect(url_for("main.add_transaction"))

        # 🔥 ITEM VALIDATION
        # 🔥 ITEM VALIDATION
        if item:
            # 1. Soo saar list-ka saxda ah
            raw_items = category_doc.get("items", [])
            
            # Haddii ay tahay JSON string, u beddel list
            if isinstance(raw_items, str):
                try:
                    items = json.loads(raw_items)
                except:
                    items = []
            else:
                items = raw_items

            # 2. Nadiifi dhammaan items-ka si ay u noqdaan strings nadiif ah
            # Tani waxay ka saaraysaa quotes-ka iyo brackets-ka aan loo baahnayn
            clean_items = [str(i).strip('[]"\' ') for i in items]

            # 3. Hadda isbarbar dhig
            if item.strip() not in clean_items:
                flash(f"Invalid item: '{item}' maaha mid ku jira category-ga.", "danger")
                return redirect(url_for("main.add_transaction"))
        # 🔥 BALANCE VALIDATION (Halkan ayaan ku daray)
        if transaction_type == "expense":
            account_doc = mongo.db.accounts.find_one({
                "_id": ObjectId(account_id),
                "user_id": user_oid
            })
            if not account_doc or account_doc.get("balance", 0) < amount:
                flash(f"Digniin: Akaunkan balance-kiisu waa {account_doc.get('balance', 0)}. Ma samayn kartid expense ka badan lacagtaas!", "danger")
                return redirect(url_for("main.add_transaction"))

        # 🔥 SAVE TRANSACTION WITH SESSION (Atomicity)
        try:
            with mongo.db.client.start_session() as session:
                with session.start_transaction():
                    # 1. Diyaarinta Data
                    data = Transaction().add(
                        user_id=current_user.id,
                        account_id=account_id,
                        transaction_type=transaction_type,
                        category=category_doc["name"],
                        item=item,
                        amount=amount,
                        description=description,
                        note=note,
                        reference_no=reference_no
                    )
                    data["user_id"] = user_oid
                    data["account_id"] = ObjectId(account_id)

                    # 2. Insert Transaction
                    mongo.db.transactions.insert_one(data, session=session)

                    # 3. Update Balance
                    inc_val = amount if transaction_type == "income" else -amount
                    mongo.db.accounts.update_one(
                        {"_id": ObjectId(account_id)},
                        {"$inc": {"balance": inc_val}},
                        session=session
                    )
            
            flash("Transaction saved successfully", "success")
            return redirect(url_for("main.transaction_list"))
        
        except Exception as e:
            flash(f"Error saving transaction: {str(e)}", "danger")
            return redirect(url_for("main.add_transaction"))

    # GET Request: Fetch and Clean Categories
    # GET Request: Fetch and Clean Categories
    accounts = list(mongo.db.accounts.find({"user_id": user_oid}))
    categories_raw = list(mongo.db.categories.find({"user_id": user_oid}))

    categories = []
    for cat in categories_raw:
        items = cat.get("items", [])
        
        # Haddii ay tahay JSON string, u beddel list
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except:
                items = []
                
        # Hubi in items ay yihiin list dhab ah (haddii ay ku jiraan brackets dhexda)
        clean_items = []
        if isinstance(items, list):
            for i in items:
                # Ka saar brackets iyo quotes dheeraad ah
                clean_item = str(i).replace('[', '').replace(']', '').replace("'", "").replace('"', "").strip()
                if clean_item:
                    clean_items.append(clean_item)
                    
        cat["items"] = clean_items
        categories.append(clean_category(cat))
        

    return render_template(
        "backend/pages/components/transactions/add_transaction.html",
        accounts=accounts,
        categories=categories
    )


@bp.route("/edit-transaction/<id>", methods=["GET", "POST"])
@login_required
def edit_transaction(id):
    user_oid = ObjectId(current_user.id)
    
    # 1. Soo hel transaction-ka
    transaction = mongo.db.transactions.find_one({"_id": ObjectId(id), "user_id": user_oid})
    if not transaction:
        flash("Transaction not found", "danger")
        return redirect(url_for("main.transaction_list"))

    if request.method == "POST":
        # Soo hel xogta cusub
        account_id = request.form.get("account_id")
        transaction_type = request.form.get("transaction_type")
        category_id = request.form.get("category")
        item = request.form.get("item")
        amount = float(request.form.get("amount", 0))

        # Ka hor intaadan bilaabin transaction-ka
        if transaction_type == "expense":
            account = mongo.db.accounts.find_one({"_id": ObjectId(account_id)})
            if account and account.get("balance", 0) < amount:
                flash("Balance-ka akaunkan kuma filna in laga bixiyo lacagtan!", "danger")
                return redirect(url_for("main.edit_transaction", id=id))
            
        
        # Validation (la mid ah kii hore)
        category_doc = mongo.db.categories.find_one({"_id": ObjectId(category_id), "user_id": user_oid})
        if not category_doc:
            flash("Invalid category", "danger")
            return redirect(url_for("main.edit_transaction", id=id))

        try:
            with mongo.db.client.start_session() as session:
                with session.start_transaction():
                    # 1. Dib u hagaaji balance-ka:
                    # Marka hore, ku dar lacagtii hore (haddii ay ahayd expense -> ku dar, haddii income -> ka jar)
                    old_amount = transaction["amount"]
                    old_type = transaction["transaction_type"]
                    
                    # Revert old balance
                    revert_val = -old_amount if old_type == "income" else old_amount
                    mongo.db.accounts.update_one(
                        {"_id": transaction["account_id"]},
                        {"$inc": {"balance": revert_val}},
                        session=session
                    )

                    # 2. Update Transaction
                    mongo.db.transactions.update_one(
                        {"_id": ObjectId(id)},
                        {"$set": {
                            "account_id": ObjectId(account_id),
                            "transaction_type": transaction_type,
                            "category": category_doc["name"],
                            "item": item,
                            "amount": amount,
                            "description": request.form.get("description", ""),
                            "updated_at": datetime.utcnow()
                        }},
                        session=session
                    )

                    # 3. Apply new balance
                    new_val = amount if transaction_type == "income" else -amount
                    mongo.db.accounts.update_one(
                        {"_id": ObjectId(account_id)},
                        {"$inc": {"balance": new_val}},
                        session=session
                    )
            
            flash("Transaction updated successfully", "success")
            return redirect(url_for("main.transaction_list"))
            
        except Exception as e:
            flash(f"Error updating: {str(e)}", "danger")
            return redirect(url_for("main.edit_transaction", id=id))

    # GET: Diyaarinta xogta form-ka
    accounts = list(mongo.db.accounts.find({"user_id": user_oid}))
   # GET Request: Fetch and Clean Categories
    categories_raw = list(mongo.db.categories.find({"user_id": user_oid}))
    
    categories = []
    for cat in categories_raw:
        items = cat.get("items", [])
        
        # Haddii uu yahay string JSON ah, u beddel list
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except:
                items = []
        
        # Hubi in items ay yihiin list oo nadiifi wixii characters ah
        # Haddii uu items horey u ahaa list, koodkani wuu u shaqaynayaa
        if isinstance(items, list):
            cat["items"] = [str(i).strip('[]"\' ') for i in items]
        else:
            cat["items"] = []
            
        categories.append(clean_category(cat))

  
    return render_template(
        "backend/pages/components/transactions/edit_transaction.html",
        transaction=transaction,
        accounts=accounts,
        categories=categories
    )


@bp.route("/delete-transaction/<id>")
@login_required
def delete_transaction(id):

    trx = mongo.db.transactions.find_one({
        "_id": ObjectId(id),
        "user_id": ObjectId(current_user.id)
    })

    if not trx:
        flash("Transaction not found.", "danger")
        return redirect(url_for("main.transaction_list"))

    amount = float(trx["amount"])

    # 🔥 REVERSE BALANCE
    if trx["transaction_type"] == "income":
        mongo.db.accounts.update_one(
            {"_id": trx["account_id"]},
            {"$inc": {"balance": -amount}}
        )
    else:
        mongo.db.accounts.update_one(
            {"_id": trx["account_id"]},
            {"$inc": {"balance": amount}}
        )

    # DELETE
    mongo.db.transactions.delete_one({
        "_id": ObjectId(id)
    })

    flash("Transaction deleted successfully.", "success")
    return redirect(url_for("main.transaction_list"))


@bp.route("/add-saving", methods=["GET", "POST"])
@login_required
def add_saving():

    # 🔥 GET USER ACCOUNTS
    accounts = list(mongo.db.accounts.find({
        "user_id": ObjectId(current_user.id)
    }))

    if request.method == "POST":

        title = request.form.get("title")
        description = request.form.get("description", "")
        target_amount = request.form.get("target_amount")
        account_id = request.form.get("account_id")
        start_date = request.form.get("start_date")
        maturity_date = request.form.get("maturity_date")

        # ❌ VALIDATION
        if not title or not target_amount or not account_id:
            flash("Title, Target Amount and Account are required.", "danger")
            return redirect(url_for("main.add_saving"))

        try:
            target_amount = float(target_amount)
        except ValueError:
            flash("Invalid target amount.", "danger")
            return redirect(url_for("main.add_saving"))

        # 🔥 CHECK ACCOUNT EXISTS
        account = mongo.db.accounts.find_one({
            "_id": ObjectId(account_id),
            "user_id": ObjectId(current_user.id)
        })

        if not account:
            flash("Invalid account selected.", "danger")
            return redirect(url_for("main.add_saving"))

        # 🔥 CREATE SAVING OBJECT
        saving = Saving()

        data = saving.add(
            user_id=current_user.id,
            title=title,
            description=description,
            target_amount=target_amount,
            account_id=account_id,
            start_date=start_date,
            maturity_date=maturity_date
        )

        # convert ObjectIds
        data["user_id"] = ObjectId(current_user.id)
        data["account_id"] = ObjectId(account_id)

        # 💾 SAVE TO DB
        mongo.db.savings.insert_one(data)

        flash("Saving goal created successfully.", "success")
        return redirect(url_for("main.saving_list"))

    return render_template(
        "backend/pages/components/savings/add_saving.html",
        accounts=accounts
    )


@bp.route("/savings")
@login_required
def saving_list():

    # User accounts
    accounts = list(
        mongo.db.accounts.find({
            "user_id": ObjectId(current_user.id)
        })
    )

    # Account map
    account_map = {
        str(acc["_id"]): acc["name"]
        for acc in accounts
    }

    # Savings
    savings = list(
        mongo.db.savings.find({
            "user_id": ObjectId(current_user.id)
        }).sort("created_at", -1)
    )

    # Add account name + progress
    for saving in savings:

        saving["account_name"] = account_map.get(
            str(saving.get("account_id")),
            "Unknown"
        )

        target = float(saving.get("target_amount", 0))
        current = float(saving.get("current_balance", 0))

        if target > 0:
            saving["progress"] = round((current / target) * 100, 2)
        else:
            saving["progress"] = 0

    return render_template(
        "backend/pages/components/savings/all_savings.html",
        savings=savings
    )



# ===============================
# EDIT SAVING
# ===============================
@bp.route("/edit-saving/<id>", methods=["GET", "POST"])
@login_required
def edit_saving(id):

    saving = mongo.db.savings.find_one({
        "_id": ObjectId(id),
        "user_id": ObjectId(current_user.id)
    })

    if not saving:
        flash("Saving goal not found.", "danger")
        return redirect(url_for("main.saving_list"))

    accounts = list(mongo.db.accounts.find({
        "user_id": ObjectId(current_user.id)
    }))

    if request.method == "POST":

        title = request.form.get("title")
        description = request.form.get("description")
        target_amount = request.form.get("target_amount")
        account_id = request.form.get("account_id")
        maturity_date = request.form.get("maturity_date")
        status = request.form.get("status")



        try:
            target_amount = float(target_amount)
        except:
            flash("Invalid target amount.", "danger")
            return redirect(request.url)

        update_data = {
            "title": title,
            "description": description,
            "target_amount": target_amount,
            "account_id": ObjectId(account_id),
            "status": status,
            "updated_at": datetime.utcnow()
        }

        saving = mongo.db.savings.find_one({
            "_id": ObjectId(id),
            "user_id": ObjectId(current_user.id)
        })

        if not saving:
            flash("Saving goal not found.", "danger")
            return redirect(url_for("main.saving_list"))

        # Convert maturity_date haddii uu string yahay
        if saving.get("maturity_date") and isinstance(saving["maturity_date"], str):
            try:
                saving["maturity_date"] = datetime.strptime(
                    saving["maturity_date"],
                    "%Y-%m-%d"
                )
            except:
                saving["maturity_date"] = None

        mongo.db.savings.update_one(
            {"_id": ObjectId(id)},
            {"$set": update_data}
        )

        flash("Saving updated successfully.", "success")
        return redirect(url_for("main.saving_list"))

    return render_template(
        "backend/pages/components/savings/edit_saving.html",
        saving=saving,
        accounts=accounts
    )



# ===============================
# DELETE SAVING
# ===============================
@bp.route("/delete-saving/<id>")
@login_required
def delete_saving(id):

    saving = mongo.db.savings.find_one({
        "_id": ObjectId(id),
        "user_id": ObjectId(current_user.id)
    })

    if not saving:
        flash("Saving goal not found.", "danger")
        return redirect(url_for("main.saving_list"))

    mongo.db.savings.delete_one({
        "_id": ObjectId(id)
    })

    flash("Saving goal deleted successfully.", "success")

    return redirect(url_for("main.saving_list"))


@bp.route("/saving/<id>/add-transaction", methods=["GET", "POST"])
@login_required
def add_saving_transaction(id):

    try:
        saving_obj_id = ObjectId(id)
    except:
        flash("Invalid saving ID.", "danger")
        return redirect(url_for("main.saving_list"))

    # ------------------------
    # GET SAVING
    # ------------------------
    saving = mongo.db.savings.find_one({
        "_id": saving_obj_id,
        "user_id": ObjectId(current_user.id)
    })

    if not saving:
        flash("Saving goal not found.", "danger")
        return redirect(url_for("main.saving_list"))

    # ------------------------
    # GET ACCOUNTS
    # ------------------------
    accounts = list(mongo.db.accounts.find({
        "user_id": ObjectId(current_user.id)
    }))

    # ------------------------
    # POST LOGIC
    # ------------------------
    if request.method == "POST":

        account_id = request.form.get("account_id")
        transaction_type = request.form.get("transaction_type")
        amount = request.form.get("amount")
        description = request.form.get("description", "")
        note = request.form.get("note", "")
        reference_no = request.form.get("reference_no")

        # validate required
        if not account_id or not amount:
            flash("Account and Amount are required.", "danger")
            return redirect(request.url)

        # validate amount
        try:
            amount = float(amount)
        except:
            flash("Invalid amount.", "danger")
            return redirect(request.url)

        if amount <= 0:
            flash("Amount must be greater than 0.", "danger")
            return redirect(request.url)

        # validate account
        try:
            account_obj_id = ObjectId(account_id)
        except:
            flash("Invalid account ID.", "danger")
            return redirect(request.url)

        account = mongo.db.accounts.find_one({
            "_id": account_obj_id,
            "user_id": ObjectId(current_user.id)
        })

        if not account:
            flash("Account not found.", "danger")
            return redirect(request.url)

        # ------------------------
        # BALANCE VALIDATION
        # ------------------------
        if transaction_type == "deposit":
            if account.get("balance", 0) < amount:
                flash("Account balance is insufficient.", "danger")
                return redirect(request.url)

        elif transaction_type == "withdrawal":
            if saving.get("current_balance", 0) < amount:
                flash("Saving balance is insufficient.", "danger")
                return redirect(request.url)

        else:
            flash("Invalid transaction type.", "danger")
            return redirect(request.url)

        # ------------------------
        # CREATE TRANSACTION DATA
        # ------------------------
        trx = SavingTransaction()

        data = trx.add(
            user_id=current_user.id,
            saving_id=id,
            account_id=account_id,
            transaction_type=transaction_type,
            amount=amount,
            description=description,
            note=note,
            reference_no=reference_no
        )

        data["user_id"] = ObjectId(current_user.id)
        data["saving_id"] = saving_obj_id
        data["account_id"] = account_obj_id

        mongo.db.saving_transactions.insert_one(data)

        # ------------------------
        # UPDATE BALANCES
        # ------------------------
        if transaction_type == "deposit":

            mongo.db.accounts.update_one(
                {"_id": account_obj_id},
                {"$inc": {"balance": -amount}}
            )

            mongo.db.savings.update_one(
                {"_id": saving_obj_id},
                {"$inc": {"current_balance": amount}}
            )

        elif transaction_type == "withdrawal":

            mongo.db.savings.update_one(
                {"_id": saving_obj_id},
                {"$inc": {"current_balance": -amount}}
            )

            mongo.db.accounts.update_one(
                {"_id": account_obj_id},
                {"$inc": {"balance": amount}}
            )

        # ------------------------
        # AUTO COMPLETE SAVING
        # ------------------------
        updated = mongo.db.savings.find_one({"_id": saving_obj_id})

        if updated.get("current_balance", 0) >= updated.get("target_amount", 0):

            mongo.db.savings.update_one(
                {"_id": saving_obj_id},
                {
                    "$set": {
                        "status": "completed",
                        "updated_at": datetime.utcnow()
                    }
                }
            )

        flash("Saving transaction added successfully.", "success")

        return redirect(url_for("main.saving_transaction_list"))

    # ------------------------
    # RENDER PAGE
    # ------------------------
    return render_template(
        "backend/pages/components/savings_transaction/add_saving_transaction.html",
        saving=saving,
        accounts=accounts
    )



@bp.route("/saving-transactions")
@login_required
def saving_transaction_list():

    transaction_type = request.args.get("type")
    saving_id = request.args.get("saving_id")
    account_id = request.args.get("account_id")

    query = {
        "user_id": ObjectId(current_user.id)
    }

    # Transaction Type Filter
    if transaction_type:
        query["transaction_type"] = transaction_type

    # Saving Filter
    if saving_id:
        query["saving_id"] = ObjectId(saving_id)

    # Account Filter
    if account_id:
        query["account_id"] = ObjectId(account_id)

    # Transactions
    transactions = list(
        mongo.db.saving_transactions.find(query).sort("created_at", -1)
    )

    # Savings
    savings = list(
        mongo.db.savings.find({
            "user_id": ObjectId(current_user.id)
        })
    )

    # Accounts
    accounts = list(
        mongo.db.accounts.find({
            "user_id": ObjectId(current_user.id)
        })
    )

    # Maps
    saving_map = {
        str(s["_id"]): s["title"]
        for s in savings
    }

    account_map = {
        str(a["_id"]): a["name"]
        for a in accounts
    }

    # Display Names
    for trx in transactions:

        trx["saving_name"] = saving_map.get(
            str(trx["saving_id"]),
            "Unknown Saving"
        )

        trx["account_name"] = account_map.get(
            str(trx["account_id"]),
            "Unknown Account"
        )

    return render_template(
        "backend/pages/components/savings_transaction/all_saving_transactions.html",
        transactions=transactions,
        savings=savings,
        accounts=accounts,
        selected_type=transaction_type,
        selected_saving=saving_id,
        selected_account=account_id
    )



@bp.route("/saving-transaction/edit/<id>", methods=["GET", "POST"])
@login_required
def edit_saving_transaction(id):

    trx = mongo.db.saving_transactions.find_one({
        "_id": ObjectId(id),
        "user_id": ObjectId(current_user.id)
    })

    if not trx:
        flash("Transaction not found.", "danger")
        return redirect(url_for("main.saving_transaction_list"))

    accounts = list(mongo.db.accounts.find({
        "user_id": ObjectId(current_user.id)
    }))

    if request.method == "POST":

        new_account = request.form.get("account_id")
        new_type = request.form.get("transaction_type")
        new_amount = float(request.form.get("amount"))
        description = request.form.get("description")
        note = request.form.get("note")
        reference_no = request.form.get("reference_no")

        old_account = trx["account_id"]
        old_amount = float(trx["amount"])
        old_type = trx["transaction_type"]
        saving_id = trx["saving_id"]

        # Reverse old balances
        if old_type == "deposit":
            mongo.db.accounts.update_one(
                {"_id": old_account},
                {"$inc": {"balance": old_amount}}
            )
            mongo.db.savings.update_one(
                {"_id": saving_id},
                {"$inc": {"current_balance": -old_amount}}
            )

        else:
            mongo.db.accounts.update_one(
                {"_id": old_account},
                {"$inc": {"balance": -old_amount}}
            )
            mongo.db.savings.update_one(
                {"_id": saving_id},
                {"$inc": {"current_balance": old_amount}}
            )

        # Apply new balances
        if new_type == "deposit":
            mongo.db.accounts.update_one(
                {"_id": ObjectId(new_account)},
                {"$inc": {"balance": -new_amount}}
            )
            mongo.db.savings.update_one(
                {"_id": saving_id},
                {"$inc": {"current_balance": new_amount}}
            )

        else:
            mongo.db.accounts.update_one(
                {"_id": ObjectId(new_account)},
                {"$inc": {"balance": new_amount}}
            )
            mongo.db.savings.update_one(
                {"_id": saving_id},
                {"$inc": {"current_balance": -new_amount}}
            )

        mongo.db.saving_transactions.update_one(
            {"_id": ObjectId(id)},
            {
                "$set": {
                    "account_id": ObjectId(new_account),
                    "transaction_type": new_type,
                    "amount": new_amount,
                    "description": description,
                    "note": note,
                    "reference_no": reference_no,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        flash("Transaction updated successfully.", "success")
        return redirect(url_for("main.saving_transaction_list"))

    return render_template(
        "backend/pages/components/savings_transaction/edit_saving_transaction.html",
        trx=trx,
        accounts=accounts
    )


@bp.route("/saving-transaction/delete/<id>")
@login_required
def delete_saving_transaction(id):

    trx = mongo.db.saving_transactions.find_one({
        "_id": ObjectId(id),
        "user_id": ObjectId(current_user.id)
    })

    if not trx:
        flash("Transaction not found.", "danger")
        return redirect(url_for("main.saving_transaction_list"))

    amount = float(trx["amount"])
    account_id = trx["account_id"]
    saving_id = trx["saving_id"]

    # Reverse balances
    if trx["transaction_type"] == "deposit":

        mongo.db.accounts.update_one(
            {"_id": account_id},
            {"$inc": {"balance": amount}}
        )

        mongo.db.savings.update_one(
            {"_id": saving_id},
            {"$inc": {"current_balance": -amount}}
        )

    else:

        mongo.db.accounts.update_one(
            {"_id": account_id},
            {"$inc": {"balance": -amount}}
        )

        mongo.db.savings.update_one(
            {"_id": saving_id},
            {"$inc": {"current_balance": amount}}
        )

    mongo.db.saving_transactions.delete_one({
        "_id": ObjectId(id)
    })

    flash("Transaction deleted successfully.", "success")

    return redirect(url_for("main.saving_transaction_list"))





#---------------------------------------------------
#---- Route: 70 | Dashboard - Backend Template -----
#---------------------------------------------------
@bp.route("/logout")
def logout():
    if current_user.is_authenticated:

        # Log the logout action
       

        # Only log out from Flask-Login
        logout_user()

        # ✅ Do NOT clear session or delete DB session yet
        # session.clear()  <-- remove this
        # db.session.delete(user_session)  <-- remove this

        # Flash message
        flash("You have been logged out! Your session record remains for inspection.", "success")

    # Clear remember_token cookie to prevent auto-login
    resp = make_response(redirect(url_for("main.index")))
    resp.set_cookie("remember_token", "", expires=0)
    return resp









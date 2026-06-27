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

from app.modal import Category, User, UserRole


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
@bp.route('/', methods=['GET'])
def index():

   
    return render_template(
        "frontend/home/index.html",
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

    # ❌ role guard
    if current_user.role not in ['superadmin', 'admin']:
        return abort(403)

  

    
    return render_template(
        "backend/home/dashbaord.html",
        user=current_user,
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









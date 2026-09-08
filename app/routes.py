
# -U google-genai 
# python-dotenv

# ============================================================
# GEMINI AI ASSISTANT
# MONGODB-AWARE VERSION
# ============================================================

from flask import request, jsonify
from flask_login import login_required, current_user

from bson import ObjectId
from datetime import datetime, timedelta

import os

from google import genai
from google.genai import types


# ============================================================
# GEMINI CONFIGURATION
# ============================================================



# ============================================================
# GEMINI CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.7-flash"
)

gemini_client = None

if GEMINI_API_KEY:

    try:

        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )

    except Exception as e:

        print(
            "GEMINI CLIENT INIT ERROR:",
            repr(e)
        )

        gemini_client = None


# ============================================================
# AI SAFE FLOAT
# ============================================================

def ai_safe_float(value, default=0.0):

    try:

        if value is None:
            return default

        if isinstance(value, bool):
            return default

        return float(value)

    except Exception:

        return default


# ============================================================
# AI OBJECT ID
# ============================================================

def ai_to_object_id(value):

    try:

        if isinstance(value, ObjectId):
            return value

        if value is None:
            return None

        value = str(value).strip()

        if not value:
            return None

        if ObjectId.is_valid(value):

            return ObjectId(value)

    except Exception:
        pass

    return None


# ============================================================
# CURRENT USER ID
# ============================================================

def ai_get_current_user_id():

    try:

        if not current_user:

            return None

        user_id = getattr(
            current_user,
            "id",
            None
        )

        if not user_id:

            user_id = getattr(
                current_user,
                "get_id",
                lambda: None
            )()

        if not user_id:

            return None

        return str(user_id)

    except Exception:

        return None


# ============================================================
# USER IDS
#
# MongoDB may contain:
#
# user_id: ObjectId(...)
#
# OR
#
# user_id: "ObjectId string"
#
# ============================================================

def ai_get_user_ids():

    user_id = ai_get_current_user_id()

    if not user_id:
        return []

    ids = []

    # String
    ids.append(str(user_id))

    # ObjectId
    object_id = ai_to_object_id(user_id)

    if object_id:

        ids.append(object_id)

    # Remove duplicates
    unique_ids = []

    for item in ids:

        if item not in unique_ids:

            unique_ids.append(item)

    return unique_ids


# ============================================================
# SAFE TEXT
# ============================================================

def ai_clean_text(value):

    if value is None:
        return ""

    try:

        value = str(value)

    except Exception:

        return ""

    value = value.strip()

    # Remove excessive whitespace
    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value[:10000]


# ============================================================
# DATETIME → STRING
# ============================================================

def ai_date_to_string(value):

    if value is None:

        return None

    try:

        if isinstance(value, datetime):

            return value.isoformat()

        if isinstance(value, date):

            return value.isoformat()

        return str(value)

    except Exception:

        return str(value)


# ============================================================
# DATETIME FORMAT
# ============================================================

def ai_format_datetime(value):

    if not value:

        return None

    try:

        if isinstance(value, datetime):

            dt = value

        else:

            text = str(value).strip()

            if text.endswith("Z"):

                text = text[:-1] + "+00:00"

            dt = datetime.fromisoformat(
                text
            )

        # UTC
        if dt.tzinfo is not None:

            dt = dt.astimezone(
                timezone.utc
            )

        return dt.strftime(
            "%d %B %Y, %I:%M %p UTC"
        )

    except Exception:

        return str(value)


# ============================================================
# SAFE JSON
# ============================================================

def ai_json(value):

    try:

        return json.dumps(
            value,
            ensure_ascii=False,
            default=str
        )

    except Exception:

        return "{}"


# ============================================================
# GET REAL CURRENT USER FROM MONGODB
# ============================================================

def ai_get_real_current_user():

    try:

        user_id = ai_get_current_user_id()

        if not user_id:

            return None

        object_id = ai_to_object_id(
            user_id
        )

        projection = {

            "password": 0,

            "password_hash": 0,

            "reset_token": 0,

            "reset_otp": 0,

            "otp": 0,

            "otp_code": 0,

            "session_token": 0,

            "api_key": 0,

            "secret_key": 0

        }

        user = None

        # ----------------------------------------------------
        # OBJECT ID
        # ----------------------------------------------------

        if object_id:

            user = mongo.db.users.find_one(

                {
                    "_id": object_id
                },

                projection
            )

        # ----------------------------------------------------
        # STRING FALLBACK
        # ----------------------------------------------------

        if not user:

            user = mongo.db.users.find_one(

                {
                    "_id": user_id
                },

                projection
            )

        return user

    except Exception as e:

        print(
            "AI USER PROFILE ERROR:",
            repr(e)
        )

        return None

# ============================================================
# USER PROFILE
# ============================================================

def ai_get_user_profile():

    user = ai_get_real_current_user()

    if not user:

        return {}

    return {

        "id":
            str(
                user.get("_id", "")
            ),

        "fullname":
            user.get(
                "fullname"
            ),

        "username":
            user.get(
                "username"
            ),

        "email":
            user.get(
                "email"
            ),

        "role":
            user.get(
                "role"
            ),

        "status":
            user.get(
                "status"
            ),

        # IMPORTANT:
        # Account creation date
        "created_at":
            ai_date_to_string(
                user.get(
                    "created_at"
                )
            ),

        "created_at_formatted":
            ai_format_datetime(
                user.get(
                    "created_at"
                )
            ),

        "updated_at":
            ai_date_to_string(
                user.get(
                    "updated_at"
                )
            ),

        "city":
            user.get(
                "city"
            ),

        "country":
            user.get(
                "country"
            ),

        "state":
            user.get(
                "state"
            ),

        "phone":
            user.get(
                "phone"
            ),

        "address":
            user.get(
                "address"
            ),

        "bio":
            user.get(
                "bio"
            ),

        "gender":
            user.get(
                "gender"
            ),

        "auth_status":
            user.get(
                "auth_status"
            ),

        "last_active":
            ai_date_to_string(
                user.get(
                    "last_active"
                )
            ),

        "last_seen":
            ai_date_to_string(
                user.get(
                    "last_seen"
                )
            ),

        "login_time":
            ai_date_to_string(
                user.get(
                    "login_time"
                )
            )
    }

# ============================================================
# GET MAAREYE OWNER / SUPERADMIN
# ============================================================

def ai_get_owner():

    try:

        # ====================================================
        # 1. SUPERADMIN FIRST
        # ====================================================

        owner = mongo.db.users.find_one(

            {
                "role": {
                    "$regex": "^superadmin$",
                    "$options": "i"
                },

                "status": True
            },

            {
                "fullname": 1,
                "username": 1,
                "email": 1,
                "phone": 1,
                "phone_number": 1,
                "mobile": 1,
                "mobile_number": 1,
                "telephone": 1,
                "contact": 1,
                "contact_number": 1
            }

        )

        # ====================================================
        # 2. IF NOT FOUND, TRY ACTIVE SUPERADMIN WITHOUT
        #    STATUS FILTER
        # ====================================================

        if not owner:

            owner = mongo.db.users.find_one(

                {
                    "role": {
                        "$regex": "^superadmin$",
                        "$options": "i"
                    }
                },

                {
                    "fullname": 1,
                    "username": 1,
                    "email": 1,
                    "phone": 1,
                    "phone_number": 1,
                    "mobile": 1,
                    "mobile_number": 1,
                    "telephone": 1,
                    "contact": 1,
                    "contact_number": 1
                }

            )

        # ====================================================
        # NO SUPERADMIN
        # ====================================================

        if not owner:

            return {}

        # ====================================================
        # PHONE FALLBACKS
        # ====================================================

        phone = (

            owner.get("phone")

            or

            owner.get("phone_number")

            or

            owner.get("mobile")

            or

            owner.get("mobile_number")

            or

            owner.get("telephone")

            or

            owner.get("contact")

            or

            owner.get("contact_number")

        )

        return {

            "name":
                owner.get(
                    "fullname"
                )

                or

                owner.get(
                    "username"
                )

                or

                "Maareye Owner",

            "username":
                owner.get(
                    "username"
                ),

            "email":
                owner.get(
                    "email"
                ),

            "phone":
                phone

        }

    except Exception as e:

        print(
            "AI OWNER ERROR:",
            repr(e)
        )

        return {}


# ============================================================
# OWNER CONTACT TEXT
# ============================================================

def ai_owner_contact_text(owner):

    owner = owner or {}

    name = (
        owner.get("name")
        or "Maareye Owner"
    )

    email = (
        owner.get("email")
        or "Not available"
    )

    phone = (
        owner.get("phone")
        or "Not available"
    )

    return f"""
Maareye Owner / Superadmin:

Name: {name}
Email: {email}
Phone: {phone}

Registration:
https://maareye.vercel.app/register

Login:
https://maareye.vercel.app/login
"""

# ============================================================
# FINANCIAL CONTEXT
# ============================================================

def ai_get_financial_context():

    try:

        user_ids = ai_get_user_ids()

        if not user_ids:

            return {}

        user_query = {

            "user_id": {
                "$in": user_ids
            }

        }

        # ====================================================
        # ACCOUNTS
        # ====================================================

        accounts = list(

            mongo.db.accounts.find(
                user_query
            )
            .sort(
                "_id",
                -1
            )
            .limit(100)
        )

        # ====================================================
        # TRANSACTIONS
        # ====================================================

        transactions = list(

            mongo.db.transactions.find(
                user_query
            )
            .sort(
                "date",
                -1
            )
            .limit(500)
        )

        # ====================================================
        # SAVINGS
        # ====================================================

        savings = list(

            mongo.db.savings.find(
                user_query
            )
            .sort(
                "_id",
                -1
            )
            .limit(100)
        )

        # ====================================================
        # SAVING TRANSACTIONS
        # ====================================================

        saving_transactions = list(

            mongo.db.saving_transactions.find(
                user_query
            )
            .sort(
                "date",
                -1
            )
            .limit(300)
        )

        # ====================================================
        # ACCOUNT TRANSFERS
        # ====================================================

        account_transfers = list(

            mongo.db.account_transfers.find(
                user_query
            )
            .sort(
                "created_at",
                -1
            )
            .limit(300)
        )

        # ====================================================
        # PERSON OPENINGS
        # ====================================================

        person_openings = list(

            mongo.db.person_opening_transactions.find(
                user_query
            )
            .sort(
                "date",
                -1
            )
            .limit(300)
        )

        # ====================================================
        # ACCOUNT SUMMARY
        # ====================================================

        total_account_balance = 0.0

        account_summary = []

        for account in accounts:

            balance = ai_safe_float(
                account.get(
                    "balance"
                )
            )

            total_account_balance += balance

            account_summary.append({

                "id":
                    str(
                        account.get("_id")
                    ),

                "name":
                    account.get(
                        "name"
                    ),

                "type":
                    account.get(
                        "type"
                    ),

                "balance":
                    balance,

                "currency":
                    account.get(
                        "currency",
                        "USD"
                    ),

                "status":
                    account.get(
                        "status"
                    )

            })

        # ====================================================
        # TRANSACTION SUMMARY
        # ====================================================

        total_income = 0.0

        total_expense = 0.0

        income_count = 0

        expense_count = 0

        income_by_category = {}

        expense_by_category = {}

        transaction_summary = []

        for tx in transactions:

            amount = ai_safe_float(
                tx.get(
                    "amount"
                )
            )

            tx_type = str(

                tx.get(
                    "transaction_type",
                    ""
                )

            ).strip().lower()

            category = (
                tx.get(
                    "category"
                )
                or
                "Uncategorized"
            )

            if tx_type == "income":

                total_income += amount

                income_count += 1

                income_by_category[category] = (

                    income_by_category.get(
                        category,
                        0.0
                    )
                    + amount

                )

            elif tx_type == "expense":

                total_expense += amount

                expense_count += 1

                expense_by_category[category] = (

                    expense_by_category.get(
                        category,
                        0.0
                    )
                    + amount

                )

            transaction_summary.append({

                "id":
                    str(
                        tx.get("_id")
                    ),

                "type":
                    tx_type,

                "amount":
                    amount,

                "category":
                    category,

                "item":
                    tx.get(
                        "item"
                    ),

                "description":
                    tx.get(
                        "description"
                    ),

                "person_name":
                    tx.get(
                        "person_name"
                    ),

                "note":
                    tx.get(
                        "note"
                    ),

                "date":
                    ai_date_to_string(
                        tx.get(
                            "date"
                        )
                    ),

                "status":
                    tx.get(
                        "status"
                    ),

                "reference_no":
                    tx.get(
                        "reference_no"
                    )

            })

        # ====================================================
        # SAVINGS SUMMARY
        # ====================================================

        total_savings_balance = 0.0

        total_savings_target = 0.0

        savings_summary = []

        for saving in savings:

            current_balance = ai_safe_float(

                saving.get(
                    "current_balance"
                )

            )

            target_amount = ai_safe_float(

                saving.get(
                    "target_amount"
                )

            )

            total_savings_balance += (
                current_balance
            )

            total_savings_target += (
                target_amount
            )

            savings_summary.append({

                "id":
                    str(
                        saving.get("_id")
                    ),

                "title":
                    saving.get(
                        "title"
                    ),

                "target_amount":
                    target_amount,

                "current_balance":
                    current_balance,

                "remaining_amount":
                    ai_safe_float(
                        saving.get(
                            "remaining_amount"
                        )
                    ),

                "progress":
                    ai_safe_float(
                        saving.get(
                            "progress"
                        )
                    ),

                "daily_required":
                    ai_safe_float(
                        saving.get(
                            "daily_required"
                        )
                    ),

                "weekly_required":
                    ai_safe_float(
                        saving.get(
                            "weekly_required"
                        )
                    ),

                "monthly_required":
                    ai_safe_float(
                        saving.get(
                            "monthly_required"
                        )
                    ),

                "status":
                    saving.get(
                        "status"
                    )

            })

        # ====================================================
        # NET
        # ====================================================

        net_income = (
            total_income
            - total_expense
        )

        # ====================================================
        # TOTAL WEALTH
        # ====================================================

        total_wealth = (

            total_account_balance

            +

            total_savings_balance

        )

        # ====================================================
        # SAVING TRANSACTIONS
        # ====================================================

        saving_transaction_summary = []

        for tx in saving_transactions:

            saving_transaction_summary.append({

                "id":
                    str(
                        tx.get("_id")
                    ),

                "saving_id":
                    str(
                        tx.get(
                            "saving_id"
                        )
                    )
                    if tx.get(
                        "saving_id"
                    )
                    else None,

                "account_id":
                    str(
                        tx.get(
                            "account_id"
                        )
                    )
                    if tx.get(
                        "account_id"
                    )
                    else None,

                "type":
                    tx.get(
                        "transaction_type"
                    ),

                "amount":
                    ai_safe_float(
                        tx.get(
                            "amount"
                        )
                    ),

                "description":
                    tx.get(
                        "description"
                    ),

                "note":
                    tx.get(
                        "note"
                    ),

                "date":
                    ai_date_to_string(
                        tx.get(
                            "date"
                        )
                    ),

                "status":
                    tx.get(
                        "status"
                    ),

                "reference_no":
                    tx.get(
                        "reference_no"
                    )

            })

        # ====================================================
        # ACCOUNT TRANSFERS
        # ====================================================

        transfer_summary = []

        for transfer in account_transfers:

            transfer_summary.append({

                "id":
                    str(
                        transfer.get("_id")
                    ),

                "transfer_type":
                    transfer.get(
                        "transfer_type"
                    ),

                "from_account":
                    transfer.get(
                        "from_account_name"
                    )
                    or
                    str(
                        transfer.get(
                            "from_account",
                            ""
                        )
                    ),

                "to_account":
                    transfer.get(
                        "to_account_name"
                    )
                    or
                    str(
                        transfer.get(
                            "to_account",
                            ""
                        )
                    ),

                "amount":
                    ai_safe_float(
                        transfer.get(
                            "amount"
                        )
                    ),

                "currency":
                    transfer.get(
                        "currency",
                        "USD"
                    ),

                "status":
                    transfer.get(
                        "status"
                    ),

                "reference":
                    transfer.get(
                        "reference"
                    ),

                "created_at":
                    ai_date_to_string(
                        transfer.get(
                            "created_at"
                        )
                    )

            })

        # ====================================================
        # PERSON OPENINGS
        # ====================================================

        person_opening_summary = []

        person_totals = {}

        for opening in person_openings:

            person_name = (

                opening.get(
                    "person_name"
                )

                or

                "Unknown Person"

            )

            transaction_type = (

                opening.get(
                    "transaction_type"
                )

                or

                opening.get(
                    "type"
                )

                or

                ""

            )

            transaction_type = (
                str(
                    transaction_type
                )
                .strip()
                .lower()
            )

            amount = ai_safe_float(
                opening.get(
                    "amount"
                )
            )

            if person_name not in person_totals:

                person_totals[person_name] = {

                    "income": 0.0,

                    "expense": 0.0

                }

            if transaction_type == "income":

                person_totals[
                    person_name
                ]["income"] += amount

            elif transaction_type == "expense":

                person_totals[
                    person_name
                ]["expense"] += amount

            person_opening_summary.append({

                "id":
                    str(
                        opening.get(
                            "_id"
                        )
                    ),

                "person_name":
                    person_name,

                "transaction_type":
                    transaction_type,

                "amount":
                    amount,

                "item":
                    opening.get(
                        "item"
                    ),

                "description":
                    opening.get(
                        "description"
                    ),

                "note":
                    opening.get(
                        "note"
                    ),

                "date":
                    ai_date_to_string(
                        opening.get(
                            "date"
                        )
                    ),

                "reference_no":
                    opening.get(
                        "reference_no"
                    )

            })

        # ====================================================
        # PERSON SUMMARY
        # ====================================================

        person_summary = []

        for name, values in person_totals.items():

            person_summary.append({

                "person_name":
                    name,

                "income":
                    values["income"],

                "expense":
                    values["expense"],

                "net":
                    (
                        values["income"]
                        -
                        values["expense"]
                    )

            })

        # ====================================================
        # RECENT TRANSACTIONS
        # ====================================================

        recent_transactions = (
            transaction_summary[:30]
        )

        recent_saving_transactions = (
            saving_transaction_summary[:20]
        )

        recent_transfers = (
            transfer_summary[:20]
        )

        # ====================================================
        # FINAL CONTEXT
        # ====================================================

        return {

            "summary": {

                "total_account_balance":
                    round(
                        total_account_balance,
                        2
                    ),

                "total_savings_balance":
                    round(
                        total_savings_balance,
                        2
                    ),

                "total_savings_target":
                    round(
                        total_savings_target,
                        2
                    ),

                "total_income":
                    round(
                        total_income,
                        2
                    ),

                "total_expense":
                    round(
                        total_expense,
                        2
                    ),

                "net_income":
                    round(
                        net_income,
                        2
                    ),

                "total_wealth":
                    round(
                        total_wealth,
                        2
                    ),

                "account_count":
                    len(accounts),

                "transaction_count":
                    len(transactions),

                "income_count":
                    income_count,

                "expense_count":
                    expense_count,

                "savings_count":
                    len(savings),

                "saving_transaction_count":
                    len(
                        saving_transactions
                    ),

                "transfer_count":
                    len(
                        account_transfers
                    ),

                "person_opening_count":
                    len(
                        person_openings
                    )

            },

            "accounts":
                account_summary,

            "savings":
                savings_summary,

            "income_by_category":
                income_by_category,

            "expense_by_category":
                expense_by_category,

            "recent_transactions":
                recent_transactions,

            "recent_saving_transactions":
                recent_saving_transactions,

            "recent_transfers":
                recent_transfers,

            "persons":
                person_summary,

            "person_opening_transactions":
                person_opening_summary[:50]

        }

    except Exception as e:

        print(
            "AI FINANCIAL CONTEXT ERROR:",
            repr(e)
        )

        return {}


# ============================================================
# CHAT HISTORY
# ============================================================

def ai_build_chat_history(history):

    if not isinstance(
        history,
        list
    ):

        return []

    safe_history = []

    for item in history[-20:]:

        if not isinstance(
            item,
            dict
        ):

            continue

        role = str(

            item.get(
                "role",
                ""
            )

        ).strip().lower()

        content = ai_clean_text(

            item.get(
                "content"
            )

            or

            item.get(
                "message"
            )

            or

            item.get(
                "text"
            )

        )

        if role not in (
            "user",
            "assistant"
        ):

            continue

        if not content:

            continue

        safe_history.append({

            "role":
                role,

            "content":
                content[:4000]

        })

    return safe_history


# ============================================================
# AI SYSTEM INSTRUCTION
# ============================================================

def ai_build_system_instruction(
    user_profile_result=None,
    financial_context=None,
    owner=None,
    is_logged_in=False
):

    user_profile_result = (
        user_profile_result
        or {}
    )

    financial_context = (
        financial_context
        or {}
    )

    owner = (
        owner
        or {}
    )

    owner_contact = (
        ai_owner_contact_text(
            owner
        )
    )

    # ========================================================
    # LOGGED IN
    # ========================================================

    if is_logged_in:

        user_mode = """

The user IS LOGGED IN.

The supplied profile belongs to the authenticated current user.

The supplied financial data also belongs ONLY to that user.

You may answer questions about:

- profile
- fullname
- username
- email
- account creation date
- accounts
- balances
- income
- expenses
- transactions
- categories
- savings
- saving transactions
- transfers
- persons
- reports
- financial summaries

Use ONLY the MongoDB context supplied in the prompt.

Never invent missing information.

"""

    # ========================================================
    # GUEST
    # ========================================================

    else:

        user_mode = """

The user is NOT LOGGED IN.

There is NO private user financial context.

You MUST NOT claim to know the visitor's:

- account balance
- transactions
- income
- expenses
- savings
- accounts
- reports
- personal financial data

You MUST NOT use another user's information.

You CAN explain Maareye generally.

You can explain:

- how Maareye works
- how to create an account
- how to login
- how to add accounts
- how to record income
- how to record expenses
- how savings work
- how transfers work
- how Persons Ledger works
- how reports work
- how to manage finances

If the visitor asks about their own account data,
tell them they need to login first.

Registration:
https://maareye.vercel.app/register

Login:
https://maareye.vercel.app/login

"""

    return f"""

You are the official AI Assistant for Maareye Expense
Management System.

You are helpful, accurate, friendly and professional.

============================================================
CURRENT USER MODE
============================================================

{user_mode}

============================================================
OWNER / SUPPORT
============================================================

{owner_contact}

If the user asks for:

- owner
- superadmin
- administrator
- support
- developer
- technical support
- contact
- management
- help from owner

Use ONLY the owner information provided above.

Never invent owner information.

============================================================
SECURITY
============================================================

NEVER reveal:

- password
- password hash
- OTP
- reset token
- session token
- API key
- secret key
- authentication credentials
- private security information

============================================================
ACCOUNT CREATION DATE
============================================================

If the logged-in user asks:

"When did I create my account?"
"Goormee account-kayga furmay?"
"Goormee account sameystay?"

Use:

profile.created_at

This MUST come from users.created_at.

DO NOT use:

- first transaction date
- first saving date
- first transfer date
- first financial activity

============================================================
FINANCIAL DEFINITIONS
============================================================

Account balance:

summary.total_account_balance

Savings balance:

summary.total_savings_balance

Total wealth:

summary.total_wealth

Total income:

summary.total_income

Total expense:

summary.total_expense

Net income:

summary.net_income

============================================================
IMPORTANT
============================================================

If a value is not available in MongoDB context:

Say that the information is not available.

Do not guess.

Do not invent numbers.

============================================================
LANGUAGE
============================================================

If the user asks in Somali, answer in Somali.

If the user asks in English, answer in English.

============================================================
MAAREYE
============================================================

Maareye is a financial management system for managing:

- Accounts
- Income
- Expenses
- Transactions
- Savings
- Transfers
- Persons Ledger
- Reports

Explain system usage clearly.

"""

# ============================================================
# BUILD AI PROMPT
# ============================================================

def ai_build_prompt(
    message,
    history
):

    safe_history = (
        ai_build_chat_history(
            history
        )
    )

    history_text = ""

    if safe_history:

        history_parts = []

        for item in safe_history:

            role = item.get(
                "role"
            )

            content = item.get(
                "content"
            )

            history_parts.append(

                f"{role.upper()}: {content}"

            )

        history_text = "\n".join(
            history_parts
        )

    return f"""

============================================================
CONVERSATION HISTORY
============================================================

{history_text}

============================================================
CURRENT USER QUESTION
============================================================

{message}

============================================================
INSTRUCTIONS
============================================================

Answer the current question accurately.

Use the supplied MongoDB context when the user is logged in.

Do not invent information.

If the user is not logged in and asks for private financial
information, explain that they need to login first.

If they need an account, explain registration.

If they need support or the owner, use the supplied owner
contact information.

"""

# ============================================================
# MAAREYE AI ASSISTANT
# ============================================================
#
# IMPORTANT:
#
# DO NOT USE @login_required
#
# Guest users are allowed to use the AI.
#
# Logged-in users receive their own MongoDB data.
#
# ============================================================

@bp.route(
    "/ai-assistant",
    methods=["POST"]
)
def ai_assistant():

    try:

        # ====================================================
        # REQUEST
        # ====================================================

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        message = ai_clean_text(
            data.get(
                "message"
            )
        )

        history = (
            data.get(
                "history",
                []
            )
            or []
        )

        if not message:

            return jsonify({

                "success": False,

                "answer":
                    "Fadlan su'aashaada qor."

            }), 400

        # ====================================================
        # GEMINI API KEY
        # ====================================================

        if not GEMINI_API_KEY:

            return jsonify({

                "success": False,

                "answer":
                    "Gemini API key lama dejin. "
                    "Fadlan owner-ka ha configure-gareeyo "
                    "AI service-ka."

            }), 500

        # ====================================================
        # GEMINI CLIENT
        # ====================================================

        if not gemini_client:

            return jsonify({

                "success": False,

                "answer":
                    "AI service-ka hadda lama heli karo. "
                    "Fadlan isku day mar kale."

            }), 500

        # ====================================================
        # LOGIN STATUS
        # ====================================================

        is_logged_in = (

            current_user is not None

            and

            getattr(
                current_user,
                "is_authenticated",
                False
            )

        )

        # ====================================================
        # DEFAULT CONTEXT
        # ====================================================

        user_profile_result = {}

        financial_context = {}

        # ====================================================
        # LOGGED-IN USER DATA
        # ====================================================

        if is_logged_in:

            # ------------------------------------------------
            # VERIFY CURRENT USER
            # ------------------------------------------------

            current_user_id = (
                ai_get_current_user_id()
            )

            if not current_user_id:

                return jsonify({

                    "success": False,

                    "answer":
                        "Account-kaaga lama aqoonsan. "
                        "Fadlan logout kadib mar kale login samee."

                }), 401

            # ------------------------------------------------
            # REAL MONGODB PROFILE
            # ------------------------------------------------

            user_profile_result = (
                ai_get_user_profile()
            )

            # ------------------------------------------------
            # REAL FINANCIAL DATA
            # ------------------------------------------------

            financial_context = (
                ai_get_financial_context()
            )

        # ====================================================
        # GUEST
        # ====================================================

        else:

            user_profile_result = {}

            financial_context = {}

        # ====================================================
        # OWNER
        # ====================================================

        owner = (
            ai_get_owner()
        )

        # ====================================================
        # SYSTEM INSTRUCTION
        # ====================================================

        system_instruction = (

            ai_build_system_instruction(

                user_profile_result,

                financial_context,

                owner,

                is_logged_in=is_logged_in

            )

        )

        # ====================================================
        # PROMPT
        # ====================================================

        prompt = ai_build_prompt(

            message,

            history

        )

        # ====================================================
        # ADD REAL CONTEXT TO PROMPT
        # ====================================================

        context_text = f"""

============================================================
AUTHENTICATION STATUS
============================================================

Logged in:
{is_logged_in}

============================================================
USER PROFILE
============================================================

{ai_json(user_profile_result)}

============================================================
FINANCIAL CONTEXT
============================================================

{ai_json(financial_context)}

============================================================
OWNER CONTACT
============================================================

{ai_json(owner)}

"""

        final_prompt = (

            prompt

            +

            "\n\n"

            +

            context_text

        )

        # ====================================================
        # GEMINI REQUEST
        # ====================================================

        response = (

            gemini_client

            .models

            .generate_content(

                model=GEMINI_MODEL,

                contents=final_prompt,

                config=types.GenerateContentConfig(

                    system_instruction=
                        system_instruction,

                    temperature=0.15,

                    max_output_tokens=2048

                )

            )

        )

        # ====================================================
        # RESPONSE TEXT
        # ====================================================

        answer = ""

        if response:

            answer = (

                getattr(
                    response,
                    "text",
                    None
                )

                or ""

            ).strip()

        # ====================================================
        # EMPTY RESPONSE
        # ====================================================

        if not answer:

            answer = (

                "Waan ka xumahay, jawaab lama helin "
                "hadda. Fadlan isku day mar kale."

            )

        # ====================================================
        # SUCCESS
        # ====================================================

        return jsonify({

            "success": True,

            "answer": answer,

            "model":
                GEMINI_MODEL,

            "logged_in":
                bool(
                    is_logged_in
                )

        }), 200

    # ========================================================
    # EXCEPTION
    # ========================================================

    except Exception as e:

        error_text = str(
            e
        )

        error_lower = (
            error_text.lower()
        )

        print(
            "================================================"
        )

        print(
            "MAAREYE AI ASSISTANT ERROR"
        )

        print(
            repr(e)
        )

        print(
            "================================================"
        )

        # ====================================================
        # QUOTA
        # ====================================================

        if (

            "429"
            in error_text

            or

            "quota"
            in error_lower

            or

            "resource exhausted"
            in error_lower

            or

            "rate limit"
            in error_lower

        ):

            return jsonify({

                "success": False,

                "answer":
                    "AI Assistant-ka wuxuu gaaray "
                    "xadka isticmaalka hadda. "
                    "Fadlan isku day wax yar kadib."

            }), 429

        # ====================================================
        # AUTHENTICATION
        # ====================================================

        if (

            "api key"
            in error_lower

            or

            "unauthenticated"
            in error_lower

            or

            "permission denied"
            in error_lower

            or

            "authentication"
            in error_lower

        ):

            return jsonify({

                "success": False,

                "answer":
                    "AI configuration-ka ayaa cilad qaba. "
                    "Fadlan la xiriir owner-ka Maareye."

            }), 500

        # ====================================================
        # DATABASE
        # ====================================================

        if (

            "mongodb"
            in error_lower

            or

            "mongo"
            in error_lower

            or

            "objectid"
            in error_lower

        ):

            return jsonify({

                "success": False,

                "answer":
                    "Xogta Maareye ayaa cilad ku timid. "
                    "Fadlan isku day mar kale."

            }), 500

        # ====================================================
        # GENERAL ERROR
        # ====================================================

        return jsonify({

            "success": False,

            "answer":
                "Waan ka xumahay, cilad ayaa ka dhacday "
                "AI Assistant-ka. Fadlan isku day mar kale."

        }), 500


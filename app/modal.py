from decimal import Decimal
import enum
from flask_login import UserMixin
from datetime import datetime, timedelta
from app import now_eat



# 1. Qeexidda Enum-ka
class UserRole(enum.Enum):
    superadmin = "superadmin"
    admin = "admin"
    user = "user"




class User(UserMixin):
    def __init__(self, data):
        self.data = data or {}

        self.id = str(self.data.get("_id"))
        self.username = self.data.get("username")
        self.fullname = self.data.get("fullname")
        self.email = self.data.get("email")
        self.password = self.data.get("password")

        # Role system (Mongo style)
        self.role = self.data.get("role", "user")
        self.role_id = self.data.get("role_id")  # ObjectId string if using reference

        # Basic info
        self.phone = self.data.get("phone")
        self.country = self.data.get("country")
        self.city = self.data.get("city")
        self.state = self.data.get("state")
        self.address = self.data.get("address")
        self.bio = self.data.get("bio")
        self.photo = self.data.get("photo")
        self.gender = self.data.get("gender")
        self.photo_visibility = self.data.get("photo_visibility", "everyone")

        self.status = self.data.get("status", True)

        # Device info
        self.device = self.data.get("device")
        self.browser = self.data.get("browser")
        self.platform = self.data.get("platform")
        self.device_name = self.data.get("device_name")
        self.interface_name = self.data.get("interface_name")

        # Security
        self.is_verified = self.data.get("is_verified", False)
        self.auth_status = self.data.get("auth_status", "logout")
        self.session_token = self.data.get("session_token")
        self.login_time = self.data.get("login_time")
        self.last_seen = self.data.get("last_seen")

        self.phone_verified = self.data.get("phone_verified", False)
        self.two_factor_enabled = self.data.get("two_factor_enabled", False)
        self.two_factor_code = self.data.get("two_factor_code")
        self.two_factor_expires_at = self.data.get("two_factor_expires_at")

        self.last_login_ip = self.data.get("last_login_ip")
        self.remember_token = self.data.get("remember_token")
        self.failed_login_attempts = self.data.get("failed_login_attempts", 0)

        self.auth_provider = self.data.get("auth_provider", "local")
        self.last_active = self.data.get("last_active")

        # Socials
        self.facebook = self.data.get("facebook")
        self.twitter = self.data.get("twitter")
        self.google = self.data.get("google")
        self.whatsapp = self.data.get("whatsapp")
        self.instagram = self.data.get("instagram")
        self.github = self.data.get("github")
        self.github_id = self.data.get("github_id")

        # Timestamps
        self.created_at = self.data.get("created_at")
        self.updated_at = self.data.get("updated_at")

        # Embedded relationships (Mongo style)
        self.user_logs = self.data.get("user_logs", [])
        self.sessions = self.data.get("sessions", [])
        self.user_permissions = self.data.get("user_permissions", [])

        self.patient_appointments = self.data.get("patient_appointments", [])
        self.doctor_appointments = self.data.get("doctor_appointments", [])

    # Flask-Login required
    def get_id(self):
        return self.id

    @property
    def is_active(self):
        return self.status is True

    @property
    def permissions(self):
        return [p.get("permission") for p in self.user_permissions]

    def to_dict(self):
        return self.data

    def __repr__(self):
        return f"<User {self.username}>"



class Category:
    def __init__(self, data):
        self.data = data or {}
        self.id = str(self.data.get("_id"))
        self.user_id = str(self.data.get("user_id"))
        
        # Magaca Qaybta Weyn (Main Category)
        self.name = self.data.get("name") # Tusaale: "Waxbarasho"
        self.slug = self.data.get("slug")
        
        # Halkaan ayaan ku kaydsanaynaa xubnaha hoose (Dynamic Items)
        self.items = self.data.get("items", []) # List of strings: ["Qalin", "Laptop", "Book"]
        
        self.type = self.data.get("type", "expense")
        self.status = self.data.get("status", True)
        
        # Timestamps
        self.created_at = self.data.get("created_at")
        self.updated_at = self.data.get("updated_at")


    def add_item(self, item_name):
        """Si aad si dynamic ah ugu dartid item cusub"""
        if item_name not in self.items:
            self.items.append(item_name)
    
    def to_dict(self):
        return {
            "_id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "items": self.items,
            "type": self.type,
            "created_at": self.created_at,
            "expires_at": self.expires_at
        }



class Account:
    def __init__(self, data=None):
        self.data = data or {}

        self.id = str(self.data.get("_id"))
        self.user_id = str(self.data.get("user_id"))

        # Account Info
        self.name = self.data.get("name")          # Main Wallet, Bank, Cash
        self.type = self.data.get("type")          # cash, bank, mobile, savings

        # Balance
        self.balance = self.data.get("balance", 0)

        # Currency
        self.currency = self.data.get("currency", "USD")

        # Status
        self.status = self.data.get("status", True)

        # Timestamps
        self.created_at = self.data.get("created_at")
        self.updated_at = self.data.get("updated_at")

    def add(
        self,
        user_id,
        name,
        account_type="cash",
        balance=0,
        currency="USD",
        status=True
    ):
        self.user_id = str(user_id)
        self.name = name
        self.type = account_type
        self.balance = balance
        self.currency = currency
        self.status = status

        now = datetime.utcnow()
        self.created_at = now
        self.updated_at = now

        return self.to_dict()

    def update_balance(self, amount, operation="add"):
        """
        operation:
        - add → lacag ku dar
        - subtract → lacag ka jar
        """
        if operation == "add":
            self.balance += amount
        elif operation == "subtract":
            self.balance -= amount

        self.updated_at = datetime.utcnow()

        return self.balance

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "name": self.name,
            "type": self.type,
            "balance": self.balance,
            "currency": self.currency,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }



class Transaction:
    def __init__(self, data=None):
        self.data = data or {}

        self.id = str(self.data.get("_id"))
        self.user_id = str(self.data.get("user_id"))

        # Account
        self.account_id = self.data.get("account_id")

        # Transaction
        self.transaction_type = self.data.get("transaction_type")  # income | expense

        # Category
        self.category = self.data.get("category")
        self.item = self.data.get("item")

        # Amount
        self.amount = self.data.get("amount", 0)

        # Details
        self.description = self.data.get("description")
        self.note = self.data.get("note")

        # Optional reference number
        self.reference_no = self.data.get("reference_no")

        # Date
        self.date = self.data.get("date")

        self.status = self.data.get("status", True)

        # Timestamps
        self.created_at = self.data.get("created_at")
        self.updated_at = self.data.get("updated_at")

    def add(
        self,
        user_id,
        account_id,
        transaction_type,
        category,
        item,
        amount,
        description="",
        note="",
        date=None,
        status=True,
        reference_no=None
    ):
        self.user_id = str(user_id)
        self.account_id = account_id
        self.transaction_type = transaction_type
        self.category = category
        self.item = item
        self.amount = amount
        self.description = description
        self.note = note
        self.reference_no = reference_no
        self.date = date or datetime.utcnow()
        self.status = status

        now = datetime.utcnow()
        self.created_at = now
        self.updated_at = now

        return self.to_dict()

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "account_id": self.account_id,
            "transaction_type": self.transaction_type,
            "category": self.category,
            "item": self.item,
            "amount": self.amount,
            "description": self.description,
            "note": self.note,
            "reference_no": self.reference_no,
            "date": self.date,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }



class Saving:
    def __init__(self, data=None):
        self.data = data or {}

        self.id = str(self.data.get("_id"))
        self.user_id = str(self.data.get("user_id"))

        # Saving Goal
        self.title = self.data.get("title")
        self.description = self.data.get("description", "")

        self.target_amount = float(self.data.get("target_amount", 0))
        self.current_balance = float(self.data.get("current_balance", 0))

        # Source Account (Wallet/Bank)
        self.account_id = self.data.get("account_id")

        # Dates
        self.start_date = self.data.get("start_date")
        self.maturity_date = self.data.get("maturity_date")

        # Status
        self.status = self.data.get("status", "active")  # active | completed | paused

        # Timestamps
        self.created_at = self.data.get("created_at")
        self.updated_at = self.data.get("updated_at")

    def add(
        self,
        user_id,
        title,
        target_amount,
        account_id,
        start_date=None,
        maturity_date=None,
        description="",
        status="active"
    ):
        self.user_id = str(user_id)
        self.title = title
        self.description = description

        self.target_amount = float(target_amount)
        self.current_balance = 0.0

        self.account_id = account_id
        self.start_date = start_date or datetime.utcnow()
        self.maturity_date = maturity_date

        self.status = status

        now = datetime.utcnow()
        self.created_at = now
        self.updated_at = now

        return self.to_dict()

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "target_amount": self.target_amount,
            "current_balance": self.current_balance,
            "account_id": self.account_id,
            "start_date": self.start_date,
            "maturity_date": self.maturity_date,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }



class SavingTransaction:
    def __init__(self, data=None):
        self.data = data or {}

        self.id = str(self.data.get("_id"))
        self.user_id = str(self.data.get("user_id"))

        self.saving_id = self.data.get("saving_id")
        self.account_id = self.data.get("account_id")  # 🔥 IMPORTANT

        # deposit | withdrawal
        self.transaction_type = self.data.get("transaction_type")

        self.amount = float(self.data.get("amount", 0))  # 🔥 safer

        self.description = self.data.get("description", "")
        self.note = self.data.get("note", "")

        self.date = self.data.get("date")

        self.status = self.data.get("status", True)

        self.reference_no = self.data.get("reference_no")  # 🔥 tracking

        self.created_at = self.data.get("created_at")
        self.updated_at = self.data.get("updated_at")

    def add(
        self,
        user_id,
        saving_id,
        account_id,
        transaction_type,
        amount,
        description="",
        note="",
        date=None,
        status=True,
        reference_no=None
    ):
        self.user_id = str(user_id)
        self.saving_id = saving_id
        self.account_id = account_id
        self.transaction_type = transaction_type
        self.amount = float(amount)

        self.description = description
        self.note = note
        self.date = date or datetime.utcnow()
        self.status = status
        self.reference_no = reference_no

        now = datetime.utcnow()
        self.created_at = now
        self.updated_at = now

        return self.to_dict()

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "saving_id": self.saving_id,
            "account_id": self.account_id,
            "transaction_type": self.transaction_type,
            "amount": self.amount,
            "description": self.description,
            "note": self.note,
            "reference_no": self.reference_no,
            "date": self.date,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }



class Session:
    def __init__(self, data):
        self.data = data or {}

        self.id = str(self.data.get("_id"))
        self.user_id = str(self.data.get("user_id"))

        self.session_token = self.data.get("session_token")
        self.ip = self.data.get("ip")
        self.device = self.data.get("device")

        self.created_at = self.data.get("created_at", datetime.utcnow())
        self.expires_at = self.data.get(
            "expires_at",
            datetime.utcnow() + timedelta(days=7)
        )

    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    def is_active(self):
        return not self.is_expired()

    def to_dict(self):
        return {
            "_id": self.id,
            "user_id": self.user_id,
            "session_token": self.session_token,
            "ip": self.ip,
            "device": self.device,
            "created_at": self.created_at,
            "expires_at": self.expires_at
        }

    def __repr__(self):
        return f"<Session {self.session_token}>"













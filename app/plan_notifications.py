
"""
Maareeye Personal Plan Notifications
Email + Browser Web Push + Protected Cron
Timezone: Africa/Mogadishu
"""

from __future__ import annotations

import os
import json
import html
import hmac
import secrets

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId
from flask import Blueprint, abort, jsonify, request, current_app
from flask_login import current_user, login_required
from flask_mail import Message

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


TZ = ZoneInfo("Africa/Mogadishu")


# =========================================================
# HELPERS
# =========================================================

def _user_ids(user):
    raw = getattr(user, "id", None) or getattr(user, "_id", None)

    if raw is None:
        abort(403)

    text = str(raw)

    try:
        oid = raw if isinstance(raw, ObjectId) else ObjectId(text)
        return [oid, text], oid
    except Exception:
        return [text], text


def _owner_values(raw_owner):
    if raw_owner is None:
        return []

    values = [raw_owner, str(raw_owner)]

    try:
        oid = ObjectId(str(raw_owner))
        if oid not in values:
            values.append(oid)
    except Exception:
        pass

    return values


def _vapid_public_key():
    return (
        os.getenv("VAPID_PUBLIC_KEY")
        or current_app.config.get("VAPID_PUBLIC_KEY")
        or ""
    ).strip()


def _vapid_private_key():
    return (
        os.getenv("VAPID_PRIVATE_KEY")
        or current_app.config.get("VAPID_PRIVATE_KEY")
        or ""
    ).strip()


# =========================================================
# BLUEPRINT
# =========================================================

def create_plan_notifications_blueprint(mongo):

    bp = Blueprint(
        "plan_notifications",
        __name__,
        url_prefix="/plan/notifications"
    )

    def subscriptions():
        return mongo.db.push_subscriptions

    # -----------------------------------------------------
    # PUBLIC VAPID KEY
    # -----------------------------------------------------

    @bp.get("/public-key")
    @login_required
    def public_key():

        key = _vapid_public_key()

        if not key:
            return jsonify({
                "success": False,
                "error": "VAPID_PUBLIC_KEY lama dejin."
            }), 503

        return jsonify({"publicKey": key})

    # -----------------------------------------------------
    # SUBSCRIBE
    # -----------------------------------------------------

    @bp.post("/subscribe")
    @login_required
    def subscribe():

        _, owner_id = _user_ids(current_user)

        data = request.get_json(silent=True) or {}

        endpoint = str(data.get("endpoint") or "").strip()
        keys = data.get("keys") or {}

        p256dh = keys.get("p256dh")
        auth = keys.get("auth")

        if not endpoint or not p256dh or not auth:
            return jsonify({
                "success": False,
                "error": "Subscription data ma dhammaystirna."
            }), 400

        now = datetime.now(TZ)

        subscriptions().update_one(
            {"endpoint": endpoint},
            {
                "$set": {
                    "user_id": owner_id,
                    "endpoint": endpoint,
                    "subscription": {
                        "endpoint": endpoint,
                        "keys": {
                            "p256dh": p256dh,
                            "auth": auth
                        }
                    },
                    "updated_at": now
                },
                "$setOnInsert": {
                    "created_at": now
                }
            },
            upsert=True
        )

        return jsonify({
            "success": True,
            "message": "Browser notifications waa la hawlgeliyey."
        })

    # -----------------------------------------------------
    # UNSUBSCRIBE
    # -----------------------------------------------------

    @bp.post("/unsubscribe")
    @login_required
    def unsubscribe():

        values, _ = _user_ids(current_user)

        data = request.get_json(silent=True) or {}
        endpoint = str(data.get("endpoint") or "").strip()

        if endpoint:
            subscriptions().delete_one({
                "endpoint": endpoint,
                "user_id": {"$in": values}
            })

        return jsonify({
            "success": True,
            "message": "Browser notifications waa la damiyey."
        })

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    @bp.get("/status")
    @login_required
    def status():

        values, _ = _user_ids(current_user)

        count = subscriptions().count_documents({
            "user_id": {"$in": values}
        })

        return jsonify({
            "enabled": count > 0,
            "supported": bool(_vapid_public_key())
        })

    # -----------------------------------------------------
    # PROTECTED CRON ENDPOINT
    # -----------------------------------------------------

    @bp.get("/cron")
    def cron_runner():

        expected_secret = (
            os.getenv("CRON_SECRET")
            or current_app.config.get("CRON_SECRET")
            or ""
        ).strip()

        authorization = request.headers.get("Authorization", "")

        if not expected_secret:
            current_app.logger.error(
                "CRON_SECRET lama dejin."
            )
            return jsonify({
                "success": False,
                "error": "Cron secret lama dejin."
            }), 503

        expected_header = f"Bearer {expected_secret}"

        if not hmac.compare_digest(
            authorization,
            expected_header
        ):
            return jsonify({
                "success": False,
                "error": "Unauthorized."
            }), 401

        lock_collection = mongo.db.job_locks

        lock_id = "personal_plan_reminders"
        lock_token = secrets.token_urlsafe(32)

        now_utc = datetime.now(timezone.utc)
        lease_until = now_utc + timedelta(minutes=15)

        try:
            lock_collection.find_one_and_update(
                {
                    "_id": lock_id,
                    "$or": [
                        {"lease_until": {"$lte": now_utc}},
                        {"lease_until": {"$exists": False}}
                    ]
                },
                {
                    "$set": {
                        "token": lock_token,
                        "locked_at": now_utc,
                        "lease_until": lease_until
                    }
                },
                upsert=True,
                return_document=ReturnDocument.AFTER
            )

        except DuplicateKeyError:
            return jsonify({
                "success": True,
                "skipped": True,
                "message": "Reminder job hore ayuu u socdaa."
            }), 202

        try:
            app = current_app._get_current_object()

            send_due_plan_notifications(app, mongo)

            return jsonify({
                "success": True,
                "message": "Personal Plan reminders waa la hubiyey.",
                "processed_at": datetime.now(TZ).isoformat()
            }), 200

        except Exception:
            current_app.logger.exception(
                "Personal Plan Cron failed."
            )

            return jsonify({
                "success": False,
                "error": "Reminder execution failed."
            }), 500

        finally:
            lock_collection.delete_one({
                "_id": lock_id,
                "token": lock_token
            })

    return bp


# =========================================================
# PLAN DEADLINE
# =========================================================

def _deadline_for(plan):

    raw_date = (
        plan.get("due_date")
        or plan.get("plan_date")
    )

    if not raw_date:
        return None

    raw_time = (
        plan.get("end_time")
        or plan.get("start_time")
        or "09:00"
    )

    try:
        day = datetime.strptime(
            str(raw_date)[:10],
            "%Y-%m-%d"
        ).date()

        clock = datetime.strptime(
            str(raw_time)[:5],
            "%H:%M"
        ).time()

        return datetime.combine(
            day,
            clock,
            tzinfo=TZ
        )

    except (TypeError, ValueError):
        return None


# =========================================================
# REMINDER LOGIC
# =========================================================

def _reminder_kind(delta_seconds, now, deadline):

    # Cron 5 daqiiqo kasta:
    # 10-minute window ayaa ka hortagaya in reminder la waayo.

    reminders = (
        (24, "24h"),
        (3, "3h"),
        (1, "1h")
    )

    for hours, label in reminders:

        target = hours * 3600

        if target - 600 <= delta_seconds <= target + 30:

            if hours == 24:
                message = "Deadline-ka qorshahaagu waa berri."

            else:
                message = (
                    f"Deadline-ka qorshahaaga waxaa ka harsan "
                    f"{hours} saac."
                )

            return label, message

    # Waqtigii deadline-ka
    if -600 <= delta_seconds <= 30:

        return (
            "due",
            "Waqtigii deadline-ka qorshahaaga ayaa la gaaray."
        )

    # Overdue: isla maalinta deadline-ku dhaafo ayuu bilaabmaa.
    # Hal fariin maalintii.

    if delta_seconds < -600:

        return (
            f"overdue-{now.date().isoformat()}",
            "Qorshahaagu wuu dhaafay waqtigii loogu talagalay."
        )

    return None, None


# =========================================================
# USER LOOKUP
# =========================================================

def _get_plan_owner(mongo, raw_owner):

    values = _owner_values(raw_owner)

    if not values:
        return None

    return mongo.db.users.find_one({
        "_id": {"$in": values}
    })


def _get_owner_email(owner):

    if not owner:
        return None

    email = (
        owner.get("email")
        or owner.get("google_email")
        or ""
    )

    email = str(email).strip()

    if not email or "@" not in email:
        return None

    return email


# =========================================================
# EMAIL
# =========================================================

def send_plan_email(
    app,
    mail,
    owner,
    plan,
    deadline,
    reminder_kind,
    reminder_message
):

    recipient = _get_owner_email(owner)

    if not recipient:
        app.logger.warning(
            "Personal Plan: user has no valid email. Plan=%s",
            plan.get("_id")
        )
        return False

    fullname = (
        owner.get("fullname")
        or owner.get("username")
        or "Maareeye User"
    )

    title = str(
        plan.get("title")
        or plan.get("name")
        or "Personal Plan"
    )

    category = str(
        plan.get("category")
        or plan.get("plan_type")
        or "Personal Plan"
    )

    description = str(
        plan.get("description")
        or "Ma jiro faahfaahin dheeraad ah."
    )

    base_url = (
        os.getenv("APP_BASE_URL")
        or app.config.get("PUBLIC_BASE_URL")
        or ""
    ).strip().rstrip("/")

    if not base_url:
        app.logger.error("APP_BASE_URL lama dejin.")
        return False

    plan_url = f"{base_url}/plan/"

    deadline_text = deadline.strftime(
        "%d %B %Y at %I:%M %p"
    )

    safe_name = html.escape(str(fullname))
    safe_title = html.escape(title)
    safe_category = html.escape(category)
    safe_description = html.escape(description)
    safe_message = html.escape(reminder_message)
    safe_deadline = html.escape(deadline_text)
    safe_url = html.escape(plan_url, quote=True)

    subject = f"Maareeye | {title} Reminder"

    text_body = f"""
Salaan {fullname},

{reminder_message}

Plan: {title}
Category: {category}
Deadline: {deadline_text}

{description}

Eeg qorshahaaga:
{plan_url}

Maareeye
"""

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:24px;background:#f3f5f9;
                 font-family:Arial,sans-serif;color:#172033;">
      <div style="max-width:560px;margin:auto;background:#ffffff;
                  border-radius:14px;overflow:hidden;">
        <div style="background:#06245f;padding:24px;color:white;">
          <h2 style="margin:0;">Maareeye</h2>
          <p style="margin:8px 0 0;">Personal Plan Reminder</p>
        </div>
        <div style="padding:26px;">
          <p>Dear {safe_name},</p>
          <div style="padding:14px;background:#fff4e5;
                      border-radius:8px;color:#8a4b08;">
            <strong>{safe_message}</strong>
          </div>
          <h2>{safe_title}</h2>
          <p><strong>Category:</strong> {safe_category}</p>
          <p><strong>Deadline:</strong> {safe_deadline}</p>
          <p>{safe_description}</p>
          <a href="{safe_url}"
             style="display:inline-block;background:#32b73a;
                    color:white;padding:12px 22px;
                    border-radius:7px;text-decoration:none;
                    font-weight:bold;">
            Open Personal Plan
          </a>
        </div>
        <div style="padding:16px;text-align:center;
                    color:#777;background:#f7f8fa;">
          Maareeye Personal Plan Notifications
        </div>
      </div>
    </body>
    </html>
    """

    message = Message(
        subject=subject,
        recipients=[recipient],
        body=text_body,
        html=html_body
    )

    mail.send(message)

    return True


# =========================================================
# WEB PUSH
# =========================================================

def send_plan_push(
    app,
    subscriptions,
    plan,
    reminder_kind,
    reminder_message,
    private_key,
    subject
):

    try:
        from pywebpush import webpush

    except ImportError:
        app.logger.exception(
            "pywebpush lama rakibin."
        )
        return 0

    raw_owner = plan.get("user_id")
    owner_values = _owner_values(raw_owner)

    if not owner_values:
        return 0

    owner_subscriptions = list(
        subscriptions.find({
            "user_id": {"$in": owner_values}
        })
    )

    if not owner_subscriptions:
        return 0

    title = str(
        plan.get("title")
        or plan.get("name")
        or "Personal Plan"
    )

    payload = json.dumps({
        "title": "Maareeye — Plan Reminder",
        "body": f"{reminder_message} {title}",
        "url": "/plan/",
        "tag": (
            f"plan-{plan['_id']}-{reminder_kind}"
        )
    }, ensure_ascii=False)

    delivered = 0

    for sub in owner_subscriptions:

        info = sub.get("subscription") or {
            "endpoint": sub.get("endpoint"),
            "keys": sub.get("keys", {})
        }

        try:
            from pywebpush import WebPushException

            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": subject}
            )

            delivered += 1

        except Exception as exc:

            status_code = getattr(
                getattr(exc, "response", None),
                "status_code",
                None
            )

            app.logger.warning(
                "Push failed. Status=%s Error=%s",
                status_code,
                exc
            )

            if status_code in (404, 410):
                subscriptions.delete_one({
                    "_id": sub["_id"]
                })

    return delivered


# =========================================================
# MAIN NOTIFICATION JOB
# =========================================================

def send_due_plan_notifications(app, mongo):
    """
    Checks all active Personal Plans.
    Sends email and push reminders separately.
    """

    with app.app_context():

        now = datetime.now(TZ)

        plans_col = mongo.db.personal_plans
        subs_col = mongo.db.push_subscriptions
        logs_col = mongo.db.plan_notification_logs

        private_key = _vapid_private_key()
        public_key = _vapid_public_key()

        vapid_subject = (
            os.getenv("VAPID_CLAIMS_EMAIL")
            or app.config.get("VAPID_CLAIMS_EMAIL")
            or "mailto:admin@example.com"
        ).strip()

        mail = app.extensions.get("mail")

        if mail is None:
            app.logger.error(
                "Flask-Mail lama helin. Hubi mail.init_app(app)."
            )

        plans = plans_col.find({
            "status": {
                "$nin": [
                    "completed",
                    "cancelled",
                    "deleted"
                ]
            }
        })

        checked = 0
        reminders_found = 0
        email_sent = 0
        push_sent = 0

        for plan in plans:

            checked += 1

            try:
                deadline = _deadline_for(plan)

                if not deadline:
                    continue

                delta = (
                    deadline - now
                ).total_seconds()

                reminder_kind, reminder_message = (
                    _reminder_kind(
                        delta,
                        now,
                        deadline
                    )
                )

                if not reminder_kind:
                    continue

                reminders_found += 1

                raw_owner = plan.get("user_id")

                if raw_owner is None:
                    app.logger.warning(
                        "Plan has no user_id: %s",
                        plan.get("_id")
                    )
                    continue

                plan_id = plan["_id"]

                log_base = (
                    f"{plan_id}:"
                    f"{deadline.isoformat()}:"
                    f"{reminder_kind}"
                )

                # ---------------------------------------------
                # EMAIL
                # ---------------------------------------------

                email_key = f"email:{log_base}"

                email_exists = logs_col.find_one(
                    {"key": email_key},
                    {"_id": 1}
                )

                if not email_exists and mail is not None:

                    owner = _get_plan_owner(
                        mongo,
                        raw_owner
                    )

                    if owner:

                        try:
                            sent = send_plan_email(
                                app=app,
                                mail=mail,
                                owner=owner,
                                plan=plan,
                                deadline=deadline,
                                reminder_kind=reminder_kind,
                                reminder_message=reminder_message
                            )

                            if sent:
                                logs_col.update_one(
                                    {"key": email_key},
                                    {
                                        "$setOnInsert": {
                                            "key": email_key,
                                            "channel": "email",
                                            "plan_id": plan_id,
                                            "user_id": raw_owner,
                                            "kind": reminder_kind,
                                            "deadline": deadline,
                                            "sent_at": now,
                                            "recipient": _get_owner_email(owner)
                                        }
                                    },
                                    upsert=True
                                )

                                email_sent += 1

                        except Exception:
                            app.logger.exception(
                                "Email failed. Plan=%s",
                                plan_id
                            )

                # ---------------------------------------------
                # BROWSER PUSH
                # ---------------------------------------------

                push_key = f"push:{log_base}"

                push_exists = logs_col.find_one(
                    {"key": push_key},
                    {"_id": 1}
                )

                if (
                    not push_exists
                    and private_key
                    and public_key
                ):

                    try:
                        delivered = send_plan_push(
                            app=app,
                            subscriptions=subs_col,
                            plan=plan,
                            reminder_kind=reminder_kind,
                            reminder_message=reminder_message,
                            private_key=private_key,
                            subject=vapid_subject
                        )

                        if delivered:
                            logs_col.update_one(
                                {"key": push_key},
                                {
                                    "$setOnInsert": {
                                        "key": push_key,
                                        "channel": "push",
                                        "plan_id": plan_id,
                                        "user_id": raw_owner,
                                        "kind": reminder_kind,
                                        "deadline": deadline,
                                        "sent_at": now,
                                        "delivered_count": delivered
                                    }
                                },
                                upsert=True
                            )

                            push_sent += delivered

                    except Exception:
                        app.logger.exception(
                            "Push failed. Plan=%s",
                            plan_id
                        )

            except Exception:
                app.logger.exception(
                    "Plan notification error. Plan=%s",
                    plan.get("_id")
                )

        app.logger.info(
            "Personal Plan job finished: checked=%s reminders=%s "
            "email_sent=%s push_sent=%s",
            checked,
            reminders_found,
            email_sent,
            push_sent
        )

        return {
            "checked": checked,
            "reminders_found": reminders_found,
            "email_sent": email_sent,
            "push_sent": push_sent
        }

"""Standalone Personal Plan & Schedule blueprint for Maareeye (Flask + MongoDB).

Register after Flask-PyMongo has been initialized:
    from app.personal_plan import create_personal_plan_blueprint
    app.register_blueprint(create_personal_plan_blueprint(mongo))

Template path:
    templates/backend/pages/components/personal_plans/personal_plan.html

Uses its own `personal_plans` collection; it does not touch `personal_timeline`.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from bson import ObjectId
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

TZ = ZoneInfo("Africa/Mogadishu")
STATUSES = ("pending", "in_progress", "completed", "cancelled")
PRIORITIES = ("low", "medium", "high", "urgent")
CATEGORIES = ("Personal", "Work", "Study", "Health", "Finance", "Family", "Business", "Other")


def now_local():
    return datetime.now(TZ)


def owner_values():
    raw = getattr(current_user, "id", None) or getattr(current_user, "_id", None)
    if raw is None:
        abort(403)
    text = str(raw)
    try:
        oid = raw if isinstance(raw, ObjectId) else ObjectId(text)
        return [oid, text], oid
    except Exception:
        return [text], text


def owner_query():
    values, _ = owner_values()
    return {"user_id": {"$in": values}}


def parse_date(value, label, required=False):
    value = (value or "").strip()
    if not value:
        if required:
            raise ValueError(f"{label} waa qasab.")
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError(f"{label} sax ma aha. Isticmaal YYYY-MM-DD.")


def parse_time(value, label):
    value = (value or "").strip()
    if not value:
        return ""
    try:
        return time.fromisoformat(value).strftime("%H:%M")
    except ValueError:
        raise ValueError(f"{label} sax ma aha. Isticmaal HH:MM.")


def form_data():
    title = (request.form.get("title") or "").strip()
    if not title:
        raise ValueError("Cinwaanka qorshaha waa qasab.")
    if len(title) > 150:
        raise ValueError("Cinwaanka kama badnaan karo 150 xaraf.")
    plan_date = parse_date(request.form.get("plan_date"), "Taariikhda", True)
    due_date = parse_date(request.form.get("due_date"), "Due date")
    start_time = parse_time(request.form.get("start_time"), "Waqtiga bilowga")
    end_time = parse_time(request.form.get("end_time"), "Waqtiga dhammaadka")
    if start_time and end_time and end_time < start_time:
        raise ValueError("Waqtiga dhammaadka kama horreyn karo waqtiga bilowga.")
    if due_date and due_date < plan_date:
        raise ValueError("Due date kama horreyn karto taariikhda qorshaha.")
    status = (request.form.get("status") or "pending").lower()
    priority = (request.form.get("priority") or "medium").lower()
    category = (request.form.get("category") or "Personal").strip()
    if status not in STATUSES:
        status = "pending"
    if priority not in PRIORITIES:
        priority = "medium"
    if category not in CATEGORIES:
        category = "Other"
    try:
        progress = max(0, min(100, int(request.form.get("progress") or 0)))
    except (TypeError, ValueError):
        progress = 0
    if status == "completed":
        progress = 100
    return {
        "title": title,
        "description": (request.form.get("description") or "").strip()[:5000],
        "plan_date": plan_date,
        "due_date": due_date,
        "start_time": start_time,
        "end_time": end_time,
        "category": category,
        "priority": priority,
        "status": status,
        "progress": progress,
        "notes": (request.form.get("notes") or "").strip()[:5000],
    }


def make_stats(records, today):
    return {
        "total": len(records),
        "pending": sum(p.get("status") == "pending" for p in records),
        "in_progress": sum(p.get("status") == "in_progress" for p in records),
        "completed": sum(p.get("status") == "completed" for p in records),
        "urgent": sum(p.get("priority") == "urgent" and p.get("status") not in ("completed", "cancelled") for p in records),
        "today": sum(p.get("plan_date") == today for p in records),
    }


def create_personal_plan_blueprint(mongo):
    bp = Blueprint("plan", __name__, url_prefix="/plan")
    plans_collection = lambda: mongo.db.personal_plans

    def get_owned(plan_id):
        if not ObjectId.is_valid(plan_id):
            abort(404)
        plan = plans_collection().find_one({"_id": ObjectId(plan_id), **owner_query()})
        if not plan:
            abort(404)
        return plan

    def render_page(plans=None, edit_plan=None, mode="week", selected=None, status_filter="all", range_start="", range_end=""):
        today = now_local().date().isoformat()
        selected = selected or today
        all_records = list(plans_collection().find(owner_query()))
        plans = plans if plans is not None else []
        for item in plans:
            item["id"] = str(item["_id"])
        if edit_plan:
            edit_plan["id"] = str(edit_plan["_id"])
        return render_template(
            "backend/pages/components/personal_plans/personal_plan.html",
            plans=plans, edit_plan=edit_plan, stats=make_stats(all_records, today),
            today=today, selected_date=selected, view_mode=mode,
            range_start=range_start, range_end=range_end, status_filter=status_filter,
            categories=CATEGORIES, statuses=STATUSES, priorities=PRIORITIES,
        )

    @bp.route("/", methods=["GET"])
    @login_required
    def plan_dashboard():
        today = now_local().date()
        selected = request.args.get("date", today.isoformat())
        try:
            chosen = date.fromisoformat(selected)
        except ValueError:
            chosen, selected = today, today.isoformat()
        mode = request.args.get("view", "week").lower()
        if mode not in ("day", "week", "month", "all"):
            mode = "week"
        if mode == "day":
            start = end = chosen
        elif mode == "month":
            start = chosen.replace(day=1)
            next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            end = next_month - timedelta(days=1)
        elif mode == "all":
            start = end = None
        else:
            start = chosen - timedelta(days=chosen.weekday())
            end = start + timedelta(days=6)
        records = list(plans_collection().find(owner_query()).sort([("plan_date", 1), ("start_time", 1), ("created_at", -1)]))
        if start:
            records = [p for p in records if start.isoformat() <= (p.get("plan_date") or "") <= end.isoformat()]
        status_filter = request.args.get("status", "all").lower()
        if status_filter in STATUSES:
            records = [p for p in records if p.get("status") == status_filter]
        else:
            status_filter = "all"
        page = render_page(records, mode=mode, selected=selected, status_filter=status_filter,
                            range_start=start.isoformat() if start else "",
                            range_end=end.isoformat() if end else "")
        # Inject selected range labels into the already prepared template context via template globals is unnecessary;
        # the selected date and mode remain visible and drive the schedule navigation.
        return page

    @bp.route("/add", methods=["POST"])
    @login_required
    def plan_add():
        try:
            payload = form_data()
            _, user_id = owner_values()
            now = now_local()
            payload.update(user_id=user_id, created_at=now, updated_at=now,
                           completed_at=now if payload["status"] == "completed" else None)
            plans_collection().insert_one(payload)
            flash("Qorshaha si guul leh ayaa loo diiwaangeliyey.", "success")
        except ValueError as exc:
            flash(str(exc), "danger")
        return redirect(url_for("plan.plan_dashboard"))

    @bp.route("/<plan_id>/edit", methods=["GET", "POST"])
    @login_required
    def plan_edit(plan_id):
        plan = get_owned(plan_id)
        if request.method == "POST":
            try:
                payload = form_data()
                payload["updated_at"] = now_local()
                payload["completed_at"] = (plan.get("completed_at") or now_local()) if payload["status"] == "completed" else None
                plans_collection().update_one({"_id": plan["_id"], **owner_query()}, {"$set": payload})
                flash("Qorshaha waa la cusboonaysiiyey.", "success")
                return redirect(url_for("plan.plan_dashboard"))
            except ValueError as exc:
                flash(str(exc), "danger")
        return render_page(edit_plan=plan)

    @bp.route("/<plan_id>/delete", methods=["POST"])
    @login_required
    def plan_delete(plan_id):
        plan = get_owned(plan_id)
        plans_collection().delete_one({"_id": plan["_id"], **owner_query()})
        flash("Qorshaha waa la tirtiray.", "success")
        return redirect(url_for("plan.plan_dashboard"))

    @bp.route("/<plan_id>/status", methods=["POST"])
    @login_required
    def plan_update_status(plan_id):
        plan = get_owned(plan_id)
        status = (request.form.get("status") or "").lower()
        if status not in STATUSES:
            abort(400)
        now = now_local()
        progress = 100 if status == "completed" else min(int(plan.get("progress", 0) or 0), 99)
        plans_collection().update_one(
            {"_id": plan["_id"], **owner_query()},
            {"$set": {"status": status, "progress": progress, "updated_at": now,
                      "completed_at": now if status == "completed" else None}},
        )
        flash("Xaaladda qorshaha waa la beddelay.", "success")
        return redirect(request.referrer or url_for("plan.plan_dashboard"))

    @bp.route("/api/events", methods=["GET"])
    @login_required
    def plan_events():
        query = owner_query()
        date_filter = {}
        if request.args.get("start"):
            date_filter["$gte"] = request.args["start"][:10]
        if request.args.get("end"):
            date_filter["$lte"] = request.args["end"][:10]
        if date_filter:
            query["plan_date"] = date_filter
        result = []
        for plan in plans_collection().find(query).sort([("plan_date", 1), ("start_time", 1)]):
            result.append({"id": str(plan["_id"]), "title": plan.get("title", "Untitled"),
                           "date": plan.get("plan_date", ""), "start": plan.get("start_time", ""),
                           "end": plan.get("end_time", ""), "status": plan.get("status", "pending"),
                           "priority": plan.get("priority", "medium"), "category": plan.get("category", "Personal"),
                           "url": url_for("plan.plan_edit", plan_id=str(plan["_id"]))})
        return jsonify(result)

    return bp

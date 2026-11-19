"""Register / login / logout। Session cookie দিয়ে কে login করা আছে মনে রাখা হয়।"""
import re
import time
from functools import wraps

from flask import Blueprint, g, jsonify, request, session

from .models import Notification, User, db, log

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = db.session.get(User, session.get("uid")) if session.get("uid") else None
        if not user:
            return jsonify(error="Please log in"), 401
        g.user = user
        return fn(*args, **kwargs)
    return wrapper


def error(msg, code=400):
    return jsonify(error=msg), code


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BD_PHONE = re.compile(r"^(\+?88)?01[3-9]\d{8}$")


def password_problem(pw):
    """Frontend-এর নিয়মের সাথে একই: ৮+ অক্ষর, অন্তত একটা অক্ষর আর একটা সংখ্যা।"""
    if len(pw) < 8 or len(pw) > 128 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must be 8+ characters with at least one letter and one number"


def phone_problem(phone):
    if phone and not BD_PHONE.match(re.sub(r"[\s-]", "", phone)):
        return "Enter a valid Bangladeshi phone number"


# ---- Login brute-force সুরক্ষা: একই IP + email থেকে ১৫ মিনিটে ৫ বার ভুল হলে কিছুক্ষণ বন্ধ ----
MAX_FAILS, WINDOW = 5, 15 * 60
_fails = {}


def _too_many(key):
    now = time.time()
    _fails[key] = [t for t in _fails.get(key, []) if now - t < WINDOW]
    return len(_fails[key]) >= MAX_FAILS


@bp.post("/register")
def register():
    d = request.get_json(silent=True) or {}
    name, email, pw = (d.get("name") or "").strip(), (d.get("email") or "").strip().lower(), d.get("password") or ""
    phone = (d.get("phone") or "").strip()
    if not name or len(name) > 120 or len(email) > 120 or not EMAIL.match(email):
        return error("Name and a valid email are required")
    if msg := password_problem(pw) or phone_problem(phone):
        return error(msg)
    if User.query.filter_by(email=email).first():
        return error("This email is already registered", 409)
    user = User(name=name, email=email, phone=phone or None, allergies=[], conditions=[])
    user.set_password(pw)
    db.session.add(user)
    db.session.flush()
    db.session.add(Notification(user_id=user.id, type="System", title="Welcome to MediSafe",
                                text="Complete your medical profile."))
    log(user.id, "Created account")
    db.session.commit()
    session.clear()
    session.permanent = True
    session["uid"] = user.id
    return jsonify(ok=True), 201


@bp.post("/login")
def login():
    d = request.get_json(silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    key = (request.remote_addr, email)
    if _too_many(key):
        return error("Too many failed attempts. Please wait 15 minutes and try again.", 429)
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(d.get("password") or ""):
        _fails.setdefault(key, []).append(time.time())
        return error("Incorrect email or password", 401)  # কোনটা ভুল তা বলা হয় না (security)
    _fails.pop(key, None)
    session.clear()
    session.permanent = True
    session["uid"] = user.id
    return jsonify(ok=True)


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.post("/change-password")
@login_required
def change_password():
    d = request.get_json(silent=True) or {}
    if not g.user.check_password(d.get("current") or ""):
        return error("Current password is incorrect")
    if msg := password_problem(d.get("new") or ""):
        return error(msg)
    g.user.set_password(d["new"])
    db.session.commit()
    return jsonify(ok=True)

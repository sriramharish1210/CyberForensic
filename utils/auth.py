from werkzeug.security import generate_password_hash, check_password_hash
from flask import session, redirect

def hash_password(password):
    return generate_password_hash(password)

def verify_password(stored_password, provided_password):
    return check_password_hash(stored_password, provided_password)

def login_user(user):
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]

def logout_user():
    session.clear()

def login_required(role=None):
    if "user_id" not in session:
        return redirect("/login")

    if role and session.get("role") != role:
        return "Unauthorized Access", 403

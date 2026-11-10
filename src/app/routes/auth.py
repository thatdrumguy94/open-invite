from functools import wraps
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    g,
)
from src.app import db
from src.app.models.user import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def login_required(view_func):
    """Decorator to enforce host authentication on protected routes."""
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if g.current_user is None:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return view_func(*args, **kwargs)
    return wrapped_view


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Host registration view."""
    if g.current_user:
        return redirect(url_for("events.list_events"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("auth/register.html", name=name, email=email)

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html", name=name, email=email)

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("auth/register.html", name=name, email=email)

        # Check existing email
        if User.query.filter_by(email=email).first():
            flash("An account with this email address already exists.", "warning")
            return render_template("auth/register.html", name=name, email=email)

        # Create new host user
        user = User(email=email, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # Log user in
        session.clear()
        session["user_id"] = user.user_id
        session["user_name"] = user.name
        flash(f"Welcome to the Event Invitation System, {user.name}!", "success")
        return redirect(url_for("events.list_events"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Host login view."""
    if g.current_user:
        return redirect(url_for("events.list_events"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            flash("Invalid email or password. Please try again.", "danger")
            return render_template("auth/login.html", email=email)

        # Set session
        session.clear()
        session["user_id"] = user.user_id
        session["user_name"] = user.name
        flash(f"Welcome back, {user.name}!", "success")

        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("events.list_events"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    """Host logout view."""
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))

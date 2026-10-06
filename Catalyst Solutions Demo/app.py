# cd "Catalyst Solutions Demo"; python app.py
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)

# Required for sessions. Change this to a long random value before real use.
app.secret_key = "change-this-later"

# TEMPORARY demo account. Later this will be replaced by a MySQL users table.
DEMO_USER = {"username": "daniel", "password": "buffbison123", "name": "Daniel Carter"}


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]

        if username == DEMO_USER["username"] and password == DEMO_USER["password"]:
            session["user"] = DEMO_USER["name"]
            return redirect(url_for("dashboard"))

        error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    return render_template("dashboard.html", user_name=session["user"])


# ---------- PROJECTS ----------

@app.route("/projects")
def projects():
    if "user" not in session:
        return redirect(url_for("login"))

    return render_template("projects.html", user_name=session["user"])


@app.route("/new-project", methods=["GET", "POST"])
def new_project():
    if "user" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        # Nothing is saved yet. Later: insert the form data into MySQL here.
        return redirect(url_for("projects"))

    return render_template("new_project.html", user_name=session["user"])


@app.route("/project/<int:project_id>")
def project_details(project_id):
    if "user" not in session:
        return redirect(url_for("login"))

    # For now every ID shows the same sample project.
    # Later: look up project_id in MySQL.
    return render_template("project_details.html", user_name=session["user"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
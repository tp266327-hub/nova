import os, sqlite3, uuid
from functools import wraps
from flask import (Flask, g, request, session, redirect, url_for, render_template,
                   jsonify, send_from_directory, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "nova.db")
UPLOADS = os.path.join(BASE, "uploads")
os.makedirs(UPLOADS, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
ALLOWED = {"pdf", "png", "jpg", "jpeg", "txt", "zip", "docx", "csv"}
FREE_PROJECTS, FREE_FILE_MB = 3, 2

# ---------- database ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d: d.close()

def init_db():
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL, premium INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS projects(
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL,
      details TEXT, filename TEXT, stored TEXT,
      created TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS comments(
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, username TEXT NOT NULL,
      body TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    c.commit(); c.close()

def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if "uid" not in session:
            if request.path.startswith("/api/"):
                return jsonify(error="Please sign in again."), 401
            return redirect(url_for("login"))
        return f(*a, **k)
    return wrap

def me():
    return db().execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone()

# ---------- auth ----------
@app.route("/")
def index():
    return redirect(url_for("home" if "uid" in session else "login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    d = request.get_json(force=True)
    mode = d.get("mode", "login")
    name, pw = (d.get("username") or "").strip(), d.get("password") or ""
    if len(name) < 3 or len(pw) < 6:
        return jsonify(error="Username needs 3+ characters and password 6+."), 400
    if mode == "register":
        try:
            cur = db().execute("INSERT INTO users(username,password) VALUES(?,?)",
                               (name, generate_password_hash(pw)))
            db().commit()
        except sqlite3.IntegrityError:
            return jsonify(error="That username is taken. Try another."), 409
        session["uid"] = cur.lastrowid
    else:
        u = db().execute("SELECT * FROM users WHERE username=?", (name,)).fetchone()
        if not u or not check_password_hash(u["password"], pw):
            return jsonify(error="Wrong username or password."), 401
        session["uid"] = u["id"]
    return jsonify(ok=True, next=url_for("home"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/home")
@login_required
def home():
    return render_template("home.html", user=me(), free_projects=FREE_PROJECTS,
                           free_mb=FREE_FILE_MB)

# ---------- projects + file attachment ----------
def project_json(r):
    return dict(id=r["id"], name=r["name"], details=r["details"],
                filename=r["filename"], created=r["created"][:10])

@app.route("/api/projects", methods=["GET", "POST"])
@login_required
def projects():
    u = me()
    if request.method == "GET":
        rows = db().execute("SELECT * FROM projects WHERE user_id=? ORDER BY id DESC",
                            (u["id"],)).fetchall()
        return jsonify([project_json(r) for r in rows])
    count = db().execute("SELECT COUNT(*) c FROM projects WHERE user_id=?",
                         (u["id"],)).fetchone()["c"]
    if not u["premium"] and count >= FREE_PROJECTS:
        return jsonify(error=f"Free plan allows {FREE_PROJECTS} projects. Upgrade to Premium for unlimited.",
                       premium=True), 402
    name = (request.form.get("name") or "").strip()
    if not name:
        return jsonify(error="Give your project a name."), 400
    fname = stored = None
    f = request.files.get("file")
    if f and f.filename:
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED:
            return jsonify(error="File type not allowed: " + ", ".join(sorted(ALLOWED))), 400
        f.seek(0, os.SEEK_END); size = f.tell(); f.seek(0)
        if not u["premium"] and size > FREE_FILE_MB * 1024 * 1024:
            return jsonify(error=f"Free plan files are limited to {FREE_FILE_MB} MB.", premium=True), 402
        fname = secure_filename(f.filename)
        stored = uuid.uuid4().hex + "." + ext
        f.save(os.path.join(UPLOADS, stored))
    db().execute("INSERT INTO projects(user_id,name,details,filename,stored) VALUES(?,?,?,?,?)",
                 (u["id"], name, request.form.get("details", ""), fname, stored))
    db().commit()
    return jsonify(ok=True)

@app.route("/api/projects/<int:pid>", methods=["DELETE"])
@login_required
def delete_project(pid):
    r = db().execute("SELECT * FROM projects WHERE id=? AND user_id=?",
                     (pid, session["uid"])).fetchone()
    if not r: abort(404)
    if r["stored"]:
        try: os.remove(os.path.join(UPLOADS, r["stored"]))
        except OSError: pass
    db().execute("DELETE FROM projects WHERE id=?", (pid,)); db().commit()
    return jsonify(ok=True)

@app.route("/files/<int:pid>")
@login_required
def download(pid):
    r = db().execute("SELECT * FROM projects WHERE id=? AND user_id=?",
                     (pid, session["uid"])).fetchone()
    if not r or not r["stored"]: abort(404)
    return send_from_directory(UPLOADS, r["stored"], as_attachment=True,
                               download_name=r["filename"])

# ---------- comments ----------
@app.route("/api/comments", methods=["GET", "POST"])
@login_required
def comments():
    if request.method == "POST":
        body = (request.get_json(force=True).get("body") or "").strip()[:500]
        if not body:
            return jsonify(error="Write something first."), 400
        db().execute("INSERT INTO comments(user_id,username,body) VALUES(?,?,?)",
                     (session["uid"], me()["username"], body)); db().commit()
    rows = db().execute("SELECT username,body,created FROM comments ORDER BY id DESC LIMIT 50").fetchall()
    return jsonify([dict(r) for r in rows])

# ---------- AI chat ----------
SYSTEM = ("You are Nova, the assistant inside a project workspace. Help users plan, "
          "describe and organise their projects. Be concise and practical.")

def fallback_reply(text):
    t = text.lower()
    if "premium" in t: return "Premium removes the 3-project limit and raises file uploads to 16 MB. Open Premium in the top bar."
    if "upload" in t or "file" in t: return "Fill in a project name, add details, and choose a file in the Projects panel. Allowed: " + ", ".join(sorted(ALLOWED)) + "."
    if "project" in t: return "Try describing your project's goal, the tools you're using, and the next milestone. I can help refine it once an API key is connected."
    return "I'm running in offline mode. Set ANTHROPIC_API_KEY on the server to get full AI answers."

@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    msgs = request.get_json(force=True).get("messages", [])[-12:]
    msgs = [{"role": m["role"], "content": str(m["content"])[:2000]}
            for m in msgs if m.get("role") in ("user", "assistant")]
    if not msgs or msgs[-1]["role"] != "user":
        return jsonify(error="Say something first."), 400
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            r = anthropic.Anthropic().messages.create(
                model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
                max_tokens=600, system=SYSTEM, messages=msgs)
            return jsonify(reply=r.content[0].text)
        except Exception as e:
            return jsonify(reply="The AI service is unavailable right now. " + fallback_reply(msgs[-1]["content"]))
    return jsonify(reply=fallback_reply(msgs[-1]["content"]))

# ---------- premium ----------
@app.route("/api/premium", methods=["POST"])
@login_required
def premium():
    # Demo upgrade. Replace with Stripe/Razorpay checkout + webhook before real use.
    db().execute("UPDATE users SET premium=1 WHERE id=?", (session["uid"],)); db().commit()
    return jsonify(ok=True)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)

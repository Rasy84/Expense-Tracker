import os
import re
import sqlite3
from datetime import datetime, date
from pathlib import Path

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

APP_ROOT = Path(__file__).resolve().parent
DB_PATH = APP_ROOT / "expense_tracker.db"
UPLOAD_DIR = APP_ROOT / "uploads"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

app = Flask(__name__)
app.secret_key = "dev-secret-key"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT,
                note TEXT,
                entry_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                ocr_text TEXT,
                detected_amount REAL,
                detected_date TEXT,
                entry_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(entry_id) REFERENCES entries(id)
            )
            """
        )


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def try_ocr_image(image_path):
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None, "OCR libraries not installed."

    try:
        text = pytesseract.image_to_string(Image.open(image_path))
        return text, None
    except Exception as exc:
        return None, f"OCR failed: {exc}"


def extract_amount(text):
    if not text:
        return None

    keyword_match = re.search(
        r"(?i)(total|amount due|balance)\s*[:$]?\s*([0-9,]+\.\d{2})",
        text,
    )
    if keyword_match:
        return float(keyword_match.group(2).replace(",", ""))

    amounts = re.findall(r"(?<!\d)([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{2}))", text)
    if not amounts:
        return None

    values = [float(value.replace(",", "")) for value in amounts]
    return max(values) if values else None


def parse_date_string(raw_date):
    if not raw_date:
        return None

    formats = ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"]
    for fmt in formats:
        try:
            parsed = datetime.strptime(raw_date, fmt)
            return parsed.date().isoformat()
        except ValueError:
            continue
    return None


def extract_date(text):
    if not text:
        return None

    patterns = [
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{4}/\d{2}/\d{2})",
        r"(\d{2}/\d{2}/\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            parsed = parse_date_string(match.group(1))
            if parsed:
                return parsed
    return None


def insert_entry(entry_type, amount, category, note, entry_date):
    created_at = datetime.utcnow().isoformat()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO entries (entry_type, amount, category, note, entry_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (entry_type, amount, category, note, entry_date, created_at),
        )
        return cursor.lastrowid


def insert_receipt(filename, ocr_text, detected_amount, detected_date, entry_id):
    created_at = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO receipts (filename, ocr_text, detected_amount, detected_date, entry_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (filename, ocr_text, detected_amount, detected_date, entry_id, created_at),
        )


UPLOAD_DIR.mkdir(exist_ok=True)
init_db()


@app.route("/")
def index():
    current_year = str(date.today().year)
    with get_db() as conn:
        totals = conn.execute(
            """
            SELECT
                SUM(CASE WHEN entry_type = 'income' THEN amount ELSE 0 END) AS total_income,
                SUM(CASE WHEN entry_type = 'expense' THEN amount ELSE 0 END) AS total_expense
            FROM entries
            WHERE strftime('%Y', entry_date) = ?
            """,
            (current_year,),
        ).fetchone()

        recent_entries = conn.execute(
            """
            SELECT * FROM entries
            ORDER BY entry_date DESC, created_at DESC
            LIMIT 6
            """
        ).fetchall()

    total_income = totals["total_income"] or 0
    total_expense = totals["total_expense"] or 0
    net = total_income - total_expense

    return render_template(
        "index.html",
        current_year=current_year,
        total_income=total_income,
        total_expense=total_expense,
        net=net,
        recent_entries=recent_entries,
    )


@app.route("/entries")
def entries():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM entries
            ORDER BY entry_date DESC, created_at DESC
            """
        ).fetchall()
    return render_template("entries.html", entries=rows)


@app.route("/entries/new", methods=["GET", "POST"])
def new_entry():
    if request.method == "POST":
        entry_type = request.form.get("entry_type")
        amount = request.form.get("amount")
        category = request.form.get("category")
        note = request.form.get("note")
        entry_date = request.form.get("entry_date") or date.today().isoformat()

        if entry_type not in {"income", "expense"}:
            flash("Please select income or expense.", "error")
            return redirect(url_for("new_entry"))

        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            flash("Please provide a valid amount.", "error")
            return redirect(url_for("new_entry"))

        insert_entry(entry_type, amount_value, category, note, entry_date)
        flash("Entry saved.", "success")
        return redirect(url_for("entries"))

    return render_template("add_entry.html")


@app.route("/receipts")
def receipts():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT r.*, e.entry_date, e.amount AS entry_amount
            FROM receipts r
            LEFT JOIN entries e ON r.entry_id = e.id
            ORDER BY r.created_at DESC
            """
        ).fetchall()
    return render_template("receipts.html", receipts=rows)


@app.route("/receipts/upload", methods=["GET", "POST"])
def upload_receipt():
    if request.method == "POST":
        file = request.files.get("receipt")
        if not file or file.filename == "":
            flash("Please select a receipt image.", "error")
            return redirect(url_for("upload_receipt"))

        if not allowed_file(file.filename):
            flash("Upload a PNG or JPG image.", "error")
            return redirect(url_for("upload_receipt"))

        filename = secure_filename(file.filename)
        filepath = UPLOAD_DIR / filename
        file.save(filepath)

        ocr_text, ocr_error = try_ocr_image(filepath)
        detected_amount = extract_amount(ocr_text)
        detected_date = extract_date(ocr_text) or date.today().isoformat()

        entry_id = None
        if detected_amount is not None:
            entry_id = insert_entry(
                "expense",
                detected_amount,
                "Receipt",
                "Auto-imported from receipt",
                detected_date,
            )
            flash("Receipt processed and expense saved.", "success")
        else:
            flash("Receipt saved, but amount was not detected.", "warning")

        if ocr_error:
            flash(ocr_error, "warning")

        insert_receipt(filename, ocr_text, detected_amount, detected_date, entry_id)
        return redirect(url_for("receipts"))

    return render_template("upload_receipt.html")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/yearly-summary")
def yearly_summary():
    year = request.args.get("year") or str(date.today().year)
    with get_db() as conn:
        totals = conn.execute(
            """
            SELECT
                SUM(CASE WHEN entry_type = 'income' THEN amount ELSE 0 END) AS total_income,
                SUM(CASE WHEN entry_type = 'expense' THEN amount ELSE 0 END) AS total_expense
            FROM entries
            WHERE strftime('%Y', entry_date) = ?
            """,
            (year,),
        ).fetchone()

        monthly_rows = conn.execute(
            """
            SELECT
                strftime('%m', entry_date) AS month,
                SUM(CASE WHEN entry_type = 'income' THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN entry_type = 'expense' THEN amount ELSE 0 END) AS expense
            FROM entries
            WHERE strftime('%Y', entry_date) = ?
            GROUP BY strftime('%m', entry_date)
            ORDER BY month
            """,
            (year,),
        ).fetchall()

        category_rows = conn.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM entries
            WHERE entry_type = 'expense' AND strftime('%Y', entry_date) = ?
            GROUP BY category
            ORDER BY total DESC
            """,
            (year,),
        ).fetchall()

    total_income = totals["total_income"] or 0
    total_expense = totals["total_expense"] or 0
    net = total_income - total_expense

    return render_template(
        "yearly_summary.html",
        year=year,
        total_income=total_income,
        total_expense=total_expense,
        net=net,
        monthly_rows=monthly_rows,
        category_rows=category_rows,
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)

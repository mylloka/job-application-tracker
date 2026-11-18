"""COP4751 Job Application Tracker — Flask application."""
import json
import os
from datetime import date
from functools import wraps
from urllib.parse import urlparse

import mysql.connector
from flask import Flask, abort, flash, redirect, render_template, request, url_for

from database import get_db

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "local-development-only-change-me")

# All SQL table/column names below come exclusively from this server-side allowlist.
TABLES = {
    "companies": {
        "label": "Companies", "singular": "Company", "pk": "company_id", "required": ["company_name"],
        "fields": [
            ("company_name", "Company Name", "text", 100),
            ("industry", "Industry", "text", 50),
            ("website", "Website", "url", 200),
            ("city", "City", "text", 50),
            ("state", "State", "text", 50),
            ("notes", "Notes", "textarea", None),
        ],
    },
    "jobs": {
        "label": "Jobs", "singular": "Job", "pk": "job_id", "required": ["job_title", "company_id"],
        "fields": [
            ("company_id", "Company", "company_fk", None),
            ("job_title", "Job Title", "text", 100),
            ("job_type", "Job Type", "job_enum", None),
            ("salary_min", "Minimum Salary ($)", "number", None),
            ("salary_max", "Maximum Salary ($)", "number", None),
            ("job_url", "Job Posting URL", "url", 300),
            ("date_posted", "Date Posted", "date", None),
            ("requirements", "Requirements (JSON)", "requirements_json", None),
        ],
    },
    "applications": {
        "label": "Applications", "singular": "Application", "pk": "application_id", "required": ["job_id", "application_date"],
        "fields": [
            ("job_id", "Job", "job_fk", None),
            ("application_date", "Application Date", "date", None),
            ("status", "Status", "status_enum", None),
            ("resume_version", "Resume Version", "text", 50),
            ("cover_letter_sent", "Cover Letter Sent", "checkbox", None),
            ("interview_data", "Interview Data (JSON)", "interview_json", None),
        ],
    },
    "contacts": {
        "label": "Contacts", "singular": "Contact", "pk": "contact_id", "required": ["contact_name", "company_id"],
        "fields": [
            ("company_id", "Company", "company_fk", None),
            ("contact_name", "Contact Name", "text", 100),
            ("title", "Job Title", "text", 100),
            ("email", "Email", "email", 100),
            ("phone", "Phone", "text", 20),
            ("linkedin_url", "LinkedIn URL", "url", 200),
            ("notes", "Notes", "textarea", None),
        ],
    },
}
JOB_TYPES = ["Full-time", "Part-time", "Contract", "Internship"]
STATUSES = ["Applied", "Screening", "Interview", "Offer", "Rejected", "Withdrawn"]


def query_all(sql, params=()):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def query_one(sql, params=()):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def execute_write(sql, params=()):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        row_id = cursor.lastrowid
        conn.commit()
        return row_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def table_config(table):
    if table not in TABLES:
        abort(404)
    return TABLES[table]


def fetch_records(table):
    table_config(table)
    if table == "jobs":
        return query_all("""SELECT j.*, c.company_name FROM jobs j
                           LEFT JOIN companies c ON j.company_id = c.company_id
                           ORDER BY j.job_id DESC""")
    if table == "applications":
        return query_all("""SELECT a.*, j.job_title, c.company_name
                           FROM applications a
                           LEFT JOIN jobs j ON a.job_id = j.job_id
                           LEFT JOIN companies c ON j.company_id = c.company_id
                           ORDER BY a.application_id DESC""")
    if table == "contacts":
        return query_all("""SELECT t.*, c.company_name FROM contacts t
                           LEFT JOIN companies c ON t.company_id = c.company_id
                           ORDER BY t.contact_id DESC""")
    return query_all("SELECT * FROM companies ORDER BY company_id DESC")


def fetch_record(table, record_id):
    config = table_config(table)
    # Identifier is trusted (from TABLES), and record_id is an integer route parameter.
    return query_one(f"SELECT * FROM `{table}` WHERE `{config['pk']}` = %s", (record_id,))


def select_options():
    companies = query_all("SELECT company_id, company_name FROM companies ORDER BY company_name")
    jobs = query_all("""SELECT j.job_id, j.job_title, c.company_name
                        FROM jobs j LEFT JOIN companies c ON j.company_id=c.company_id
                        ORDER BY c.company_name, j.job_title""")
    return companies, jobs


def clean_form(table):
    config = table_config(table)
    errors = []
    data = {}
    for field, label, kind, max_len in config["fields"]:
        raw = request.form.get(field, "").strip()
        if kind == "checkbox":
            data[field] = 1 if request.form.get(field) == "on" else 0
            continue
        if field in config["required"] and not raw:
            errors.append(f"{label} is required.")
        if max_len and len(raw) > max_len:
            errors.append(f"{label} must be at most {max_len} characters.")
        if kind in ("company_fk", "job_fk"):
            if raw:
                try:
                    data[field] = int(raw)
                    if data[field] < 1:
                        raise ValueError
                except ValueError:
                    errors.append(f"Choose a valid {label.lower()}.")
                    data[field] = None
            else:
                data[field] = None
        elif kind == "number":
            if raw:
                try:
                    value = int(raw)
                    if value < 0 or value > 2147483647:
                        raise ValueError
                    data[field] = value
                except ValueError:
                    errors.append(f"{label} must be a non-negative whole number.")
                    data[field] = None
            else:
                data[field] = None
        elif kind == "job_enum":
            if raw and raw not in JOB_TYPES:
                errors.append("Choose a valid job type.")
            data[field] = raw or None
        elif kind == "status_enum":
            if raw and raw not in STATUSES:
                errors.append("Choose a valid application status.")
            data[field] = raw or None
        elif kind in ("requirements_json", "interview_json"):
            if raw:
                try:
                    obj = json.loads(raw)
                    if not isinstance(obj, dict):
                        raise ValueError("JSON must be an object")
                    if kind == "requirements_json":
                        skills = obj.get("skills", [])
                        if not isinstance(skills, list) or any(not isinstance(s, str) for s in skills):
                            raise ValueError("skills must be a list of strings")
                    data[field] = json.dumps(obj)
                except (json.JSONDecodeError, ValueError) as exc:
                    errors.append(f"{label} is invalid: {exc}")
                    data[field] = None
            else:
                data[field] = None
        elif kind == "date":
            if raw:
                try:
                    date.fromisoformat(raw)
                except ValueError:
                    errors.append(f"{label} must be a valid date.")
            data[field] = raw or None
        elif kind == "email":
            if raw and ("@" not in raw or "." not in raw.split("@")[-1]):
                errors.append("Enter a valid email address.")
            data[field] = raw or None
        elif kind == "url":
            if raw:
                parsed = urlparse(raw)
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    errors.append(f"{label} must start with http:// or https:// and have a host.")
            data[field] = raw or None
        else:
            data[field] = raw or None

    if table == "jobs" and data.get("salary_min") is not None and data.get("salary_max") is not None:
        if data["salary_min"] > data["salary_max"]:
            errors.append("Minimum salary cannot exceed maximum salary.")
    if table in ("jobs", "contacts") and data.get("company_id") is not None:
        if query_one("SELECT company_id FROM companies WHERE company_id = %s", (data["company_id"],)) is None:
            errors.append("Selected company does not exist.")
    if table == "applications" and data.get("job_id") is not None:
        if query_one("SELECT job_id FROM jobs WHERE job_id = %s", (data["job_id"],)) is None:
            errors.append("Selected job does not exist.")
    return data, errors


@app.route("/")
def home():
    stats = {
        "companies": query_one("SELECT COUNT(*) AS total FROM companies")["total"],
        "jobs": query_one("SELECT COUNT(*) AS total FROM jobs")["total"],
        "applications": query_one("SELECT COUNT(*) AS total FROM applications")["total"],
        "contacts": query_one("SELECT COUNT(*) AS total FROM contacts")["total"],
        "interviews": query_one("SELECT COUNT(*) AS total FROM applications WHERE status='Interview'")["total"],
        "offers": query_one("SELECT COUNT(*) AS total FROM applications WHERE status='Offer'")["total"],
    }
    recent = query_all("""SELECT a.application_id, a.application_date, a.status,
                              j.job_title, c.company_name
                       FROM applications a LEFT JOIN jobs j ON a.job_id = j.job_id
                       LEFT JOIN companies c ON j.company_id = c.company_id
                       ORDER BY a.application_date DESC, a.application_id DESC LIMIT 5""")
    return render_template("dashboard.html", stats=stats, recent=recent)


@app.route("/<table>")
def list_records(table):
    config = table_config(table)
    return render_template(f"{table}.html", config=config, table=table,
                           records=fetch_records(table))


@app.route("/<table>/add", methods=["GET", "POST"])
def add_record(table):
    config = table_config(table)
    if request.method == "POST":
        values, errors = clean_form(table)
        if not errors:
            columns = list(values)
            names = ", ".join(f"`{c}`" for c in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            try:
                execute_write(f"INSERT INTO `{table}` ({names}) VALUES ({placeholders})",
                              tuple(values[c] for c in columns))
                flash(f"{config['singular']} added successfully!", "success")
                return redirect(url_for("list_records", table=table))
            except mysql.connector.Error as exc:
                errors.append(f"Database could not save the record: {exc.msg}")
        for error in errors:
            flash(error, "error")
        record = request.form.to_dict()
    else:
        record = {}
    companies, jobs = select_options()
    template = "add_company.html" if table == "companies" else "record_form.html"
    return render_template(template, table=table, config=config, record=record,
                           companies=companies, jobs=jobs, job_types=JOB_TYPES,
                           statuses=STATUSES, editing=False)


@app.route("/<table>/<int:record_id>")
def record_detail(table, record_id):
    config = table_config(table)
    record = fetch_record(table, record_id)
    if record is None:
        abort(404)
    return render_template("detail.html", config=config, table=table, record=record)


@app.route("/<table>/<int:record_id>/edit", methods=["GET", "POST"])
def edit_record(table, record_id):
    config = table_config(table)
    existing = fetch_record(table, record_id)
    if existing is None:
        abort(404)
    if request.method == "POST":
        values, errors = clean_form(table)
        if not errors:
            setters = ", ".join(f"`{c}` = %s" for c in values)
            try:
                execute_write(f"UPDATE `{table}` SET {setters} WHERE `{config['pk']}` = %s",
                              (*values.values(), record_id))
                flash("Record updated successfully!", "success")
                return redirect(url_for("record_detail", table=table, record_id=record_id))
            except mysql.connector.Error as exc:
                errors.append(f"Database could not update the record: {exc.msg}")
        for error in errors:
            flash(error, "error")
        record = request.form.to_dict()
    else:
        record = existing
    companies, jobs = select_options()
    return render_template("record_form.html", table=table, config=config,
                           record=record, companies=companies, jobs=jobs,
                           job_types=JOB_TYPES, statuses=STATUSES, editing=True,
                           record_id=record_id)


@app.route("/<table>/<int:record_id>/delete", methods=["GET", "POST"])
def delete_record(table, record_id):
    config = table_config(table)
    record = fetch_record(table, record_id)
    if record is None:
        abort(404)
    if request.method == "POST":
        try:
            execute_write(f"DELETE FROM `{table}` WHERE `{config['pk']}` = %s", (record_id,))
            flash("Record deleted successfully!", "success")
            return redirect(url_for("list_records", table=table))
        except mysql.connector.IntegrityError:
            flash("Cannot delete: related records exist. Delete or reassign those first.", "error")
            return redirect(url_for("record_detail", table=table, record_id=record_id))
    return render_template("confirm_delete.html", table=table, config=config,
                           record=record, record_id=record_id)


def normalized_skills(values):
    return {str(s).strip().lower() for s in values if str(s).strip()}


def required_skills(raw):
    if not raw:
        return set()
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, dict):
            skills = data.get("skills", [])
            if isinstance(skills, list):
                return normalized_skills(skills)
    except (ValueError, TypeError):
        pass
    return set()


@app.route("/job-match", methods=["GET", "POST"])
def job_match():
    entered = request.form.get("skills", "") if request.method == "POST" else ""
    results = []
    if request.method == "POST":
        user_skills = normalized_skills(entered.split(","))
        jobs = query_all("""SELECT j.job_id, j.job_title, j.requirements, c.company_name
                            FROM jobs j LEFT JOIN companies c ON j.company_id = c.company_id""")
        for job in jobs:
            required = required_skills(job.get("requirements"))
            matched = required & user_skills
            missing = required - user_skills
            percentage = round(100 * len(matched) / len(required)) if required else 0
            results.append({**job, "percentage": percentage, "matched": sorted(matched),
                            "missing": sorted(missing), "total": len(required)})
        results.sort(key=lambda x: (-x["percentage"], x["job_title"].lower()))
    return render_template("job_match.html", entered=entered, results=results,
                           submitted=request.method == "POST")


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1")

# Job Application Tracker — COP4751 Course Project

A Flask + MySQL web app to manage companies, jobs, job applications, and recruiter contacts. Supports Create, Read (lists and details), Update, Delete with confirmation for **all four tables**, plus dashboard statistics and a skill-based Job Match page.

## Requirements
- Python 3.10+
- MySQL 8+
- Git

## Run from a fresh clone (macOS/Linux)

```bash
git clone YOUR_REPOSITORY_URL
cd job_tracker
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your **own local** MySQL username/password and a random `FLASK_SECRET_KEY`. `.env` must **not** be committed to GitHub. Keep MySQL server running.

### Database setup

In MySQL Workbench, connect to your MySQL server, open `schema.sql`, and execute the **entire script**. This creates `job_tracker` and four tables with their foreign keys. It does **not** insert sample data.

### Start

```bash
python app.py
```

Open http://127.0.0.1:5000/ in your browser. If you receive a MySQL connection error, confirm the server is running and the values in `.env` are correct.

## Pages
- `/` — dashboard totals, interviews/offers, recent applications
- `/companies` — company list and CRUD
- `/jobs` — job list and CRUD
- `/applications` — application list and CRUD
- `/contacts` — contacts list and CRUD
- `/job-match` — entered skills ranked against job requirements

For each table: `/<table>/add`, `/<table>/<id>`, `/<table>/<id>/edit`, `/<table>/<id>/delete`. Deletes use a confirmation page. Related records must be deleted or reassigned before their parent can be deleted.

## Job Match

In a job's **Requirements (JSON)** field, enter a JSON object such as:

```json
{"skills": ["Python", "SQL", "Flask"]}
```

On Job Match, enter skills separated by commas. Matching ignores capitalization, whitespace, and duplicate skills. The percentage is `round(matched_required_skills / total_required_skills * 100)`. Jobs without required skills show 0% and a notice. Results are sorted highest first and display matched/missing skills.

## Important design decisions
- Parameterized SQL `%s` prevents input values being interpreted as SQL commands.
- Table names and column names come exclusively from a server-side allowlist.
- MySQL FK rules use `ON DELETE RESTRICT` to protect dependent records.
- JSON requirements and interview data are stored in the specified JSON columns.
- `FLASK_DEBUG=1` is for **local development only**, not a public server.
- This is a course demonstration; no user accounts/authentication are implemented.

## Submission

Include the **3–7 minute real demonstration video file** in this repository (e.g., `demo.mp4`) and ensure it plays from GitHub. Show the browser, Flask server, and MySQL Workbench. Submit the **GitHub repository URL** to the assignment. See `DEMO_CHECKLIST.md`.

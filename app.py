from flask import Flask, render_template, request, redirect, session, send_file
from config import db
from datetime import datetime, date
import pandas as pd
from io import BytesIO
from collections import Counter

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key = "secret123"

app.config['SQLALCHEMY_DATABASE_URI'] = 'import os

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    "DATABASE_URL",
    "sqlite:///database.db"
)'
db.init_app(app)

# ================= DATABASE ================= #

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(50))


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    password = db.Column(db.String(50))
    role_id = db.Column(db.Integer)


class Office(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    office_name = db.Column(db.String(100), unique=True)


class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_no = db.Column(db.String(50))
    case_year = db.Column(db.String(10))
    petitioner = db.Column(db.String(200))
    court = db.Column(db.String(100))
    case_type = db.Column(db.String(100))
    office = db.Column(db.String(100))
    next_hearing = db.Column(db.Date)
    status = db.Column(db.String(50))

    # Prevent duplicates
    __table_args__ = (
        db.UniqueConstraint('case_no', 'case_year', name='unique_case'),
    )


# ================= LOGIN ================= #

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(
            username=request.form["username"],
            password=request.form["password"]
        ).first()

        if user:
            session["user"] = user.username
            session["role"] = user.role_id
            return redirect("/dashboard")

        return render_template("login.html", error="Invalid Username or Password")

    return render_template("login.html", error=None)


# ================= DASHBOARD ================= #

@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/")

    court = request.args.get("court")
    case_type = request.args.get("case_type")
    office = request.args.get("office")
    year = request.args.get("year")

    query = Case.query

    if court:
        query = query.filter_by(court=court)
    if case_type:
        query = query.filter_by(case_type=case_type)
    if office:
        query = query.filter_by(office=office)
    if year:
        query = query.filter_by(case_year=year)

    cases_db = query.all()
    today = date.today()

    processed = []
    red = orange = green = 0

    for c in cases_db:
        days_left = (c.next_hearing - today).days if c.next_hearing else 999

        if days_left <= 7:
            red += 1
        elif days_left <= 15:
            orange += 1
        else:
            green += 1

        processed.append({
            "id": c.id,
            "case_no": c.case_no,
            "year": c.case_year,
            "petitioner": c.petitioner,
            "court": c.court,
            "case_type": c.case_type,
            "office": c.office,
            "next_hearing": c.next_hearing,
            "days_left": days_left
        })

    processed.sort(key=lambda x: x["days_left"])

    # ✅ Chart data restored
    court_counts = Counter([c["court"] for c in processed])
    type_counts = Counter([c["case_type"] for c in processed])
    office_counts = Counter([c["office"] for c in processed])
    year_counts = Counter([str(c["year"]) for c in processed])

    return render_template("dashboard.html",
        cases=processed,
        total=len(processed),
        red=red,
        orange=orange,
        green=green,

        court_labels=list(court_counts.keys()),
        court_data=list(court_counts.values()),

        type_labels=list(type_counts.keys()),
        type_data=list(type_counts.values()),

        office_labels=list(office_counts.keys()),
        office_data=list(office_counts.values()),

        year_labels=list(year_counts.keys()),
        year_data=list(year_counts.values())
    )


# ================= OFFICE ================= #

@app.route("/office", methods=["GET", "POST"])
def office():

    if "user" not in session:
        return redirect("/")

    if request.method == "POST":

        if session.get("role") != 1:
            return "Unauthorized", 403

        office_name = request.form["office"].strip()

        if office_name:
            existing = Office.query.filter_by(office_name=office_name).first()
            if not existing:
                db.session.add(Office(office_name=office_name))
                db.session.commit()

    offices = Office.query.all()
    return render_template("office.html", offices=offices)


@app.route("/delete_office/<int:id>")
def delete_office(id):

    if session.get("role") != 1:
        return "Unauthorized", 403

    office = Office.query.get(id)

    if office:
        db.session.delete(office)
        db.session.commit()

    return redirect("/office")


# ================= ADD CASE ================= #

@app.route("/add_case", methods=["GET", "POST"])
def add_case():

    if session.get("role") != 1:
        return "Unauthorized", 403

    offices = Office.query.all()

    if request.method == "POST":

        nh = request.form.get("next_hearing")
        next_hearing = datetime.strptime(nh, "%Y-%m-%d") if nh else None

        case_no = request.form.get("case_no")
        case_year = request.form.get("year")

        if Case.query.filter_by(case_no=case_no, case_year=case_year).first():
            return "❌ Case already exists!"

        case = Case(
            case_no=case_no,
            case_year=case_year,
            petitioner=request.form.get("petitioner"),
            court=request.form.get("court"),
            case_type=request.form.get("case_type"),
            office=request.form.get("office"),
            next_hearing=next_hearing,
            status="Pending"
        )

        db.session.add(case)
        db.session.commit()

        return redirect("/dashboard")

    return render_template("add_case.html", offices=offices)


# ================= VIEW ================= #

@app.route("/view/<int:id>")
def view_case(id):
    case = Case.query.get(id)

    today = date.today()
    days_left = (case.next_hearing - today).days if case.next_hearing else None

    return render_template("view_case.html", case=case, days_left=days_left)


# ================= EDIT ================= #

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_case(id):

    if session.get("role") != 1:
        return "Unauthorized", 403

    case = Case.query.get(id)
    offices = Office.query.all()

    if request.method == "POST":
        case.case_no = request.form["case_no"]
        case.case_year = request.form["year"]
        case.petitioner = request.form["petitioner"]
        case.court = request.form["court"]
        case.case_type = request.form["case_type"]
        case.office = request.form["office"]
        case.next_hearing = datetime.strptime(request.form["next_hearing"], "%Y-%m-%d")

        db.session.commit()
        return redirect("/dashboard")

    return render_template("edit_case.html", case=case, offices=offices)


# ================= DELETE ================= #

@app.route("/delete/<int:id>")
def delete_case(id):

    if session.get("role") != 1:
        return "Unauthorized", 403

    case = Case.query.get(id)
    db.session.delete(case)
    db.session.commit()

    return redirect("/dashboard")


# ================= EXCEL UPLOAD ================= #

@app.route("/upload", methods=["GET", "POST"])
def upload():

    if session.get("role") != 1:
        return "Unauthorized", 403

    if request.method == "POST":

        file = request.files.get("file")
        if not file:
            return "❌ No file uploaded"

        df = pd.read_excel(file)

        # Safe null handling
        df = df.where(pd.notnull(df), None)

        required_cols = ["Case No","Year","Petitioner","Court","Case Type","Office","Next Hearing"]
        if not all(col in df.columns for col in required_cols):
            return "❌ Invalid Excel Format"

        inserted = 0
        updated = 0

        for _, row in df.iterrows():

            case_no = str(row["Case No"]).strip() if row["Case No"] else ""
            case_year = str(row["Year"]).strip() if row["Year"] else ""

            if not case_no or not case_year:
                continue

            next_hearing = pd.to_datetime(row["Next Hearing"]).date() if pd.notna(row["Next Hearing"]) else None

            existing_case = Case.query.filter_by(
                case_no=case_no,
                case_year=case_year
            ).first()

            if existing_case:
                if existing_case.next_hearing != next_hearing:
                    existing_case.next_hearing = next_hearing

                existing_case.petitioner = row["Petitioner"]
                existing_case.court = row["Court"]
                existing_case.case_type = row["Case Type"]
                existing_case.office = row["Office"]

                updated += 1

            else:
                new_case = Case(
                    case_no=case_no,
                    case_year=case_year,
                    petitioner=row["Petitioner"],
                    court=row["Court"],
                    case_type=row["Case Type"],
                    office=row["Office"],
                    next_hearing=next_hearing,
                    status="Pending"
                )
                db.session.add(new_case)
                inserted += 1

        db.session.commit()

        return f"✅ Upload Done | Inserted: {inserted}, Updated: {updated}"

    return render_template("upload.html")


# ================= EXCEL DOWNLOAD ================= #

@app.route('/download_excel')
def download_excel():

    cases = Case.query.all()
    today = date.today()

    data = []
    for c in cases:
        days_left = (c.next_hearing - today).days if c.next_hearing else ""

        data.append({
            "Case No": c.case_no,
            "Year": c.case_year,
            "Petitioner": c.petitioner,
            "Court": c.court,
            "Case Type": c.case_type,
            "Office": c.office,
            "Next Hearing": c.next_hearing,
            "Days Left": days_left
        })

    df = pd.DataFrame(data)
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(output, download_name="Litigation_Report.xlsx", as_attachment=True)


# ================= PDF DOWNLOAD ================= #

@app.route('/download_pdf')
def download_pdf():

    cases = Case.query.all()
    today = date.today()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Collectorate Litigation Report", styles['Title']))

    data = [["Case No", "Year", "Petitioner", "Court", "Case Type", "Office", "Next Hearing", "Days Left"]]

    for c in cases:
        days_left = (c.next_hearing - today).days if c.next_hearing else ""

        data.append([
            c.case_no, c.case_year, c.petitioner,
            c.court, c.case_type, c.office,
            str(c.next_hearing), str(days_left)
        ])

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    return send_file(buffer, download_name="Litigation_Report.pdf", as_attachment=True)


# ================= LOGOUT ================= #

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================= RUN ================= #

if __name__ == "__main__":

    with app.app_context():
        db.create_all()

        if not Role.query.first():
            db.session.add(Role(id=1, role_name="Admin"))
            db.session.add(Role(id=2, role_name="Viewer"))
            db.session.commit()

        if not User.query.first():
            db.session.add(User(username="admin", password="admin123", role_id=1))
            db.session.add(User(username="viewer", password="viewer123", role_id=2))
            db.session.commit()

    app.run(host="0.0.0.0", port=5000, debug=True)
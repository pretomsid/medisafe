"""Database টেবিল। প্রতিটা model-এর to_dict() ঠিক করে frontend কোন নামে data পাবে।
Frontend-এর field নাম বদলালে শুধু to_dict() বদলালেই চলবে।"""
from datetime import date, datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def iso(d):
    return d.isoformat() if d else ""


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    dob = db.Column(db.String(10))
    gender = db.Column(db.String(10))
    blood = db.Column(db.String(4))
    height = db.Column(db.Float)
    weight = db.Column(db.Float)
    allergies = db.Column(db.JSON, default=list)
    conditions = db.Column(db.JSON, default=list)
    ec_name = db.Column(db.String(120))
    ec_phone = db.Column(db.String(20))

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def to_dict(self):
        return {"name": self.name, "email": self.email, "phone": self.phone or "",
                "dob": self.dob or "", "gender": self.gender or "", "blood": self.blood or "",
                "height": self.height, "weight": self.weight,
                "allergies": self.allergies or [], "conditions": self.conditions or [],
                "ecName": self.ec_name or "", "ecPhone": self.ec_phone or ""}


class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    record_date = db.Column(db.String(10))
    original_name = db.Column(db.String(255))
    stored_name = db.Column(db.String(64))  # random নাম, আসল নাম দিয়ে disk-এ রাখা হয় না
    note = db.Column(db.String(255), default="")

    def to_dict(self):
        return {"id": self.id, "title": self.title, "cat": self.category,
                "date": self.record_date or "", "file": self.original_name or "", "note": self.note or ""}


class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    ingredient = db.Column(db.String(120))
    strength = db.Column(db.String(40))
    dose = db.Column(db.String(60))
    freq = db.Column(db.String(60))
    start = db.Column(db.String(10))
    end = db.Column(db.String(10))
    status = db.Column(db.String(10), default="Current")  # বন্ধ হলে delete না করে "Previous" (history থাকে)

    FIELDS = ["name", "ingredient", "strength", "dose", "freq", "start", "end", "status"]

    def to_dict(self):
        return {"id": self.id, **{f: getattr(self, f) or "" for f in self.FIELDS}}


class Product(db.Model):
    """ওষুধের catalog (সব user-এর জন্য এক)। Data আসে model2/medicine.csv থেকে।"""
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.String(20), index=True)          # medicine.csv-এর brand id (model-এর সাথে মেলানোর জন্য)
    brand = db.Column(db.String(120), nullable=False, index=True)
    generic = db.Column(db.String(255), nullable=False, index=True)
    strength = db.Column(db.String(120))
    form = db.Column(db.String(80), index=True)
    maker = db.Column(db.String(120))
    type = db.Column(db.String(20), default="allopathic")
    price = db.Column(db.Float)                               # package-এর প্রথম তালিকাভুক্ত দাম (৳)
    package = db.Column(db.String(255))                       # যেমন "Unit Price: ৳ 15.00,(20's pack...)"
    source = db.Column(db.String(40), default="medicine.csv")

    def to_dict(self):
        return {"id": self.id, "brand": self.brand, "generic": self.generic, "strength": self.strength,
                "form": self.form, "maker": self.maker, "type": self.type, "price": self.price,
                "package": self.package or ""}


class Generic(db.Model):
    """Generic (active ingredient)-এর তথ্য। Data আসে model2/generic.csv থেকে।
    interaction/contraindication লেখা monograph-এর বর্ণনা, কোনো risk label নয়।"""
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.String(20))
    name = db.Column(db.String(255), nullable=False)
    name_key = db.Column(db.String(255), index=True)          # ছোট হাতের, খোঁজার জন্য
    drug_class = db.Column(db.String(255))
    indication = db.Column(db.String(255))
    interaction_text = db.Column(db.Text)
    contraindication_text = db.Column(db.Text)


class KnownInteraction(db.Model):
    """যাচাই করা (verified) drug interaction। AI model আসার আগেও এটা কাজ করে।
    DDInter 2.0-এর Major/Moderate/Minor pair-গুলো import-data দিয়ে এখানে আসে।"""
    __table_args__ = (db.Index("ix_known_pair", "generic_a", "generic_b"),)
    id = db.Column(db.Integer, primary_key=True)
    generic_a = db.Column(db.String(120), nullable=False)  # সবসময় ছোট নামটা a-তে (A+B = B+A)
    generic_b = db.Column(db.String(120), nullable=False)
    severity = db.Column(db.String(20), nullable=False)    # low / moderate / high
    text = db.Column(db.String(255))
    source = db.Column(db.String(120))


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    type = db.Column(db.String(20))
    title = db.Column(db.String(200))
    text = db.Column(db.String(255))
    created = db.Column(db.Date, default=date.today)
    read = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {"id": self.id, "type": self.type, "title": self.title, "text": self.text,
                "date": iso(self.created), "read": self.read}


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    text = db.Column(db.String(255))
    created = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {"text": self.text, "date": self.created.date().isoformat()}


def log(user_id, text):
    db.session.add(Activity(user_id=user_id, text=text))

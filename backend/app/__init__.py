"""App factory: সব অংশ (database, API blueprint) এখানে জোড়া লাগে।
নতুন feature = নতুন blueprint ফাইল + এখানে এক লাইন register।"""
import os

from flask import Flask, abort, jsonify, send_from_directory

from .config import Config
from .models import db


def _add_missing_columns():
    """db.create_all() never alters existing tables, so columns added later are created here (idempotent)."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)
        for table in db.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have:
                    ddl = col.type.compile(dialect=db.engine.dialect)
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))
    except Exception:
        pass


def create_app(config=Config):
    app = Flask(__name__)
    app.config.from_object(config)
    db.init_app(app)

    from . import auth, interactions, routes, seed
    app.register_blueprint(auth.bp)
    app.register_blueprint(routes.bp)
    app.register_blueprint(interactions.bp)
    app.cli.add_command(seed.import_command)
    app.cli.add_command(seed.check_live_apis_command)

    with app.app_context():
        from sqlalchemy import event
        @event.listens_for(db.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            if "sqlite" not in db.engine.dialect.name:
                return
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()
            except Exception:
                pass

        try:
            db.create_all()
        except Exception:
            pass
        _add_missing_columns()
        # Model 1 (interaction risk) JSON থাকলে তবেই লাগানো হয়, তাই "connected" সবসময় সত্যি কথা বলে
        from .ai import interaction_adapter
        interactions.set_predictor(interaction_adapter.predict if interaction_adapter.available() else None)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(error="Not found"), 404

    @app.errorhandler(413)
    def too_large(e):
        return jsonify(error="File is larger than 10 MB"), 413

    # একই server থেকে frontend দেখানো (same-origin, তাই cookie সহজে কাজ করে)।
    # শুধু .html আর assets/ দেওয়া হয়, backend-এর ফাইল কখনো না।
    front = app.config.get("FRONTEND_DIR")
    if front:
        @app.get("/")
        def index():
            return send_from_directory(front, "index.html")

        @app.get("/favicon.ico")
        def favicon():
            fav = os.path.join(front, "assets", "favicon.ico")
            if os.path.exists(fav):
                return send_from_directory(os.path.join(front, "assets"), "favicon.ico")
            return "", 204

        @app.get("/<path:path>")
        def frontend(path):
            if path.endswith(".html") or path.startswith("assets/"):
                return send_from_directory(front, path)
            abort(404)

    return app

"""MediSafe Application Runner (Flask).

Starts the MediSafe Clinical Decision Support web server on http://127.0.0.1:5000.
"""
import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG") == "1"
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")

    print("=" * 60)
    print("  MediSafe Clinical Decision Support System (Flask)")
    print(f"  • Web App:              http://{host}:{port}")
    print("  • Database:             SQLite (WAL Mode Enabled)")
    print("  • Models:               Model 1 (DDI) & Model 2 (Alternatives)")
    print("  • Real-time APIs:       DDInter 2.0 & OpenFDA Active")
    print("=" * 60)

    app.run(host=host, port=port, debug=debug)

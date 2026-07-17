"""
app.py — Entry point for the Cloudflare GraphQL API service.

This file is intentionally thin: it creates the Flask application, registers
the routes Blueprint, and starts the development server. All business logic
lives in lib/.

Module layout:
    lib/config.py      — Cloudflare credentials and query tuning constants
    lib/cloudflare.py  — Cloudflare Analytics GraphQL API client (three query functions)
    lib/pipeline.py    — Data processing: path cleaning, aggregation, CSV export, time ranges
    lib/classifier.py  — Path classifier: maps cambridge.org paths to drupal / c5 / unmatched
    lib/logger.py      — HTTP error log manager (error_400.log / error_500.log)
    lib/routes.py      — Flask Blueprint with all route handlers
"""

import os

from flask import Flask
from lib.config import validate_config
from lib.routes import bp

validate_config()

app = Flask(__name__)
app.register_blueprint(bp)

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', '0') == '1', port=5000)

"""Vercel serverless entrypoint.

Routes every request (/, /api/*, /static/*) to the LocalPulse Flask app.
Vercel imports this module and looks for a WSGI callable named ``app``
(``vercel_app`` is also exported as an alias for compatibility).

Note: web/app.py performs its own sys.path setup (``PROJECT_ROOT`` derived
from ``__file__``), which resolves to /var/task under Vercel's layout, so the
core/ imports work without any change there. We add the project root to
sys.path as well for robustness when the handler is imported directly.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent

for _p in (str(PROJECT_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from web.app import app as flask_app  # noqa: E402

app = flask_app          # primary WSGI callable for Vercel
vercel_app = flask_app   # explicit alias some presets look for
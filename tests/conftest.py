import os
import pathlib
import tempfile

# Configure the test environment before the app (and its settings) are imported.
_db_path = pathlib.Path(tempfile.gettempdir()) / "syncfit_backend_test.db"
if _db_path.exists():
    _db_path.unlink()
os.environ["SYNCFIT_DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["BACKEND_SECRET_KEY"] = "test-secret-key-with-at-least-32-bytes!!"
os.environ["SUPERADMIN_EMAIL"] = "root@syncfit.dev"
os.environ["SUPERADMIN_PASSWORD"] = "rootsecret123"
os.environ["SUPERADMIN_NAME"] = "Root"

# Force the offline AI path: an empty key makes OpenCodeGoClient raise, so tests
# stay fast and deterministic (no network) whether or not syncfit-ai is installed.
os.environ["REASONING_API_KEY"] = ""
os.environ["OPENCODE_API_KEY"] = ""

from app import create_app
from app.db_patch import run_schema_patch

app = create_app()
with app.app_context():
    print("Executing schema patch...")
    run_schema_patch()
    print("Done.")

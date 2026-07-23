import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


with tempfile.TemporaryDirectory() as temporary_directory:
    database_path = Path(temporary_directory) / "ticketflow-test.sqlite3"
    os.environ["DEBUG"] = "True"
    os.environ["SECRET_KEY"] = "automated-test-secret"
    os.environ["SQLITE_PATH"] = str(database_path)
    os.environ["APP_NAME"] = "TicketFlow Community"

    from run import app
    from apps import db
    from apps.authentication.models import Users

    with app.app_context():
        db.create_all()

    runner = app.test_cli_runner()
    result = runner.invoke(args=[
        "create-admin",
        "--username", "community-admin",
        "--email", "admin@example.org",
        "--password", "temporary-test-password",
    ])
    assert result.exit_code == 0, result.output

    client = app.test_client()
    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert b"TicketFlow" in login_page.data

    response = client.post("/login", data={
        "login": "1",
        "username": "community-admin",
        "password": "temporary-test-password",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Dashboard" in response.data

    kanban = client.get("/tablero-kanban")
    assert kanban.status_code == 200
    assert b"Tablero Kanban" in kanban.data
    assert b"kanban-board" in kanban.data

    with app.app_context():
        admin = Users.query.filter_by(username="community-admin").first()
        assert admin is not None
        assert admin.rol == "Administrador"
        db.session.remove()
        db.engine.dispose()

print("TicketFlow Community smoke test passed")

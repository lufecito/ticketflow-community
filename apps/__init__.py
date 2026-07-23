# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

import os
import click

from flask import Flask
from authlib.integrations.flask_client import OAuth
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from importlib import import_module
from sqlalchemy import text


db = SQLAlchemy()
login_manager = LoginManager()
oauth = OAuth()


def register_extensions(app):
    db.init_app(app)
    login_manager.init_app(app)
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )


def register_blueprints(app):
    for module_name in ('authentication', 'home'):
        module = import_module('apps.{}.routes'.format(module_name))
        app.register_blueprint(module.blueprint)


def configure_database(app):

    @app.before_first_request
    def initialize_database():
        try:
            db.create_all()
            migrate_legacy_users()
        except Exception as e:

            print('> Error: DBMS Exception: ' + str(e) )

            # fallback to SQLite
            basedir = os.path.abspath(os.path.dirname(__file__))
            sqlite_path = os.getenv('SQLITE_PATH', os.path.join(basedir, 'db.sqlite3'))
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.abspath(sqlite_path)

            print('> Fallback to SQLite ')
            db.create_all()
            migrate_legacy_users()

    @app.teardown_request
    def shutdown_session(exception=None):
        db.session.remove()


def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)
    register_extensions(app)
    register_blueprints(app)
    configure_database(app)
    register_commands(app)

    @app.context_processor
    def inject_branding():
        return {'app_name': app.config.get('APP_NAME', 'Ticket Kanban')}

    return app


def register_commands(app):
    @app.cli.command('create-admin')
    @click.option('--username', prompt=True)
    @click.option('--email', prompt=True)
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(username, email, password):
        """Create the first administrator account."""
        from apps.authentication.models import Users

        db.create_all()
        if Users.query.filter((Users.username == username) | (Users.email == email)).first():
            raise click.ClickException('A user with that username or email already exists.')
        db.session.add(Users(
            username=username,
            email=email,
            password=password,
            rol='Administrador',
            activo=True,
        ))
        db.session.commit()
        click.echo('Administrator created successfully.')


def migrate_legacy_users():
    if db.engine.dialect.name != 'sqlite':
        return
    legacy_table = db.session.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='Users'"
    )).first()
    if not legacy_table:
        return

    legacy_users = db.session.execute(text(
        "SELECT username, email, password FROM Users"
    )).fetchall()
    for username, email, password in legacy_users:
        exists = db.session.execute(
            text("SELECT id FROM usuarios WHERE username = :username"),
            {'username': username}
        ).first()
        if not exists:
            db.session.execute(
                text(
                    "INSERT INTO usuarios (username, email, password, rol, activo) "
                    "VALUES (:username, :email, :password, 'Tecnico', 1)"
                ),
                {'username': username, 'email': email, 'password': password}
            )
    db.session.execute(text("DROP TABLE Users"))
    db.session.commit()

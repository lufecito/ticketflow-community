# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from flask import abort, current_app, render_template, redirect, request, url_for
from flask_login import (
    current_user,
    login_user,
    logout_user
)

from apps import db, login_manager, oauth
from apps.authentication import blueprint
from apps.authentication.forms import LoginForm
from apps.authentication.models import Users

from apps.authentication.util import verify_pass


GOOGLE_CLIENT_ROLE = 'Cliente'


@blueprint.route('/')
def route_default():
    return redirect(url_for('authentication_blueprint.login'))


# Login & Registration

@blueprint.route('/login', methods=['GET', 'POST'])
def login():
    login_form = LoginForm(request.form)
    if 'login' in request.form:

        # read form data
        username = request.form['username']
        password = request.form['password']

        # Locate user
        user = Users.query.filter_by(username=username).first()

        # Check the password
        if user and user.activo and verify_pass(password, user.password):

            login_user(user)
            return redirect(url_for('authentication_blueprint.route_default'))

        # Something (user or pass) is not ok
        return render_template('accounts/login.html',
                               msg='Wrong user or password',
                               form=login_form)

    if not current_user.is_authenticated:
        return render_template('accounts/login.html',
                               form=login_form)
    return redirect(url_for('home_blueprint.index'))


@blueprint.route('/login/google')
def google_login():
    if current_user.is_authenticated:
        return redirect(url_for('home_blueprint.index'))

    if not current_app.config.get('GOOGLE_CLIENT_ID') or not current_app.config.get('GOOGLE_CLIENT_SECRET'):
        return render_template(
            'accounts/login.html',
            msg='Google OAuth no estÃ¡ configurado',
            form=LoginForm(),
        )

    redirect_uri = url_for('authentication_blueprint.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@blueprint.route('/login/google/callback')
def google_callback():
    token = oauth.google.authorize_access_token()
    user_info = token.get('userinfo')
    if not user_info:
        user_info = oauth.google.get('https://openidconnect.googleapis.com/v1/userinfo').json()

    email = (user_info.get('email') or '').strip().lower()
    if not email:
        return render_template(
            'accounts/login.html',
            msg='No fue posible obtener el correo desde Google',
            form=LoginForm(),
        )

    allowed_domain = current_app.config.get('GOOGLE_ALLOWED_DOMAIN', '')
    hosted_domain = (user_info.get('hd') or '').strip().lower()
    if allowed_domain and hosted_domain != allowed_domain:
        return render_template(
            'accounts/login.html',
            msg='Esta cuenta no pertenece al dominio autorizado',
            form=LoginForm(),
        )

    user = Users.query.filter_by(email=email).first()
    if not user:
        if not current_app.config.get('GOOGLE_AUTO_PROVISION', False):
            return render_template(
                'accounts/login.html',
                msg='Tu cuenta aún no ha sido autorizada por un administrador',
                form=LoginForm(),
            )
        user = Users(
            username=_unique_google_username(email),
            email=email,
            nombre=(user_info.get('given_name') or user_info.get('name') or '').strip(),
            apellido=(user_info.get('family_name') or '').strip(),
            rol=GOOGLE_CLIENT_ROLE,
            activo=True,
        )
        db.session.add(user)
        db.session.commit()

    if not user.activo:
        return render_template(
            'accounts/login.html',
            msg='Usuario inactivo',
            form=LoginForm(),
        )

    login_user(user)
    return redirect(url_for('authentication_blueprint.route_default'))


@blueprint.route('/register', methods=['GET', 'POST'])
def register():
    abort(403)


@blueprint.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('authentication_blueprint.login'))


# Errors

@login_manager.unauthorized_handler
def unauthorized_handler():
    return redirect(url_for('authentication_blueprint.login'))


def _unique_google_username(email):
    base_username = email.split('@', 1)[0].strip().lower() or 'google_user'
    username = base_username[:64]
    suffix = 1

    while Users.query.filter_by(username=username).first():
        suffix_text = str(suffix)
        max_base_length = 64 - len(suffix_text) - 1
        username = f'{base_username[:max_base_length]}_{suffix_text}'
        suffix += 1

    return username


@blueprint.errorhandler(403)
def access_forbidden(error):
    return render_template('home/page-403.html'), 403


@blueprint.errorhandler(404)
def not_found_error(error):
    return render_template('home/page-404.html'), 404


@blueprint.errorhandler(500)
def internal_error(error):
    return render_template('home/page-500.html'), 500

import secrets
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

auth_bp = Blueprint('auth', __name__)


# ── Intercepta toda requisição: redireciona para troca de senha obrigatória ──

@auth_bp.before_app_request
def enforce_password_change():
    allowed = {'auth.change_password', 'auth.logout', 'static'}
    if (
        current_user.is_authenticated
        and current_user.must_change_password
        and request.endpoint not in allowed
    ):
        return redirect(url_for('auth.change_password'))


# ── Login / Logout ────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('password', '')
        from ..database.models import db, User
        session = db.get_session()
        try:
            user = session.query(User).filter_by(email=email, active=True).first()
            if user and check_password_hash(user.password_hash, senha):
                user.last_login = datetime.now()
                session.commit()
                login_user(user, remember=True)
                next_url = request.args.get('next') or url_for('index')
                return redirect(next_url)
        finally:
            session.close()
        flash('E-mail ou senha incorretos.', 'danger')
    return render_template('login.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# ── Auto-cadastro: solicita acesso ────────────────────────────────────────────

@auth_bp.route('/register', methods=['POST'])
def register():
    """Recebe nome + email e envia convite de ativação por email."""
    data = request.get_json(silent=True) or {}
    name  = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()

    if not name or not email or '@' not in email:
        return jsonify({'status': 'error', 'message': 'Nome e e-mail válidos são obrigatórios'}), 400

    from ..database.models import db, User
    session = db.get_session()
    try:
        if session.query(User).filter_by(email=email).first():
            return jsonify({'status': 'error', 'message': 'E-mail já cadastrado'}), 409

        token = secrets.token_urlsafe(32)
        expires = datetime.now() + timedelta(hours=48)
        user = User(
            name=name,
            email=email,
            role='viewer',
            active=True,
            must_change_password=True,
            invite_token=token,
            token_expires_at=expires,
            password_hash=generate_password_hash(secrets.token_urlsafe(16)),
        )
        session.add(user)
        session.commit()

        _send_invite_email(user, request.host_url)
        return jsonify({'status': 'success', 'message': 'Verifique seu e-mail para ativar o acesso'})
    except Exception as e:
        session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        session.close()


# ── Ativação via token ────────────────────────────────────────────────────────

@auth_bp.route('/activate/<token>', methods=['GET', 'POST'])
def activate(token):
    from ..database.models import db, User
    session = db.get_session()
    try:
        user = session.query(User).filter(
            User.invite_token == token,
            User.token_expires_at > datetime.now(),
        ).first()

        if not user:
            flash('Link de ativação inválido ou expirado. Solicite um novo convite.', 'danger')
            return redirect(url_for('auth.login'))

        if request.method == 'GET':
            return render_template('activate.html', token=token)

        # POST — define senha
        senha  = request.form.get('password', '')
        senha2 = request.form.get('password2', '')
        if len(senha) < 8:
            flash('A senha deve ter pelo menos 8 caracteres.', 'danger')
            return render_template('activate.html', token=token)
        if senha != senha2:
            flash('As senhas não conferem.', 'danger')
            return render_template('activate.html', token=token)

        user.password_hash      = generate_password_hash(senha)
        user.invite_token       = None
        user.token_expires_at   = None
        user.last_login         = datetime.now()
        session.commit()
        login_user(user, remember=True)
        return redirect(url_for('auth.change_password'))
    finally:
        session.close()


# ── Troca de senha (obrigatória no 1º acesso ou voluntária) ──────────────────

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'GET':
        return render_template('change_password.html')

    from ..database.models import db, User
    session = db.get_session()
    try:
        user = session.query(User).get(current_user.id)

        nova   = request.form.get('new_password', '')
        nova2  = request.form.get('new_password2', '')

        if len(nova) < 8:
            flash('A nova senha deve ter pelo menos 8 caracteres.', 'danger')
            return render_template('change_password.html')
        if nova != nova2:
            flash('As senhas não conferem.', 'danger')
            return render_template('change_password.html')

        # Troca voluntária: exige senha atual
        if not user.must_change_password:
            atual = request.form.get('current_password', '')
            if not check_password_hash(user.password_hash, atual):
                flash('Senha atual incorreta.', 'danger')
                return render_template('change_password.html')

        user.password_hash        = generate_password_hash(nova)
        user.must_change_password = False
        session.commit()
        flash('Senha alterada com sucesso!', 'success')
        return redirect(url_for('index'))
    finally:
        session.close()


# ── Helper: envio de email de convite ─────────────────────────────────────────

def _send_invite_email(user, base_url):
    """Envia email HTML com link de ativação."""
    try:
        from ..alerts.email_sender import EmailSender
        activation_link = f"{base_url.rstrip('/')}/activate/{user.invite_token}"
        subject = "Seu acesso ao Monitoramento Solar foi criado"
        body = f"""<html><body style="font-family:sans-serif;color:#212529;padding:24px">
<h2 style="color:#146c2e">Bem-vindo ao Monitoramento Solar!</h2>
<p>Olá, <strong>{user.name}</strong>!</p>
<p>Sua conta foi criada com perfil <strong>{user.role}</strong>.
Clique no botão abaixo para definir sua senha e ativar o acesso:</p>
<p style="margin:32px 0">
  <a href="{activation_link}"
     style="background:#146c2e;color:#fff;padding:14px 28px;border-radius:6px;
            text-decoration:none;font-weight:600;font-size:1rem">
    Ativar minha conta
  </a>
</p>
<p style="color:#595959;font-size:.9rem">
  Este link é válido por 48 horas.<br>
  Se você não solicitou este acesso, ignore este e-mail.
</p>
<hr style="border:none;border-top:1px solid #dee2e6;margin:24px 0">
<p style="color:#595959;font-size:.8rem">Link direto: {activation_link}</p>
</body></html>"""
        sender = EmailSender()
        sender.send_email(
            subject=subject,
            body=body,
            html=True,
            recipients=[user.email],
            email_type='invitation',
        )
    except Exception as e:
        # Email falha silenciosamente — token ainda está no banco
        from ..utils.logger import logger
        logger.warning(f"Falha ao enviar email de convite para {user.email}: {e}")

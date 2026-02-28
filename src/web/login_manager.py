from flask_login import LoginManager

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Faça login para acessar esta página.'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    from ..database.models import db, User
    session = db.get_session()
    try:
        return session.query(User).filter_by(id=int(user_id), active=True).first()
    finally:
        session.close()


@login_manager.unauthorized_handler
def unauthorized():
    from flask import request, jsonify, redirect, url_for
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"status": "error", "message": "Autenticação necessária"}), 401
    return redirect(url_for('auth.login', next=request.path))

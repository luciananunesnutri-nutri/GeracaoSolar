from functools import wraps
from flask import jsonify, request, redirect, url_for, abort
from flask_login import current_user


def api_login_required(f):
    """Decorator para rotas de API: retorna JSON 401 em vez de redirecionar."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"status": "error", "message": "Autenticação necessária"}), 401
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Decorator que exige autenticação e que o usuário tenha um dos roles informados.

    Para rotas de API (Accept: application/json ou /api/): retorna JSON 401/403.
    Para rotas HTML: redireciona para login (401) ou aborta com 403.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            is_api = (
                request.path.startswith('/api/')
                or 'application/json' in request.headers.get('Accept', '')
                or request.is_json
            )
            if not current_user.is_authenticated:
                if is_api:
                    return jsonify({"status": "error", "message": "Autenticação necessária"}), 401
                return redirect(url_for('auth.login', next=request.path))
            if current_user.role not in roles:
                if is_api:
                    return jsonify({"status": "error", "message": "Sem permissão"}), 403
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator

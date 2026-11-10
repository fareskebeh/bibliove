from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
load_dotenv()
import os

from flask import request
from flask_wtf.csrf import validate_csrf
from wtforms.validators import ValidationError


def csrf_valid():
    token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')
    try:
        validate_csrf(token)
    except ValidationError:
        return False
    return True


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300 per minute", "10000 per day"],
    storage_uri=f"redis://{os.getenv('REDIS_URI')}",
)


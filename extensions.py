from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
load_dotenv()
import os

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300 per minute", "10000 per day"],
    storage_uri=f"redis://{os.getenv('REDIS_URI')}",
)


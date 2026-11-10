import os

import redis
from dotenv import load_dotenv
from rq import Queue

load_dotenv()

rd = redis.Redis.from_url(f"redis://{os.getenv('REDIS_URI', '127.0.0.1:6379')}")
ocr_queue = Queue('ocr', connection=rd)

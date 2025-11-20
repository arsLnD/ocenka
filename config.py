import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
DATABASE_URL = os.getenv('DATABASE_URL')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в .env файле")

if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS не установлены в .env файле")
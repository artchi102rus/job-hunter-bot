
import os
import json
from urllib.request import Request, urlopen

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

data = json.dumps({
    "chat_id": CHAT_ID,
    "text": "🚀 Job Hunter запущен!\n\n"
            "✅ Подключение к Telegram работает.\n"
            "🔎 Скоро начну искать вакансии!"
}).encode("utf-8")

request = Request(
    url,
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST"
)

with urlopen(request, timeout=20) as response:
    print("Telegram response:", response.status)

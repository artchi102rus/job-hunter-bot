
import os
import json
import html
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
HH_TOKEN = os.getenv("HH_ACCESS_TOKEN", "")
STATE_FILE = Path("seen_jobs.json")

SEARCH_TEXT = "техническая поддержка"
MAX_MESSAGES = 5


def request_json(url, data=None, headers=None):
    req = Request(
        url,
        data=data,
        headers=headers or {},
    )
    with urlopen(req, timeout=25) as response:
        return json.load(response)


def send_message(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = urlencode({
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    request_json(url, payload)


def load_seen():
    if STATE_FILE.exists():
        return set(json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        ))
    return set()


def save_seen(seen):
    STATE_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False),
        encoding="utf-8"
    )


def search_jobs():
    params = {
        "text": SEARCH_TEXT,
        "work_format": "REMOTE",
        "order_by": "publication_time",
        "period": 1,
        "per_page": 100,
        "page": 0,
    }

    url = "https://api.hh.ru/vacancies?" + urlencode(params)

    headers = {
        "User-Agent": "JobHunterBot/1.0 (personal-job-monitor)"
    }

    if HH_TOKEN:
        headers["Authorization"] = f"Bearer {HH_TOKEN}"

    result = request_json(url, headers=headers)
    return result.get("items", [])


def suitable(job):
    title = job.get("name", "").lower()

    relevant = [
        "поддерж",
        "support",
        "helpdesk",
        "help desk",
        "service desk",
    ]
    excluded = [
        "руководитель",
        "директор",
        "начальник",
        "продаж",
        "телемаркет",
        "колл-центр",
        "call center",
    ]

    if not any(word in title for word in relevant):
        return False

    if any(word in title for word in excluded):
        return False

    return True


def format_salary(job):
    salary = job.get("salary") or job.get("salary_range")

    if not salary:
        return "Не указана"

    low = salary.get("from")
    high = salary.get("to")
    currency = salary.get("currency", "")

    if low and high:
        return f"{low:,}–{high:,} {currency}"
    if low:
        return f"от {low:,} {currency}"
    if high:
        return f"до {high:,} {currency}"

    return "Не указана"


def format_job(job):
    name = html.escape(job.get("name", "Вакансия"))
    company = html.escape(
        (job.get("employer") or {}).get("name", "Не указана")
    )
    salary = html.escape(format_salary(job))
    link = html.escape(
        job.get("alternate_url", ""), quote=True
    )

    return (
        f"🔎 <b>{name}</b>\n\n"
        f"🏢 {company}\n"
        f"🏠 Удалённая работа\n"
        f"💰 {salary}\n\n"
        f'<a href="{link}">Открыть вакансию</a>'
    )


def main():
    seen = load_seen()

    try:
        jobs = search_jobs()
    except (HTTPError, URLError) as error:
        print(f"HH API error: {error}")
        if isinstance(error, HTTPError) and error.code in (403, 429):
            send_message(
                "⚠️ HH.ru ограничил доступ к поиску. "
                "Может потребоваться официальная авторизация."
            )
        raise

    print(f"Получено вакансий: {len(jobs)}")

    new_jobs = [
        job for job in jobs
        if suitable(job) and str(job["id"]) not in seen
    ]

    print(f"Новых подходящих: {len(new_jobs)}")

    for job in new_jobs[:MAX_MESSAGES]:
        send_message(format_job(job))
        seen.add(str(job["id"]))
        save_seen(seen)

    if not new_jobs:
        print("Новых вакансий нет")

    print("Поиск завершён")


if __name__ == "__main__":
    main()

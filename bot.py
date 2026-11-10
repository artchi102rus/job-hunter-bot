
import os
import json
import html
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = Path("seen_jobs.json")
MAX_MESSAGES = 5

KEYWORDS = [
    "support", "helpdesk", "help desk",
    "service desk", "customer success",
    "customer care", "technical assistance",
    "qa tester", "qa analyst",
    "manual tester", "quality assurance",
    "ai trainer", "ai data", "data annotator",
    "data quality",
]

EXCLUDED = [
    "director", "head of", "vice president",
    "senior software engineer", "sales executive",
    "account executive", "call center",
    "telemarketing",
]

BLOCKED_LOCATIONS = [
    "us only", "usa only", "united states only",
    "canada only", "uk only",
]


def get_json(url, data=None):
    request = Request(
        url,
        data=data,
        headers={
            "User-Agent": "JobHunterBot/1.0",
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=30) as response:
        return json.load(response)


def send_message(text):
    from urllib.parse import urlencode

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    payload = urlencode({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    get_json(url, payload)
    print("Telegram message sent", flush=True)


def load_seen():
    if not STATE_FILE.exists():
        return set()

    return set(json.loads(
        STATE_FILE.read_text(encoding="utf-8")
    ))


def save_seen(seen):
    STATE_FILE.write_text(
        json.dumps(sorted(seen)),
        encoding="utf-8",
    )


def search_jobs():
    url = "https://remotive.com/api/remote-jobs"
    result = get_json(url)

    jobs = result.get("jobs", [])
    print("Received jobs:", len(jobs), flush=True)

    return jobs


def suitable(job):
    title = job.get("title", "").lower()
    location = job.get(
        "candidate_required_location", ""
    ).lower()

    if not any(word in title for word in KEYWORDS):
        return False

    if any(word in title for word in EXCLUDED):
        return False

    if any(word in location for word in BLOCKED_LOCATIONS):
        return False

    return True


def format_job(job):
    title = html.escape(job.get("title") or "")
    company = html.escape(job.get("company_name") or "")
    location = html.escape(
        job.get("candidate_required_location") or "Не указано"
    )
    salary = html.escape(
        job.get("salary") or "Не указана"
    )
    link = html.escape(job.get("url") or "", quote=True)

    return (
        f"🔎 <b>{title}</b>\n\n"
        f"🏢 {company}\n"
        f"🌍 Регион: {location}\n"
        f"💰 Зарплата: {salary}\n"
        f"📌 Источник: Remotive\n\n"
        f'<a href="{link}">Открыть вакансию</a>\n\n'
        f"⚠️ Проверь звонки, английский "
        f"и возможность работы из Вьетнама."
    )


def main():
    print("Job Hunter started", flush=True)

    seen = load_seen()
    first_run = len(seen) == 0

    try:
        jobs = search_jobs()
    except (HTTPError, URLError) as error:
        print("Remotive request failed:", error, flush=True)
        raise

    matching = [job for job in jobs if suitable(job)]

    new_jobs = [
        job for job in matching
        if f"remotive:{job['id']}" not in seen
    ]

    print("Matching jobs:", len(matching), flush=True)
    print("New jobs:", len(new_jobs), flush=True)

    for job in new_jobs[:MAX_MESSAGES]:
        send_message(format_job(job))

        seen.add(f"remotive:{job['id']}")
        save_seen(seen)

    if first_run and not new_jobs:
        send_message(
            "✅ Job Hunter работает!\n"
            "🔎 Remotive проверен.\n"
            "Подходящих вакансий пока не найдено."
        )

    print("Job Hunter finished", flush=True)


if __name__ == "__main__":
    main()

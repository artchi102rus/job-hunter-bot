
import os
import json
import html
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

# ========== SETTINGS ==========

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
HH_TOKEN = os.getenv("HH_ACCESS_TOKEN", "")

STATE_FILE = Path("seen_jobs.json")
MAX_MESSAGES = 5

SEARCH_TEXT = "техническая поддержка"

KEYWORDS = [
    "поддерж",
    "support",
    "helpdesk",
    "help desk",
    "service desk",
]

EXCLUDED = [
    "руководитель",
    "директор",
    "начальник",
    "продаж",
    "телемаркет",
    "колл-центр",
    "call center",
]


# ========== HTTP REQUESTS ==========

def request_json(url, data=None, headers=None):
    request = Request(
        url,
        data=data,
        headers=headers or {},
    )

    with urlopen(request, timeout=30) as response:
        return json.load(response)


# ========== TELEGRAM ==========

def send_message(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    payload = urlencode({
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    request_json(url, data=payload)
    print("Telegram: message sent")


# ========== HISTORY ==========

def load_seen():
    if not STATE_FILE.exists():
        return set()

    try:
        content = STATE_FILE.read_text(encoding="utf-8")
        return set(json.loads(content))
    except (ValueError, OSError) as error:
        print("History error:", error)
        return set()


def save_seen(seen):
    STATE_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False),
        encoding="utf-8",
    )


# ========== HH SEARCH ==========

def search_jobs():
    params = {
        "text": SEARCH_TEXT,
        "work_format": "REMOTE",
        "order_by": "publication_time",
        "period": 1,
        "per_page": 50,
        "page": 0,
    }

    url = "https://api.hh.ru/vacancies?" + urlencode(params)

    headers = {
        "User-Agent": "JobHunterBot/1.0 (alex3456763@gmail.com)",
        "Accept": "application/json",
    }

    if HH_TOKEN:
        headers["Authorization"] = f"Bearer {HH_TOKEN}"

    print("Searching HH.ru...")
    result = request_json(url, headers=headers)

    print("Total results:", result.get("found", 0))
    return result.get("items", [])


# ========== FILTERS ==========

def suitable(job):
    title = job.get("name", "").lower()

    if not any(word in title for word in KEYWORDS):
        return False

    if any(word in title for word in EXCLUDED):
        return False

    return True


# ========== SALARY ==========

def format_salary(job):
    salary = job.get("salary_range") or job.get("salary")

    if not salary:
        return "Не указана"

    low = salary.get("from")
    high = salary.get("to")
    currency = salary.get("currency", "")

    if low is not None and high is not None:
        amount = f"{low:,}–{high:,}"
    elif low is not None:
        amount = f"от {low:,}"
    elif high is not None:
        amount = f"до {high:,}"
    else:
        return "Не указана"

    return f"{amount} {currency}"


# ========== MESSAGE FORMAT ==========

def format_job(job):
    title = html.escape(job.get("name", "Вакансия"))

    employer = job.get("employer") or {}
    company = html.escape(employer.get("name", "Не указана"))

    salary = html.escape(format_salary(job))

    link = html.escape(
        job.get("alternate_url") or "",
        quote=True,
    )

    message = (
        f"🔎 <b>{title}</b>\n\n"
        f"🏢 {company}\n"
        f"🏠 Удалённая работа\n"
        f"💰 {salary}\n\n"
        f'<a href="{link}">Открыть вакансию</a>'
    )

    return message


# ========== MAIN ==========

def main():
    print("Job Hunter started")

    seen = load_seen()
    print("Previously seen jobs:", len(seen))

    try:
        jobs = search_jobs()

    except HTTPError as error:
        print("HH HTTP status:", error.code)

        body = error.read().decode(
            "utf-8", errors="replace"
        )

        print("HH response:", body[:1500])
        print("HH request failed")
        raise

    except URLError as error:
        print("Network error:", error.reason)
        raise

    print("Received jobs:", len(jobs))

    new_jobs = [
        job for job in jobs
        if suitable(job)
        and str(job["id"]) not in seen
    ]

    print("New suitable jobs:", len(new_jobs))

    sent = 0

    for job in new_jobs[:MAX_MESSAGES]:
        send_message(format_job(job))

        seen.add(str(job["id"]))
        save_seen(seen)

        sent += 1

    print("Messages sent:", sent)

    if sent == 0:
        print("No new suitable jobs")

    print("Job Hunter finished")


if __name__ == "__main__":
    main()

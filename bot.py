"""Personal Telegram vacancy alerts from Remotive's public API.

The scoring is heuristic, not a guarantee that a job is suitable.
"""
import html
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SEEN_FILE = Path("seen_jobs.json")
MAX_MESSAGES = 5
MIN_MONTHLY_USD = 700

ROLE_GROUPS = {
    "Technical / Customer Support": [
        "technical support", "tech support", "application support", "product support",
        "customer support", "customer service", "customer care", "customer success",
        "chat support", "email support", "billing support", "help desk", "helpdesk",
        "service desk", "support specialist", "support engineer", "support agent",
        "support representative", "client support", "it support", "user support",
        "customer experience", "implementation support",
    ],
    "QA / Testing": [
        "manual qa", "manual tester", "qa tester", "qa analyst", "qa engineer",
        "quality assurance", "software tester", "web tester", "game tester",
        "software testing", "quality analyst", "test analyst",
    ],
    "AI / Data": [
        "ai trainer", "ai rater", "ai evaluator", "ai data", "data annotator",
        "data annotation", "data labeling", "data labelling", "data quality",
        "search quality", "content evaluator", "content moderator", "trust and safety",
        "llm evaluator", "ai content", "data entry",
    ],
    "E-commerce / Operations": [
        "e-commerce", "ecommerce", "marketplace specialist", "marketplace support",
        "catalog specialist", "catalogue specialist", "content specialist",
        "content operations", "operations assistant", "order support",
        "order management", "product listing", "listing specialist",
        "player support", "game support", "community support",
    ],
}

SENIOR_TITLES = [
    "senior ", "sr. ", "lead ", "principal ", "staff ", "director", "head of",
    "vice president", "manager of", "tier iii", "tier 3", "level 3", "l3 support",
]
SALES_TITLES = ["sales executive", "sales development", "account executive", "telemarketing"]
PHONE_PHRASES = [
    "phone calls", "phone support", "inbound calls", "outbound calls",
    "answer calls", "take calls", "call center", "call centre", "cold calling",
    "voice support", "telephone support", "calls with customers",
]
WRITTEN_PHRASES = ["email support", "chat support", "live chat", "ticketing", "tickets", "written communication"]
LOCATION_GOOD = ["worldwide", "anywhere", "global", "vietnam", "asia", "apac", "south east asia", "southeast asia"]
LOCATION_BAD = [
    "us only", "usa only", "united states only", "canada only", "uk only",
    "united kingdom only", "europe only", "eu only", "north america only",
]


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(markup):
    parser = PlainText()
    parser.feed(markup or "")
    return html.unescape(" ".join(parser.parts))


def fetch_json(url, payload=None):
    headers = {"User-Agent": "PersonalJobHunter/2.0", "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = Request(url, data=payload, headers=headers)
    with urlopen(req, timeout=35) as response:
        return json.load(response)


def notify(message):
    payload = urlencode({
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    fetch_json(f"https://api.telegram.org/bot{TOKEN}/sendMessage", payload)


def load_seen():
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        print("History could not be read:", error, flush=True)
        return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")


def exchange_rates():
    try:
        result = fetch_json("https://open.er-api.com/v6/latest/USD")
        if result.get("result") != "success":
            raise ValueError("Unexpected exchange-rate response")
        return result.get("rates", {})
    except (HTTPError, URLError, ValueError) as error:
        print("Currency conversion unavailable:", error, flush=True)
        return {"USD": 1.0}


def salary_monthly_usd(raw, rates, job_type=""):
    """Converts *unambiguously labelled* salary to estimated USD/month.

    Returns None when currency or pay period is missing, rather than guessing.
    """
    text = (raw or "").strip()
    lower = text.lower()
    if not text:
        return None

    currencies = [
        ("USD", r"\$|\busd\b|\bus\s*dollars?\b"),
        ("EUR", r"€|\beur\b"),
        ("GBP", r"£|\bgbp\b"),
        ("RUB", r"₽|\brub\b|\brur\b|\bруб"),
        ("CAD", r"\bcad\b|\bcanadian dollars?\b"),
        ("AUD", r"\baud\b|\baustralian dollars?\b"),
        ("VND", r"₫|\bvnd\b"),
    ]
    found = [code for code, pattern in currencies if re.search(pattern, lower, flags=re.I)]
    if len(found) != 1:
        return None
    currency = found[0]
    rate = rates.get(currency)
    if not rate or rate <= 0:
        return None

    annual = bool(re.search(r"\b(per\s+year|yearly|annually|annual|/\s*(yr|year)|p\.a\.)\b", lower))
    monthly = bool(re.search(r"\b(per\s+month|monthly|/\s*(mo|month))\b|/мес|в месяц", lower))
    hourly = bool(re.search(r"\b(per\s+hour|hourly|/\s*(hr|hour))\b|/час", lower))
    if sum([annual, monthly, hourly]) != 1:
        return None
    if hourly and job_type != "full_time":
        return None  # Unknown weekly hours: don't assume 160 h/month

    number_pattern = r"(?<![A-Za-z0-9])\d{1,3}(?:[ ,.]\d{3})+(?:\.\d+)?\s*[kK]?|(?<![A-Za-z0-9])\d+(?:[.,]\d+)?\s*[kK]?"
    numbers = []
    for item in re.findall(number_pattern, lower):
        token = item.replace(" ", "")
        multiplier = 1000 if token.endswith("k") else 1
        token = token.rstrip("k")
        if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", token):
            token = token.replace(",", "").replace(".", "")
        elif token.count(",") == 1 and token.count(".") == 0:
            token = token.replace(",", ".")
        try:
            numbers.append(float(token) * multiplier)
        except ValueError:
            pass
    if not numbers:
        return None

    # For ranges, use their lower end, not the optimistic upper end.
    amount = min(numbers[:2])
    if annual:
        amount /= 12
    elif hourly:
        amount *= 160  # Estimated 40 h/week x 4 weeks
    return amount / rate


def classify_role(title):
    name = title.lower()
    for group, terms in ROLE_GROUPS.items():
        if any(term in name for term in terms):
            return group
    return None


def evaluate(job, rates):
    title = job.get("title") or ""
    role = classify_role(title)
    if role is None:
        return None

    description = plain_text(job.get("description") or "").lower()
    title_lower = title.lower()
    location = (job.get("candidate_required_location") or "").lower()
    score = 65
    notes = []

    if any(term in title_lower for term in SENIOR_TITLES):
        score -= 35
        notes.append("⚠️ Повышенный уровень / руководящая роль")
    if any(term in title_lower for term in SALES_TITLES):
        score -= 30
        notes.append("⚠️ Возможны продажи")
    if any(term in description for term in PHONE_PHRASES):
        score -= 25
        notes.append("⚠️ Упоминаются телефонные звонки")
    if any(term in description for term in WRITTEN_PHRASES):
        score += 12
        notes.append("✅ Есть письменная поддержка / тикеты")

    if any(term in location for term in LOCATION_GOOD):
        score += 12
        notes.append("✅ География выглядит перспективно")
    elif any(term in location for term in LOCATION_BAD):
        score -= 35
        notes.append("⚠️ Регион, вероятно, исключает Вьетнам")
    else:
        notes.append("❔ Проверь разрешённую страну найма")

    if re.search(r"\b(c1|c2|native english|native-level english)\b", description):
        score -= 20
        notes.append("⚠️ Требуется очень сильный английский")
    elif re.search(r"\bb2\b", description):
        notes.append("ℹ️ Английский B2 — можно попробовать")

    salary = salary_monthly_usd(job.get("salary"), rates, job.get("job_type", ""))
    if salary is None:
        notes.append("❔ Зарплату нельзя надёжно пересчитать")
    elif salary < MIN_MONTHLY_USD:
        score -= 15
        notes.append(f"⚠️ Оценка ниже ${MIN_MONTHLY_USD}/мес.")
    else:
        score += 8
        notes.append("✅ Зарплата достигает ориентира")

    return max(0, min(100, score)), role, salary, notes


def format_message(job, result):
    score, role, monthly, notes = result
    esc = lambda s: html.escape(str(s), quote=True)
    salary_raw = job.get("salary") or "Не указана"
    estimate = f"≈ ${monthly:,.0f}/мес. (оценка)" if monthly is not None else "Не определён"
    url = esc(job.get("url") or "https://remotive.com/")
    comments = "\n".join(esc(x) for x in notes[:5])
    return (
        f"🔎 <b>{esc(job.get('title') or 'Вакансия')}</b>\n"
        f"🎯 <b>{score}/100</b> · {esc(role)}\n"
        f"🏢 {esc(job.get('company_name') or 'Компания не указана')}\n"
        f"🌏 {esc(job.get('candidate_required_location') or 'Регион не указан')}\n"
        f"💰 {esc(salary_raw)}\n"
        f"💵 {esc(estimate)}\n\n"
        f"{comments}\n\n"
        f"📌 Remotive · <a href=\"{url}\">Открыть вакансию</a>\n"
        "<i>Оценка предварительная; требования проверь в оригинале.</i>"
    )


def main():
    print("Job Hunter v2 started", flush=True)
    seen = load_seen()
    jobs = fetch_json("https://remotive.com/api/remote-jobs").get("jobs", [])
    print("Received jobs:", len(jobs), flush=True)
    rates = exchange_rates()

    candidates = []
    for job in jobs:
        key = "remotive:" + str(job.get("id"))
        if key in seen:
            continue
        result = evaluate(job, rates)
        if result and result[0] >= 40:
            candidates.append((result[0], job, result, key))

    # Prioritise good matches, then publication order returned by Remotive.
    candidates.sort(key=lambda item: item[0], reverse=True)
    print("New matches:", len(candidates), flush=True)

    for _, job, result, key in candidates[:MAX_MESSAGES]:
        notify(format_message(job, result))
        seen.add(key)
        save_seen(seen)
        print("Sent:", job.get("title"), flush=True)

    if not candidates:
        print("No new matches", flush=True)
    print("Job Hunter finished", flush=True)


if __name__ == "__main__":
    main()

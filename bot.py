
def main():
    seen = load_seen()

    try:
        jobs = search_jobs()

    except (HTTPError, URLError) as error:
        if isinstance(error, HTTPError):
            print("HTTP status:", error.code)
            print(
                "HH response:",
                error.read().decode(
                    "utf-8", errors="replace"
                )[:1500]
            )

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

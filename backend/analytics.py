import json
import os
import threading
from collections import Counter
from datetime import datetime, timedelta

# Лог запросов: одна строка JSON на одно событие (формат JSON Lines).
# Папка logs подключена в docker-compose как volume — лог не стирается при пересборке.
LOG_DIR = "logs"
LOG_PATH = os.path.join(LOG_DIR, "requests.jsonl")
LOW_SIMILARITY = 0.2  # ниже этого порога считаем, что модель "не уверена"

_lock = threading.Lock()  # FastAPI обрабатывает запросы параллельно — пишем в файл по очереди


def log_event(event_type: str, **data):
    """Записать событие в лог. Ошибка записи не должна ломать сам запрос пользователя"""
    event = {"time": datetime.now().isoformat(timespec="seconds"), "type": event_type, **data}
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with _lock, open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as e:
        print("Ошибка записи лога:", e)


def _read_events():
    if not os.path.exists(LOG_PATH):
        return []
    events = []
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # повреждённую строку пропускаем
    return events


def get_live_stats(total_books: int, days: int = 14):
    events = _read_events()

    # --- Активность по дням (последние N дней, включая дни без запросов) ---
    today = datetime.now().date()
    day_labels = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    per_day = Counter(e["time"][:10] for e in events)

    # --- Спрос: какие книги и жанры запрашивают ---
    book_requests = [e for e in events if e["type"] in ("recommend", "recommend_genre")]
    top_books = Counter(e["source_title"] for e in book_requests).most_common(5)
    top_genres = Counter(e["source_genre"] for e in book_requests).most_common(5)

    # Книги, которых нет в каталоге, но их ищут (вкладка "Новая книга" и чат-агент)
    missing = Counter(
        e["source_title"] for e in events
        if e["type"] == "new_book" and not e.get("in_catalog")
    ).most_common(5)

    # --- Качество модели: только подборки, где считается сходство ---
    similarities, genre_matches, recommended_ids = [], [], set()
    for e in events:
        recommended_ids.update(e.get("rec_ids", []))
        similarities.extend(e.get("similarities", []))
        genre_matches.extend(e.get("genre_matches", []))

    avg_similarity = sum(similarities) / len(similarities) if similarities else 0
    low_share = (sum(s < LOW_SIMILARITY for s in similarities) / len(similarities) * 100) if similarities else 0
    same_genre_share = (sum(genre_matches) / len(genre_matches) * 100) if genre_matches else 0

    # Гистограмма сходства: 5 интервалов 0–0.2, 0.2–0.4, ... 0.8–1.0
    bins = [0] * 5
    for s in similarities:
        bins[min(int(max(s, 0) * 5), 4)] += 1

    return {
        "total_events": len(events),
        "by_type": dict(Counter(e["type"] for e in events)),
        "per_day": {"labels": day_labels, "values": [per_day.get(d, 0) for d in day_labels]},
        "top_books": [{"title": t, "count": c} for t, c in top_books],
        "top_genres": [{"genre": g, "count": c} for g, c in top_genres],
        "missing_books": [{"title": t, "count": c} for t, c in missing],
        "quality": {
            "avg_similarity": round(avg_similarity, 3),
            "low_similarity_pct": round(low_share, 1),
            "same_genre_pct": round(same_genre_share, 1),
            "coverage_pct": round(len(recommended_ids) / total_books * 100, 1) if total_books else 0,
            "similarity_bins": bins,
        },
    }

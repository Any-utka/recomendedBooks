import os
import requests

# Публичный API Google Books — работает без ключа (с ограничением числа запросов).
# Наш датасет собран из этого же источника, поэтому жанры (categories) совпадают с каталогом.
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"


def search_google_books(query: str, max_results: int = 8):
    """Ищет книги в Google Books. Возвращает список книг в формате нашего каталога
    или None, если API недоступен"""
    params = {
        "q": query,
        "maxResults": max_results,
        "printType": "books",
    }
    # Ключ необязателен: если он есть в .env — используем, лимит запросов будет выше
    api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
    if api_key:
        params["key"] = api_key

    try:
        response = requests.get(GOOGLE_BOOKS_URL, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print("Ошибка Google Books API:", e)
        return None

    books = []
    for item in response.json().get("items", []):
        info = item.get("volumeInfo", {})
        thumbnail = info.get("imageLinks", {}).get("thumbnail", "")

        books.append({
            "google_id": item.get("id"),
            "title": info.get("title", "Без названия"),
            "author": ", ".join(info.get("authors", ["Unknown Author"])),
            "genre": (info.get("categories") or ["Unknown Genre"])[0],
            "pages": info.get("pageCount") or 0,
            "description": info.get("description", ""),
            "thumbnail": thumbnail.replace("http://", "https://"),
            "published_date": info.get("publishedDate", ""),
        })

    return books

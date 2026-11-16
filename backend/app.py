from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import model
import agent
import google_books
import analytics
import emailer

app = FastAPI()

# Разрешаем запросы с фронтенда (иначе браузер заблокирует их из-за CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    messages: list


class EmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    book_id: Optional[int] = None


class NewBook(BaseModel):
    title: str
    description: str = ""
    genre: str = ""
    pages: float = 0


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/books")
def list_books():
    return model.get_all_books()


@app.get("/recommend/{book_id}")
def recommend(book_id: int, n: int = 5):
    result = model.get_recommendations(book_id, n)
    if result is None:
        raise HTTPException(status_code=404, detail="Книга не найдена")
    return result


@app.get("/recommend-ai/{book_id}")
def recommend_with_ai(book_id: int, n: int = 5):
    if book_id < 0 or book_id >= len(model.df):
        raise HTTPException(status_code=404, detail="Книга не найдена")
    result = agent.run_agent(book_id, n)
    if result is None:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    source = model.df.iloc[book_id]
    recs = result["recommendations"]
    analytics.log_event(
        "recommend",
        source_title=source["title"],
        source_genre=source["genre"],
        rec_ids=[r["id"] for r in recs],
        similarities=[r["similarity"] for r in recs],
        genre_matches=[r["explanation"]["genre_match"] for r in recs],
    )
    return result


@app.get("/stats")
def stats():
    return model.get_dashboard_stats()


@app.get("/genres")
def genres():
    return model.get_all_genres()


@app.get("/books-by-genre/{genre}")
def books_by_genre(genre: str):
    return model.get_books_by_genre(genre)


@app.get("/recommend-genre-rating/{book_id}")
def recommend_genre_rating(book_id: int):
    result = model.get_similar_by_genre_rating(book_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    source = model.df.iloc[book_id]
    analytics.log_event(
        "recommend_genre",
        source_title=source["title"],
        source_genre=source["genre"],
        rec_ids=[r["id"] for r in result],
    )
    return {"recommendations": result}


@app.post("/chat")
def chat(req: ChatRequest):
    analytics.log_event("chat")
    reply = agent.run_chat(req.messages)
    return {"reply": reply}


# ---------- Новая книга: поиск через Google Books API ----------
@app.get("/google-search")
def google_search(q: str):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Пустой запрос")
    result = google_books.search_google_books(q)
    if result is None:
        raise HTTPException(status_code=503, detail="Google Books API недоступен")
    analytics.log_event("google_search", query=q, found=len(result))
    return result


# ---------- Новая книга: предсказание на новых данных ----------
@app.post("/recommend-new")
def recommend_new(book: NewBook, n: int = 5):
    if not book.description.strip() and not book.genre.strip():
        raise HTTPException(status_code=400, detail="Нужно указать хотя бы описание или жанр")
    result = model.recommend_for_new_book(book.title, book.description, book.genre, book.pages, n)

    recs = result["recommendations"]
    analytics.log_event(
        "new_book",
        source_title=book.title,
        source_genre=book.genre or "Unknown Genre",
        in_catalog=result["in_catalog"],
        rec_ids=[r["id"] for r in recs],
        similarities=[r["similarity"] for r in recs],
        genre_matches=[r["explanation"]["genre_match"] for r in recs],
    )
    return result


# ---------- Живая аналитика по логу запросов ----------
@app.get("/live-stats")
def live_stats():
    return analytics.get_live_stats(total_books=len(model.df))


# ---------- RPA: email с подборкой (human-in-the-loop) ----------
# Шаг 1: агент готовит черновик, человек видит его и может отредактировать
@app.get("/email/draft/{book_id}")
def email_draft(book_id: int):
    if book_id < 0 or book_id >= len(model.df):
        raise HTTPException(status_code=404, detail="Книга не найдена")
    return agent.draft_recommendation_email(book_id)


# Шаг 2: письмо уходит только после того, как человек нажал "Отправить"
@app.post("/email/send")
def email_send(req: EmailRequest):
    if not emailer.is_valid_email(req.to):
        raise HTTPException(status_code=400, detail="Некорректный email")
    if not req.subject.strip() or not req.body.strip():
        raise HTTPException(status_code=400, detail="Пустая тема или текст письма")

    ok, error = emailer.send_email(req.to, req.subject, req.body)
    if not ok:
        raise HTTPException(status_code=502, detail=error)

    analytics.log_event("email_sent", book_id=req.book_id)
    return {"status": "sent"}

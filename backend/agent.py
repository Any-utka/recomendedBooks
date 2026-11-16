import os
from dotenv import load_dotenv
from groq import Groq
import model
import google_books
import analytics

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# ---------- Общая функция запроса к LLM ----------
def ask_llm(prompt: str):
    """Запрос к LLM. Если Groq недоступен — возвращаем None, а не роняем весь сервер"""
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.7,
            reasoning_effort="low",
        )
        return response.choices[0].message.content
    except Exception as e:
        print("Ошибка LLM:", e)
        return None


# ---------- Tool 1: получить рекомендации от ML-модели ----------
def tool_get_recommendations(book_id: int, n: int = 5):
    return model.get_recommendations(book_id, n)


# ---------- Tool 2: сгенерировать понятное объяснение через LLM ----------
def tool_generate_explanation(source_title: str, recommended_book: dict):
    exp = recommended_book['explanation']

    prompt = f"""Пользователь выбрал книгу "{source_title}".
Рекомендована книга "{recommended_book['title']}" (автор {recommended_book['author']}, жанр {recommended_book['genre']}).

Факты для объяснения:
- Совпадение жанра: {"да" if exp['genre_match'] else "нет"}
- Разница в страницах: {exp['pages_diff']}
- Текстовое сходство описаний: {exp['text_similarity']}
- Итоговое сходство: {recommended_book['similarity']}

Напиши короткое (1-2 предложения), дружелюбное объяснение для пользователя, почему эта книга может ему понравиться. Пиши на русском языке, без общих фраз, опирайся на факты выше."""

    return ask_llm(prompt)


# ---------- Сам агент: использует все tools и возвращает итог ----------
def run_agent(book_id: int, n: int = 5):
    source_book = model.df.iloc[book_id]

    # Tool 1
    recommendations = tool_get_recommendations(book_id, n)
    if recommendations is None:
        return None

    # Tool 2 — объяснение для каждой ML-рекомендации
    for rec in recommendations:
        rec['ai_explanation'] = tool_generate_explanation(source_book['title'], rec)

    # Tool 3 — агент сам добавляет трендовую книгу от себя
    already_shown_ids = [book_id] + [r['id'] for r in recommendations]
    trending = tool_get_trending(source_book['genre'], already_shown_ids)

    trending_pick = None
    if trending is not None:
        trending['ai_explanation'] = tool_generate_trending_explanation(source_book['title'], trending)
        trending_pick = trending

    return {
        'recommendations': recommendations,
        'trending_pick': trending_pick,
    }


# ---------- RPA: черновик письма с подборкой (отправляет только человек после проверки) ----------
def draft_recommendation_email(book_id: int, n: int = 5):
    """Агент готовит письмо: берёт рекомендации ML-модели, LLM пишет вступление
    и советует, с какой книги начать. Письмо НЕ отправляется — его сначала проверяет человек"""
    recommendations = model.get_recommendations(book_id, n)
    if recommendations is None:
        return None
    source = model.df.iloc[book_id]

    book_lines = "\n".join(
        f"{i}. «{r['title']}» — {r['author']} (жанр: {r['genre']}, сходство {r['similarity'] * 100:.0f}%)"
        for i, r in enumerate(recommendations, 1)
    )

    prompt = f"""Ты пишешь письмо читателю от книжного магазина.
Читатель интересовался книгой "{source['title']}" (автор {source['author']}, жанр {source['genre']}).
Наша рекомендательная система подобрала похожие книги:
{book_lines}

Напиши на русском 2-3 предложения вступления: вежливое приветствие и совет, с какой книги из списка
лучше начать и почему (опирайся на жанр и сходство). Без темы письма, без подписи, без повторения списка."""

    intro = ask_llm(prompt) or (
        f"Здравствуйте! Мы подобрали для вас книги, похожие на «{source['title']}». "
        "Надеемся, что-то из этого списка вам понравится."
    )

    subject = f"Подборка книг, похожих на «{source['title']}»"
    body = (
        f"{intro.strip()}\n\n"
        f"Похожие книги:\n{book_lines}\n\n"
        "Подборка составлена рекомендательной системой Book Recommender "
        "по описанию, жанру и объёму книг.\n"
    )
    return {"subject": subject, "body": body}


# ---------- Tool 3: найти трендовую книгу в жанре ----------
def tool_get_trending(genre: str, exclude_ids: list):
    return model.get_trending_in_genre(genre, exclude_ids)


def tool_generate_trending_explanation(source_title: str, trending_book: dict):
    genre_context = (
        f"в этом же жанре ({trending_book['genre']})" if not trending_book.get('is_fallback')
        else "среди книг в целом (в жанре исходной книги других вариантов не нашлось)"
    )

    prompt = f"""Пользователь выбрал книгу "{source_title}".

Помимо похожих книг, наш анализ данных показал, что {genre_context} есть особенно популярная и высоко оценённая книга:
"{trending_book['title']}" (автор {trending_book['author']}), рейтинг {trending_book['average_rating']}, количество оценок {trending_book['ratings_count']}.

Напиши 1-2 предложения на русском, почему стоит обратить внимание именно на эту книгу — сделай акцент на её популярности/признании среди читателей, а не только на сходстве."""

    return ask_llm(prompt)


import json

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_book",
            "description": "Найти книгу в каталоге по названию или части названия. Возвращает список книг с их id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Название книги или часть названия"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recommendations",
            "description": "Получить рекомендации книг, похожих на конкретную книгу (по id), на основе описания, жанра и объёма.",
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {"type": "integer", "description": "id книги, полученный через search_book"},
                    "n": {"type": "integer", "description": "сколько рекомендаций вернуть"}
                },
                "required": ["book_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trending_in_genre",
            "description": "Найти самую популярную и высокооценённую книгу в заданном жанре (точное название жанра из каталога).",
            "parameters": {
                "type": "object",
                "properties": {
                    "genre": {"type": "string", "description": "Точное название жанра"}
                },
                "required": ["genre"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_books",
            "description": "Сравнить две книги по жанру, объёму и смысловому сходству.",
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id_1": {"type": "integer"},
                    "book_id_2": {"type": "integer"}
                },
                "required": ["book_id_1", "book_id_2"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_books_by_genre",
            "description": "Найти популярные книги по ключевому слову жанра на английском (например 'fantasy', 'science fiction', 'romance'). Каталог жанров на английском языке. Используй этот инструмент, а не get_trending_in_genre, если не уверена в точном названии жанра.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Ключевое слово жанра на английском"},
                    "limit": {"type": "integer", "description": "сколько книг вернуть"}
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_google_books",
            "description": "Найти книгу во внешнем каталоге Google Books (через API). Используй, если книги нет в нашем каталоге или пользователь спрашивает о новой книге. Возвращает название, автора, жанр, страницы и краткое описание.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Название книги и/или автор"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_for_external_book",
            "description": "Подобрать похожие книги из НАШЕГО каталога для книги, которой в каталоге нет. Сам находит книгу в Google Books по запросу и применяет к ней ML-модель (TF-IDF + жанр + страницы). Используй, если search_book не нашёл книгу.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Название книги и/или автор"},
                    "n": {"type": "integer", "description": "сколько рекомендаций вернуть"}
                },
                "required": ["query"]
            }
        }
    },
]


# ---------- Новые tools: внешний API Google Books + ML-модель на новых данных ----------

def tool_search_google_books(query: str):
    books = google_books.search_google_books(query, max_results=5)
    if books is None:
        return {"error": "Google Books API сейчас недоступен"}
    # Описание обрезаем, чтобы не тратить лишние токены LLM
    return [
        {
            "title": b["title"],
            "author": b["author"],
            "genre": b["genre"],
            "pages": b["pages"],
            "description": b["description"][:300],
        }
        for b in books
    ]


def tool_recommend_for_external_book(query: str, n: int = 5):
    books = google_books.search_google_books(query, max_results=1)
    if books is None:
        return {"error": "Google Books API сейчас недоступен"}
    if not books:
        return {"error": "Книга не найдена в Google Books"}

    book = books[0]
    result = model.recommend_for_new_book(book["title"], book["description"], book["genre"], book["pages"], n)

    analytics.log_event(
        "new_book",
        source_title=book["title"],
        source_genre=book["genre"],
        in_catalog=result["in_catalog"],
        via="chat",
        rec_ids=[r["id"] for r in result["recommendations"]],
        similarities=[r["similarity"] for r in result["recommendations"]],
        genre_matches=[r["explanation"]["genre_match"] for r in result["recommendations"]],
    )

    # Агенту отдаём только то, что нужно для ответа (без ссылок на обложки)
    return {
        "source_book": {
            "title": book["title"],
            "author": book["author"],
            "genre": book["genre"],
            "pages": book["pages"],
        },
        "genre_known": result["genre_known"],
        "has_description": result["has_description"],
        "recommendations": [
            {
                "id": r["id"],
                "title": r["title"],
                "author": r["author"],
                "genre": r["genre"],
                "similarity": r["similarity"],
                "text_similarity": r["explanation"]["text_similarity"],
                "genre_pages_similarity": r["explanation"]["genre_pages_similarity"],
            }
            for r in result["recommendations"]
        ],
    }


def execute_tool(name, args):
    if name == "search_book":
        return model.search_books_by_title(args.get("query", ""))
    if name == "get_recommendations":
        return model.get_recommendations(args.get("book_id"), args.get("n", 5))
    if name == "get_trending_in_genre":
        return model.get_trending_in_genre(args.get("genre"), exclude_ids=[])
    if name == "compare_books":
        return model.explain_recommendation(args.get("book_id_1"), args.get("book_id_2"))
    if name == "find_books_by_genre":
        return model.find_books_by_genre_keyword(args.get("keyword", ""), args.get("limit", 5))
    if name == "search_google_books":
        return tool_search_google_books(args.get("query", ""))
    if name == "recommend_for_external_book":
        return tool_recommend_for_external_book(args.get("query", ""), args.get("n", 5))
    return {"error": "unknown tool"}


def run_chat(messages):
    system_message = {
        "role": "system",
        "content": (
            "Ты дружелюбный книжный ассистент на сайте рекомендаций книг. "
            "У тебя есть доступ к реальному каталогу книг через инструменты — используй их, "
            "чтобы находить книги и строить рекомендации, не выдумывай названия книг от себя. "
            "ВАЖНО: все жанры и названия книг в каталоге на английском языке. "
            "Если пользователь пишет на русском, переведи ключевые слова (жанр, тему) на английский "
            "перед вызовом инструментов find_books_by_genre или get_trending_in_genre. "
            "Предпочитай find_books_by_genre, если не знаешь точного названия жанра в каталоге. "
            "Если книги нет в нашем каталоге (search_book ничего не нашёл), найди её через "
            "search_google_books, а похожие книги из каталога подбери через recommend_for_external_book. "
            "Честно говори пользователю, что исходной книги нет в каталоге, но вот похожие из него. "
            "Проанализируй результат инструментов: объясни, почему книги похожи (общий жанр, сходство описаний), "
            "и если сходство низкое (меньше 0.2) — предупреди об этом. "
            "В конце ответа предложи пользователю одно конкретное следующее действие "
            "(например: с какой книги начать, сравнить две книги или посмотреть популярные в жанре). "
            "Отвечай пользователю всегда на русском языке, кратко и по делу."
        )
    }

    full_messages = [system_message] + messages

    for _ in range(5):
        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=full_messages,
                tools=tools,
                max_tokens=800,
                temperature=0.7,
                reasoning_effort="low",
            )
        except Exception as e:
            print("Ошибка LLM в чате:", e)
            return "Извини, ассистент сейчас недоступен. Попробуй чуть позже."

        msg = response.choices[0].message

        if msg.tool_calls:
            full_messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })

            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                    result = execute_tool(tc.function.name, args)
                except Exception as e:
                    result = {"error": f"Инструмент не сработал: {e}"}
                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            continue

        return msg.content

    return "Извини, не получилось обработать запрос."

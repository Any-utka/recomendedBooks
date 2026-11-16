import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics.pairwise import cosine_similarity

# ---------- Загрузка и очистка данных ----------
df = pd.read_excel("data/Books.xlsx")

# Поля, по которым запись считается "той же самой книгой"
content_cols = ['title', 'author', 'pages', 'genre', 'published_date', 'publisher', 'description']

print("Полных дубликатов строк:", df.duplicated().sum())
print("Повторов title:", df['title'].duplicated().sum())
print("Совпадений по всем содержательным полям:", df.duplicated(subset=content_cols).sum())

# Из каждой группы оставляем запись с большим числом оценок,
# затем возвращаем исходный порядок и сбрасываем индекс
df = (df.sort_values('ratings_count', ascending=False)
        .drop_duplicates(subset=content_cols, keep='first')
        .sort_index()
        .reset_index(drop=True))

print("\nКниг после удаления дубликатов:", len(df))


df['pages'] = df['pages'].fillna(df['pages'].median())
df['has_description'] = df['description'] != 'No description available'

# ---------- Модель A: TF-IDF по описанию ----------
df['text_for_tfidf'] = df['description'].apply(
    lambda d: d if d != 'No description available' else ''
)

tfidf = TfidfVectorizer(stop_words='english', max_features=5000)
tfidf_matrix = tfidf.fit_transform(df['text_for_tfidf'])
cosine_sim_text = cosine_similarity(tfidf_matrix, tfidf_matrix)

# ---------- Модель B: жанр + страницы (с ограничением выбросов) ----------
cap = df['pages'].quantile(0.99)
df['pages_capped'] = df['pages'].clip(upper=cap)

genre_dummies = pd.get_dummies(df['genre'])
scaler = MinMaxScaler()
pages_scaled = scaler.fit_transform(df[['pages_capped']])

features_B = np.hstack([genre_dummies.values, pages_scaled])
cosine_sim_genre_pages = cosine_similarity(features_B, features_B)

# ---------- Финальная гибридная модель ----------
FINAL_ALPHA = 0.7
FINAL_BETA = 0.3
cosine_sim_final = FINAL_ALPHA * cosine_sim_text + FINAL_BETA * cosine_sim_genre_pages


# ---------- Функции для использования в API ----------

def get_all_books():
    """Список всех книг для отображения на фронтенде (выбор книги пользователем)"""
    return df[['title', 'author', 'genre', 'thumbnail']].reset_index().rename(columns={'index': 'id'}).to_dict(orient='records')


def explain_recommendation(source_idx, rec_idx):
    source = df.iloc[source_idx]
    rec = df.iloc[rec_idx]

    same_genre = source['genre'] == rec['genre']
    pages_diff = abs(source['pages'] - rec['pages'])
    text_sim = cosine_sim_text[source_idx][rec_idx]
    genre_pages_sim = cosine_sim_genre_pages[source_idx][rec_idx]
    total_sim = cosine_sim_final[source_idx][rec_idx]

    return {
        'genre_match': bool(same_genre),
        'genre': rec['genre'],
        'pages_diff': round(float(pages_diff), 1),
        'text_similarity': round(float(text_sim), 3),
        'genre_pages_similarity': round(float(genre_pages_sim), 3),
        'total_similarity': round(float(total_sim), 3),
    }


def get_recommendations(book_id: int, n: int = 5):
    """Главная функция: по id книги возвращает топ-N рекомендаций с объяснением"""
    if book_id < 0 or book_id >= len(df):
        return None

    sim_scores = list(enumerate(cosine_sim_final[book_id]))
    sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
    sim_scores = sim_scores[1:n + 1]  # пропускаем саму книгу

    results = []
    for idx, score in sim_scores:
        book = df.iloc[idx]
        results.append({
            'id': int(idx),
            'title': book['title'],
            'author': book['author'],
            'genre': book['genre'],
            'pages': float(book['pages']),
            'thumbnail': book['thumbnail'],
            'similarity': round(float(score), 3),
            'explanation': explain_recommendation(book_id, idx),
        })

    return results
def get_trending_in_genre(genre: str, exclude_ids: list):
    """Находит самую популярную и качественную книгу в жанре (исключая записи без автора — неполные/мусорные данные)"""
    candidates = df[
        (df['genre'] == genre) &
        (~df.index.isin(exclude_ids)) &
        (df['author'] != 'Unknown Author')
    ].copy()
    used_fallback = False

    if candidates.empty:
        candidates = df[
            (~df.index.isin(exclude_ids)) &
            (df['author'] != 'Unknown Author')
        ].copy()
        used_fallback = True

    if candidates.empty:
        return None

    candidates['trend_score'] = candidates['ratings_count'] * candidates['average_rating']
    best = candidates.loc[candidates['trend_score'].idxmax()]

    return {
        'id': int(best.name),
        'title': best['title'],
        'author': best['author'],
        'genre': best['genre'],
        'pages': float(best['pages']),
        'thumbnail': best['thumbnail'],
        'ratings_count': int(best['ratings_count']),
        'average_rating': float(best['average_rating']),
        'is_fallback': used_fallback,
    }

# ---------- Модель C: похожесть по жанру + рейтингу ----------

def get_all_genres(min_books: int = 5):
    """Жанры с достаточным числом книг для сравнения (исключает 'длинный хвост' жанров-одиночек)"""
    counts = df['genre'].value_counts()
    valid = counts[counts >= min_books].sort_index()
    return [{'genre': g, 'count': int(c)} for g, c in valid.items()]


def get_books_by_genre(genre: str):
    """Книги конкретного жанра — показываются после того, как пользователь выбрал жанр"""
    subset = df[df['genre'] == genre]
    return subset[['title', 'author', 'genre', 'thumbnail']].reset_index().rename(columns={'index': 'id'}).to_dict(orient='records')


def get_similar_by_genre_rating(book_id: int, n: int = 5):
    """Топ-N книг того же жанра, ближайших по рейтингу (при равенстве — более надёжные, с большим числом оценок)"""
    if book_id < 0 or book_id >= len(df):
        return None

    source = df.iloc[book_id]
    same_genre = df[(df['genre'] == source['genre']) & (df.index != book_id)].copy()

    same_genre['rating_diff'] = (same_genre['average_rating'] - source['average_rating']).abs()
    same_genre = same_genre.sort_values(
        ['rating_diff', 'ratings_count'],
        ascending=[True, False]
    ).head(n)

    results = []
    for idx, book in same_genre.iterrows():
        results.append({
            'id': int(idx),
            'title': book['title'],
            'author': book['author'],
            'genre': book['genre'],
            'average_rating': round(float(book['average_rating']), 2),
            'ratings_count': int(book['ratings_count']),
            'thumbnail': book['thumbnail'],
            'rating_diff': round(float(book['rating_diff']), 2),
        })

    return results

def search_books_by_title(query: str, limit: int = 5):
    """Поиск книг по части названия — нужен иишке в чате, чтобы находить книгу по тому, что написал пользователь"""
    matches = df[df['title'].str.contains(query, case=False, na=False)].head(limit)
    return [
        {
            'id': int(idx),
            'title': book['title'],
            'author': book['author'],
            'genre': book['genre'],
        }
        for idx, book in matches.iterrows()
    ]

def find_books_by_genre_keyword(keyword: str, limit: int = 5):
    """Нечёткий поиск книг по ключевому слову в названии жанра (например 'fantasy' найдёт 'Fantasy fiction', 'Fantasy fiction, American' и т.д.)"""
    subset = df[df['genre'].str.contains(keyword, case=False, na=False)].copy()
    if subset.empty:
        return []

    subset['trend_score'] = subset['ratings_count'] * subset['average_rating']
    subset = subset.sort_values('trend_score', ascending=False).head(limit)

    return [
        {
            'id': int(idx),
            'title': book['title'],
            'author': book['author'],
            'genre': book['genre'],
            'average_rating': float(book['average_rating']),
            'ratings_count': int(book['ratings_count']),
        }
        for idx, book in subset.iterrows()
    ]

# ---------- Рекомендации для НОВОЙ книги (которой нет в каталоге) ----------

def recommend_for_new_book(title: str, description: str, genre: str, pages: float, n: int = 5):
    """Предсказание на новых данных: книгу не добавляем в датасет и модель не переобучаем —
    просто переводим её в те же признаки (TF-IDF + жанр + страницы) и сравниваем с каталогом"""

    # Модель A: transform (а не fit_transform!) — используем словарь, выученный на каталоге
    description = (description or "").strip()
    new_text_vec = tfidf.transform([description])
    text_sim = cosine_similarity(new_text_vec, tfidf_matrix)[0]

    # Модель B: one-hot жанра в тех же колонках, что и у каталога
    genre_vec = np.zeros(len(genre_dummies.columns))
    genre_known = genre in genre_dummies.columns
    if genre_known:
        genre_vec[genre_dummies.columns.get_loc(genre)] = 1

    # Страницы: пропуск -> медиана, выброс -> тот же cap, затем тот же scaler
    if not pages or pages <= 0:
        pages = float(df['pages'].median())
    pages_capped = min(float(pages), cap)
    pages_sc = scaler.transform(pd.DataFrame({'pages_capped': [pages_capped]}))[0]

    new_features_B = np.hstack([genre_vec, pages_sc]).reshape(1, -1)
    genre_pages_sim = cosine_similarity(new_features_B, features_B)[0]

    # Финальная гибридная модель — те же веса, что и для книг из каталога
    total_sim = FINAL_ALPHA * text_sim + FINAL_BETA * genre_pages_sim

    # Если такая книга уже есть в каталоге — не рекомендуем её саму себе
    same_title = (df['title'].str.lower().str.strip() == (title or "").lower().strip()).values
    total_sim = np.where(same_title, -1, total_sim)

    top_idx = np.argsort(total_sim)[::-1][:n]

    results = []
    for idx in top_idx:
        book = df.iloc[idx]
        results.append({
            'id': int(idx),
            'title': book['title'],
            'author': book['author'],
            'genre': book['genre'],
            'pages': float(book['pages']),
            'thumbnail': book['thumbnail'],
            'similarity': round(float(total_sim[idx]), 3),
            'explanation': {
                'genre_match': bool(genre_known and book['genre'] == genre),
                'genre': book['genre'],
                'pages_diff': round(abs(float(book['pages']) - float(pages)), 1),
                'text_similarity': round(float(text_sim[idx]), 3),
                'genre_pages_similarity': round(float(genre_pages_sim[idx]), 3),
                'total_similarity': round(float(total_sim[idx]), 3),
            },
        })

    return {
        'genre_known': bool(genre_known),
        'has_description': bool(description),
        'in_catalog': bool(same_title.any()),
        'recommendations': results,
    }


# ---------- Дашборд: ключевые показатели каталога (KPI) ----------

def get_dashboard_stats():
    """Считается по текущим данным при запуске — если обновить Books.xlsx, цифры обновятся сами"""
    known = df[df['author'] != 'Unknown Author'].copy()
    known['trend_score'] = known['ratings_count'] * known['average_rating']
    top_book = known.loc[known['trend_score'].idxmax()]

    # Жанры сравниваем только при достаточном числе книг (от 10), иначе среднее ненадёжно
    genre_stats = df[df['genre'] != 'Unknown Genre'].groupby('genre').agg(
        count=('title', 'count'),
        avg_rating=('average_rating', 'mean'),
        avg_popularity=('ratings_count', 'mean'),
    )
    genre_stats = genre_stats[genre_stats['count'] >= 10]

    return {
        'total_books': int(len(df)),
        'genres_count': int(df['genre'].nunique()),
        'with_description_pct': round(float(df['has_description'].mean() * 100), 1),
        'avg_rating': round(float(df['average_rating'].mean()), 2),
        'most_popular_genre': genre_stats['avg_popularity'].idxmax(),
        'best_rated_genre': genre_stats['avg_rating'].idxmax(),
        'top_book': {'title': top_book['title'], 'author': top_book['author']},
    }

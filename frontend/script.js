const API_URL = "http://127.0.0.1:8000";
let allBooks = [];
let selectedBookId = null;

// ===== TABS =====
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
  });
});

// ===== BOOK LIST (SIDEBAR) =====
async function loadBooks() {
  const res = await fetch(`${API_URL}/books`);
  allBooks = await res.json();
  renderBookList(allBooks);
}

function renderBookList(books) {
  const container = document.getElementById("bookList");
  container.innerHTML = "";

  books.forEach(book => {
    const row = document.createElement("div");
    row.className = "book-row" + (book.id === selectedBookId ? " selected" : "");
    row.innerHTML = `
      <img src="${book.thumbnail}" alt="">
      <div>
        <div class="book-row-title">${book.title}</div>
        <div class="book-row-author">${book.author}</div>
      </div>
    `;
    row.onclick = () => selectBook(book.id, book.title);
    container.appendChild(row);
  });
}

document.getElementById("searchInput").addEventListener("input", (e) => {
  const query = e.target.value.toLowerCase();
  const filtered = allBooks.filter(b => b.title.toLowerCase().includes(query));
  renderBookList(filtered);
});

// ===== SELECT A BOOK → LOAD RECOMMENDATIONS =====
async function selectBook(bookId, title) {
  selectedBookId = bookId;
  renderBookList(allBooks.filter(b =>
    b.title.toLowerCase().includes(document.getElementById("searchInput").value.toLowerCase())
  ));

  document.getElementById("emptyState").style.display = "none";
  document.getElementById("resultsArea").style.display = "block";
  document.getElementById("selectedBookTitle").textContent = `Похоже на «${title}»`;
  document.getElementById("recommendations").innerHTML = "Загрузка...";
  document.getElementById("trendingSection").innerHTML = "";

  try {
    const res = await fetch(`${API_URL}/recommend-ai/${bookId}`);
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    renderRecommendations(data.recommendations);
    renderTrending(data.trending_pick);
  } catch (e) {
    document.getElementById("recommendations").innerHTML =
      `<p style="color:#A33;">Не удалось загрузить рекомендации. Проверь, что сервер запущен.</p>`;
  }
}

function renderRecommendations(recs) {
  const container = document.getElementById("recommendations");
  container.innerHTML = "";

  recs.forEach(book => {
    const card = document.createElement("div");
    card.className = "book-card";
    card.innerHTML = `
      <span class="similarity-badge">${(book.similarity * 100).toFixed(0)}% совпадение</span>
      <img src="${book.thumbnail}" alt="">
      <h4>${book.title}</h4>
      <div class="author">${book.author}</div>
      <div class="explain">${book.ai_explanation || ""}</div>
    `;
    container.appendChild(card);
  });
}

function renderTrending(book) {
  const container = document.getElementById("trendingSection");
  if (!book) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = `
    <h3 class="section-label">Также популярно в этом жанре</h3>
    <div class="book-list">
      <div class="book-card">
        <span class="similarity-badge trending-badge">★ ${book.average_rating.toFixed(1)} · ${book.ratings_count.toLocaleString()} оценок</span>
        <img src="${book.thumbnail}" alt="">
        <h4>${book.title}</h4>
        <div class="author">${book.author}</div>
        <div class="explain">${book.ai_explanation || ""}</div>
      </div>
    </div>
  `;
}

// ===== DASHBOARD TAB =====
// Только графики, полезные пользователю и бизнесу. Технические (выбросы, нормализация,
// дубликаты, метод локтя, кластеры, важность признаков) остались в Jupyter-ноутбуке.
const charts = [
  {
    file: "genres.png",
    label: "Какие жанры есть в каталоге",
    desc: "Каталог сильно перекошен: всего три жанра (Fiction, Literary Criticism, Education) дают около четверти книг, а из 262 жанров большинство представлены 1–2 книгами. Около 12% книг без жанра (Unknown Genre). Вывод для магазина: в «длинном хвосте» жанров покупателю почти нечего предложить — это кандидаты на расширение ассортимента; карточки без жанра стоит дозаполнить.",
  },
  {
    file: "genre_popularity.png",
    label: "Популярность и рейтинг жанров",
    desc: "Каждый пузырь — жанр (размер = число книг). Self-Help — самый популярный по числу оценок, но с рейтингом ниже среднего. Education, History, Business & Economics — и популярны, и высоко оценены. Вывод: эти жанры — надёжный выбор для витрины и рекомендаций новым покупателям; популярность и качество не всегда совпадают.",
  },
  {
    file: "rating_distribution.png",
    label: "Как читатели оценивают книги",
    desc: "Рейтинг в каталоге — по шкале 0–10, среднее около 5.3, оценки распределены широко, без «накрутки» к максимуму. Вывод: рейтингу можно доверять как сигналу качества, но только вместе с числом оценок — поэтому трендовая книга на сайте выбирается по рейтингу × числу оценок.",
  },
  {
    file: "books_by_decade.png",
    label: "Книги по десятилетиям издания",
    desc: "Чем ближе к нашему времени, тем больше книг в каталоге. Вывод: каталог ориентирован на современные издания; классика представлена слабее — её можно усилить, если целевая аудитория — студенты и школьники.",
  },
  {
    file: "languages.png",
    label: "Языки книг",
    desc: "95.6% книг — на английском, остальные языки представлены единицами. Вывод: система сейчас рассчитана на англоязычную литературу; для рынка Молдовы следующий шаг — добавить книги на румынском и русском.",
  },
];

// ===== ЖИВАЯ АНАЛИТИКА (по логу запросов) =====
const liveCharts = {}; // храним графики, чтобы при обновлении удалять старые

function drawChart(canvasId, config) {
  if (liveCharts[canvasId]) liveCharts[canvasId].destroy();
  liveCharts[canvasId] = new Chart(document.getElementById(canvasId), config);
}

const ACCENT = "#8A3324";
const ACCENT_SOFT = "#D9A99C";

function barConfig(labels, values, horizontal = false) {
  return {
    type: "bar",
    data: { labels, datasets: [{ data: values, backgroundColor: ACCENT, borderRadius: 4 }] },
    options: {
      indexAxis: horizontal ? "y" : "x",
      plugins: { legend: { display: false } },
      scales: { [horizontal ? "x" : "y"]: { beginAtZero: true, ticks: { precision: 0 } } },
    },
  };
}

// Длинные названия книг обрезаем, чтобы подписи помещались на графике
const shorten = (text, max = 32) => text.length > max ? text.slice(0, max) + "…" : text;

async function loadLiveStats() {
  let s;
  try {
    const res = await fetch(`${API_URL}/live-stats`);
    if (!res.ok) throw new Error(res.status);
    s = await res.json();
  } catch (e) {
    document.getElementById("liveKpiRow").innerHTML = `<p style="color:#A33;">Не удалось загрузить живую аналитику.</p>`;
    return;
  }

  const hasData = s.total_events > 0;
  document.getElementById("liveEmpty").style.display = hasData ? "none" : "block";
  document.getElementById("liveContent").style.display = hasData ? "block" : "none";
  if (!hasData) return;

  const q = s.quality;
  const t = s.by_type;
  const kpis = [
    { value: s.total_events, label: "всего запросов" },
    { value: (t.recommend || 0) + (t.recommend_genre || 0) + (t.new_book || 0), label: "подборок книг" },
    { value: t.chat || 0, label: "сообщений агенту" },
    { value: t.email_sent || 0, label: "писем с подборкой отправлено" },
    { value: q.avg_similarity, label: "среднее сходство" },
    { value: `${q.low_similarity_pct}%`, label: "рекомендаций со слабым сходством (< 0.2)" },
    { value: `${q.same_genre_pct}%`, label: "рекомендаций того же жанра" },
    { value: `${q.coverage_pct}%`, label: "каталога хоть раз рекомендовано (coverage)" },
  ];
  document.getElementById("liveKpiRow").innerHTML = kpis.map(k => `
    <div class="kpi-tile">
      <div class="kpi-value">${k.value}</div>
      <div class="kpi-label">${k.label}</div>
    </div>
  `).join("");

  drawChart("chartPerDay", {
    type: "line",
    data: {
      labels: s.per_day.labels.map(d => d.slice(5)), // "2026-11-03" -> "11-03"
      datasets: [{ data: s.per_day.values, borderColor: ACCENT, backgroundColor: ACCENT_SOFT, fill: true, tension: 0.3 }],
    },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });

  drawChart("chartSimilarity", barConfig(
    ["0–0.2", "0.2–0.4", "0.4–0.6", "0.6–0.8", "0.8–1.0"], q.similarity_bins
  ));

  drawChart("chartTopBooks", barConfig(
    s.top_books.map(b => shorten(b.title)), s.top_books.map(b => b.count), true
  ));

  drawChart("chartTopGenres", barConfig(
    s.top_genres.map(g => g.genre), s.top_genres.map(g => g.count), true
  ));

  document.getElementById("missingBooks").innerHTML = s.missing_books.length
    ? `<ol class="missing-list">${s.missing_books.map(b => `<li>${b.title} <span>— ${b.count} раз(а)</span></li>`).join("")}</ol>`
    : `<p class="kpi-label">Пока таких запросов не было.</p>`;
}

document.getElementById("refreshLive").addEventListener("click", loadLiveStats);

// При каждом открытии вкладки "Дашборд" — свежие данные
document.querySelector('.tab-btn[data-tab="analytics"]').addEventListener("click", loadLiveStats);

async function loadDashboard() {
  // KPI считаются на сервере по актуальным данным
  const kpiRow = document.getElementById("kpiRow");
  try {
    const res = await fetch(`${API_URL}/stats`);
    if (!res.ok) throw new Error(res.status);
    const s = await res.json();

    const kpis = [
      { value: s.total_books.toLocaleString(), label: "книг в каталоге" },
      { value: s.genres_count, label: "жанров" },
      { value: `${s.with_description_pct}%`, label: "книг с описанием" },
      { value: s.avg_rating, label: "средний рейтинг (0–10)" },
      { value: s.most_popular_genre, label: "самый популярный жанр", small: true },
      { value: s.best_rated_genre, label: "самый высокооценённый жанр", small: true },
    ];

    kpiRow.innerHTML = kpis.map(k => `
      <div class="kpi-tile">
        <div class="kpi-value ${k.small ? "kpi-value-small" : ""}">${k.value}</div>
        <div class="kpi-label">${k.label}</div>
      </div>
    `).join("") + `
      <div class="kpi-tile kpi-wide">
        <div class="kpi-value kpi-value-small">«${s.top_book.title}» — ${s.top_book.author}</div>
        <div class="kpi-label">самая популярная книга (рейтинг × число оценок)</div>
      </div>
    `;
  } catch (e) {
    kpiRow.innerHTML = `<p style="color:#A33;">Не удалось загрузить показатели.</p>`;
  }

  // Графики — все сразу, сеткой
  document.getElementById("chartGrid").innerHTML = charts.map(c => `
    <div class="chart-card">
      <h3>${c.label}</h3>
      <img src="charts/${c.file}" alt="${c.label}">
      <p>${c.desc}</p>
    </div>
  `).join("");
}

// ===== GENRE TAB =====
let genreBooks = [];
let selectedGenreBookId = null;

async function loadGenres() {
  const res = await fetch(`${API_URL}/genres`);
  const genres = await res.json();

  const select = document.getElementById("genreSelect");
  genres.forEach(g => {
    const opt = document.createElement("option");
    opt.value = g.genre;
    opt.textContent = `${g.genre} (${g.count})`;
    select.appendChild(opt);

    // те же жанры — подсказки для поля "Жанр" во вкладке "Новая книга"
    const dlOpt = document.createElement("option");
    dlOpt.value = g.genre;
    document.getElementById("genreOptions").appendChild(dlOpt);
  });

  select.addEventListener("change", () => {
    if (select.value) loadBooksByGenre(select.value);
  });
}

async function loadBooksByGenre(genre) {
  const res = await fetch(`${API_URL}/books-by-genre/${encodeURIComponent(genre)}`);
  genreBooks = await res.json();
  selectedGenreBookId = null;

  document.getElementById("genreEmptyState").style.display = "block";
  document.getElementById("genreResultsArea").style.display = "none";

  renderGenreBookList(genreBooks);
}

function renderGenreBookList(books) {
  const container = document.getElementById("genreBookList");
  container.innerHTML = "";

  books.forEach(book => {
    const row = document.createElement("div");
    row.className = "book-row" + (book.id === selectedGenreBookId ? " selected" : "");
    row.innerHTML = `
      <img src="${book.thumbnail}" alt="">
      <div>
        <div class="book-row-title">${book.title}</div>
        <div class="book-row-author">${book.author}</div>
      </div>
    `;
    row.onclick = () => selectGenreBook(book.id, book.title);
    container.appendChild(row);
  });
}

async function selectGenreBook(bookId, title) {
  selectedGenreBookId = bookId;
  renderGenreBookList(genreBooks);

  document.getElementById("genreEmptyState").style.display = "none";
  document.getElementById("genreResultsArea").style.display = "block";
  document.getElementById("genreSelectedTitle").textContent = `Похоже на «${title}»`;

  const container = document.getElementById("genreRecommendations");
  container.innerHTML = "Загрузка...";

  let data;
  try {
    const res = await fetch(`${API_URL}/recommend-genre-rating/${bookId}`);
    if (!res.ok) throw new Error(res.status);
    data = await res.json();
  } catch (e) {
    container.innerHTML = `<p style="color:#A33;">Не удалось загрузить рекомендации.</p>`;
    return;
  }

  container.innerHTML = "";

  if (data.recommendations.length === 0) {
    container.innerHTML = `<p style="color:#8F8574;">Для этой книги пока нет похожих — попробуй другую.</p>`;
    return;
  }

  if (data.is_fallback) {
    const note = document.createElement("p");
    note.style.cssText = "color:#8A6A1E; font-size:13px; margin-bottom:12px;";
    note.textContent = "В этом жанре больше нет других книг — показаны похожие по рейтингу из всего каталога.";
    container.appendChild(note);
  }

  data.recommendations.forEach(book => {
    const card = document.createElement("div");
    card.className = "book-card";
    card.innerHTML = `
      <span class="similarity-badge trending-badge">★ ${book.average_rating.toFixed(1)} · ${book.ratings_count.toLocaleString()} оценок</span>
      <img src="${book.thumbnail}" alt="">
      <h4>${book.title}</h4>
      <div class="author">${book.author}</div>
    `;
    container.appendChild(card);
  });
}
// ===== FLOATING CHAT =====
let chatHistory = [];

document.getElementById("chatBubble").addEventListener("click", () => {
  document.getElementById("chatWindow").classList.add("open");
});

document.getElementById("chatClose").addEventListener("click", () => {
  document.getElementById("chatWindow").classList.remove("open");
});

function appendChatMessage(text, sender) {
  const container = document.getElementById("chatMessages");
  const msg = document.createElement("div");
  msg.className = "chat-msg " + (sender === "user" ? "chat-msg-user" : "chat-msg-bot");
  msg.textContent = text;
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
}

async function sendChatMessage() {
  const input = document.getElementById("chatInput");
  const text = input.value.trim();
  if (!text) return;

  appendChatMessage(text, "user");
  chatHistory.push({ role: "user", content: text });
  input.value = "";

  appendChatMessage("Печатает...", "bot");
  const container = document.getElementById("chatMessages");

  let reply;
  try {
    const res = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: chatHistory }),
    });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    reply = data.reply;
  } catch (e) {
    reply = "Не удалось связаться с сервером.";
  }

  container.removeChild(container.lastChild); // убираем "Печатает..."
  appendChatMessage(reply, "bot");
  chatHistory.push({ role: "assistant", content: reply });
}

document.getElementById("chatSend").addEventListener("click", sendChatMessage);
document.getElementById("chatInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendChatMessage();
});

// ===== NEW BOOK TAB (предсказание на новых данных) =====
async function searchGoogleBooks() {
  const query = document.getElementById("googleQuery").value.trim();
  if (!query) return;

  const container = document.getElementById("googleResults");
  container.innerHTML = `<p class="sidebar-hint">Поиск...</p>`;

  try {
    const res = await fetch(`${API_URL}/google-search?q=${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error(res.status);
    const books = await res.json();

    container.innerHTML = "";
    if (books.length === 0) {
      container.innerHTML = `<p class="sidebar-hint">Ничего не найдено.</p>`;
      return;
    }

    books.forEach(book => {
      const row = document.createElement("div");
      row.className = "book-row";
      row.innerHTML = `
        <img src="${book.thumbnail}" alt="">
        <div>
          <div class="book-row-title">${book.title}</div>
          <div class="book-row-author">${book.author}</div>
        </div>
      `;
      row.onclick = () => {
        container.querySelectorAll(".book-row").forEach(r => r.classList.remove("selected"));
        row.classList.add("selected");
        fillNewBookForm(book);
      };
      container.appendChild(row);
    });
  } catch (e) {
    container.innerHTML = `<p class="sidebar-hint" style="color:#D9776A;">Google Books сейчас недоступен — заполни форму вручную.</p>`;
  }
}

function fillNewBookForm(book) {
  document.getElementById("nbTitle").value = book.title;
  document.getElementById("nbGenre").value = book.genre;
  document.getElementById("nbPages").value = book.pages || "";
  document.getElementById("nbDescription").value = book.description;
}

document.getElementById("googleSearchBtn").addEventListener("click", searchGoogleBooks);
document.getElementById("googleQuery").addEventListener("keydown", (e) => {
  if (e.key === "Enter") searchGoogleBooks();
});

document.getElementById("newBookForm").addEventListener("submit", async (e) => {
  e.preventDefault(); // иначе форма перезагрузит страницу

  const payload = {
    title: document.getElementById("nbTitle").value.trim(),
    genre: document.getElementById("nbGenre").value.trim(),
    pages: Number(document.getElementById("nbPages").value) || 0,
    description: document.getElementById("nbDescription").value.trim(),
  };

  const info = document.getElementById("newBookInfo");
  const container = document.getElementById("newBookResults");
  info.innerHTML = "";
  container.innerHTML = "Загрузка...";

  try {
    const res = await fetch(`${API_URL}/recommend-new`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.status === 400) {
      const err = await res.json();
      container.innerHTML = "";
      info.innerHTML = `<div class="info-note">${err.detail}</div>`;
      return;
    }
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    renderNewBookResults(data);
  } catch (err) {
    container.innerHTML = `<p style="color:#A33;">Не удалось получить рекомендации. Проверь, что сервер запущен.</p>`;
  }
});

function renderNewBookResults(data) {
  const info = document.getElementById("newBookInfo");
  const container = document.getElementById("newBookResults");
  container.innerHTML = "";

  // Предупреждения — честно говорим, какая часть модели не смогла сработать
  const notes = [];
  if (!data.has_description) {
    notes.push("Нет описания — текстовая модель A не работает, рекомендации строятся только по жанру и объёму.");
  }
  if (!data.genre_known) {
    notes.push("Такого жанра нет в каталоге — жанр не учитывается, сходство считается по описанию и объёму.");
  }
  info.innerHTML = notes.map(n => `<div class="info-note">${n}</div>`).join("");

  const title = document.createElement("h3");
  title.className = "section-label";
  title.textContent = "Похожие книги из каталога";
  info.appendChild(title);

  data.recommendations.forEach(book => {
    const exp = book.explanation;
    const card = document.createElement("div");
    card.className = "book-card";
    card.innerHTML = `
      <span class="similarity-badge">${(book.similarity * 100).toFixed(0)}% совпадение</span>
      <img src="${book.thumbnail}" alt="">
      <h4>${book.title}</h4>
      <div class="author">${book.author}</div>
      <div class="explain">${exp.genre_match ? "Тот же жанр" : `Другой жанр (${exp.genre})`} · разница ${exp.pages_diff.toFixed(0)} стр.</div>
      <div class="breakdown">
        0.7 × текст ${exp.text_similarity} + 0.3 × жанр/стр. ${exp.genre_pages_similarity}
        = <b>${exp.total_similarity}</b>
      </div>
    `;
    container.appendChild(card);
  });
}

// ===== RPA: ПИСЬМО С ПОДБОРКОЙ (human-in-the-loop) =====
const emailModal = document.getElementById("emailModal");
const emailStatus = document.getElementById("emailStatus");
const emailSendBtn = document.getElementById("emailSend");

function showEmailStatus(text, isError = false) {
  emailStatus.innerHTML = text ? `<div class="info-note ${isError ? "error-note" : ""}">${text}</div>` : "";
}

function closeEmailModal() {
  emailModal.classList.remove("open");
}

// Шаг 1: агент готовит черновик письма для выбранной книги
document.getElementById("emailOpenBtn").addEventListener("click", async () => {
  if (selectedBookId === null) return;

  emailModal.classList.add("open");
  document.getElementById("emailSubject").value = "";
  document.getElementById("emailBody").value = "Агент готовит черновик письма...";
  emailSendBtn.disabled = true;
  showEmailStatus("");

  try {
    const res = await fetch(`${API_URL}/email/draft/${selectedBookId}`);
    if (!res.ok) throw new Error(res.status);
    const draft = await res.json();
    document.getElementById("emailSubject").value = draft.subject;
    document.getElementById("emailBody").value = draft.body;
    emailSendBtn.disabled = false;
  } catch (e) {
    document.getElementById("emailBody").value = "";
    showEmailStatus("Не удалось подготовить черновик.", true);
  }
});

// Шаг 2: человек проверил текст и сам нажал "Отправить"
emailSendBtn.addEventListener("click", async () => {
  const payload = {
    to: document.getElementById("emailTo").value.trim(),
    subject: document.getElementById("emailSubject").value.trim(),
    body: document.getElementById("emailBody").value.trim(),
    book_id: selectedBookId,
  };
  if (!payload.to) {
    showEmailStatus("Укажи адрес получателя.", true);
    return;
  }

  emailSendBtn.disabled = true;
  showEmailStatus("Отправка...");

  try {
    const res = await fetch(`${API_URL}/email/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Ошибка отправки");
    showEmailStatus(`✓ Письмо отправлено на ${payload.to}`);
    setTimeout(closeEmailModal, 1500);
  } catch (e) {
    showEmailStatus(e.message === "Failed to fetch" ? "Сервер недоступен." : e.message, true);
  } finally {
    emailSendBtn.disabled = false;
  }
});

document.getElementById("emailClose").addEventListener("click", closeEmailModal);
document.getElementById("emailCancel").addEventListener("click", closeEmailModal);

// ===== INIT =====
loadBooks();
loadDashboard();
loadGenres();

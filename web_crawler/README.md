# 🎬 SSR1 Scrape Center Movie Crawler

本專案為一個用 Python 實作的爬蟲工具，用於自動爬取  
<https://ssr1.scrape.center/>  
網站中的電影資料，涵蓋 **全部 10 頁的電影列表**，並進入每部電影的詳細頁抓取完整資訊，最後輸出成 `movies.csv`。

本爬蟲採用 `requests` + `BeautifulSoup` 解析 HTML，並遵循該示範網站的正當使用目的。

---

## 📌 **爬取資訊項目**

從列表頁 (`page/1 ~ page/10`) 提取：

- **電影名稱**
- **電影圖片 URL**
- **評分**
- **類型**

從詳細頁 (`/detail/x`) 額外提取：

- **電影類別（button.category）**

---

## 📂 **資料輸出格式：movies.csv**

CSV 欄位：

| 欄位名稱 | 說明 |
|---------|------|
| `title` | 電影名稱 |
| `image_url` | 電影海報 URL |
| `score` | 電影評分（無則留空） |
| `categories` | 電影類型（以 `/` 分隔） |



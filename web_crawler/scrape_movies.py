import csv
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://ssr1.scrape.center"

def fetch(url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.text

def parse_detail(url):
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")

    category_tags = soup.select("button.category")
    categories = [c.get_text(strip=True) for c in category_tags]
    categories_str = " / ".join(categories)

    return categories_str

def parse_list(page):
    url = f"{BASE_URL}/page/{page}"
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")

    cards = soup.select(".el-card.item.m-t.is-hover-shadow")
    movies = []

    for card in cards:
        name = card.select_one(".name").get_text(strip=True)
        img = urljoin(BASE_URL, card.select_one("img")["src"])
        score_tag = card.select_one(".score")
        score = score_tag.get_text(strip=True) if score_tag else ""

        detail_link = urljoin(BASE_URL, card.select_one("a")["href"])
        categories = parse_detail(detail_link)

        movies.append({
            "title": name,
            "image_url": img,
            "score": score,
            "categories": categories
        })

    return movies


all_movies = []
for p in range(1, 10 + 1):
    print("page", p)
    all_movies.extend(parse_list(p))

with open("movies.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["title", "image_url", "score", "categories"])
    writer.writeheader()
    writer.writerows(all_movies)

print("done:", len(all_movies))

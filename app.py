from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import altair as alt
import certifi
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_ENDPOINT = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/F-A0010-001"
DATASET_ID = "F-A0010-001"
CACHED_FALLBACK_API_KEY = "CWA-1FFDDAEC-161F-46A3-BE71-93C32C52829F"
CACHE_TTL_SECONDS = 60 * 15
DEFAULT_LOCATION = os.getenv("CWA_DEFAULT_LOCATION", "北部地區")
DB_PATH = Path("data.db")
WEATHER_ICON_MAP = {
    "1": "☀️",
    "2": "🌤️",
    "3": "⛅",
    "4": "🌥️",
    "5": "☁️",
    "6": "🌧️",
    "7": "🌦️",
    "8": "🌦️",
    "9": "🌫️",
    "10": "❄️",
    "11": "🌬️",
    "12": "🌨️",
    "13": "🌧️",
    "14": "⛈️",
}


def main() -> None:
    st.set_page_config(
        page_title="36小時天氣預報",
        layout="wide",
        page_icon="⛅",
        initial_sidebar_state="collapsed",
    )

    api_key = (os.getenv("CWA_API_KEY") or CACHED_FALLBACK_API_KEY).strip()
    if not api_key:
        st.error("請在環境變數或 `.env` 檔中設定 `CWA_API_KEY` 以取得資料。")
        st.stop()

    initialize_theme_state()
    apply_theme(st.session_state.get("theme", "light"))

    st.title("全臺農業一週氣象儀表板")

    header_cols = st.columns([3, 1, 1])
    with header_cols[1]:
        theme_toggle = st.toggle("深色模式", value=st.session_state.get("theme") == "dark")
        if theme_toggle:
            st.session_state["theme"] = "dark"
        else:
            st.session_state["theme"] = "light"
        apply_theme(st.session_state["theme"])

    with header_cols[2]:
        refresh_requested = st.button("重新整理資料", use_container_width=True, type="primary")
    if refresh_requested:
        load_forecast_data.clear()

    with st.spinner("載入資料中..."):
        try:
            dataset = load_forecast_data(api_key)
        except Exception as exc:  # pylint: disable=broad-except
            st.error(f"資料載入失敗：{exc}")
            st.stop()

    if refresh_requested:
        st.toast("資料已重新整理")

    locations = dataset["locations"]
    if not locations:
        st.info("目前沒有可用的地區資料")
        st.stop()

    if dataset.get("notice"):
        st.warning(f"即時資料取得失敗，顯示最後一次儲存資料：{dataset['notice']}")
    elif dataset.get("source") == "cache":
        st.info("顯示來自 SQLite 快取的資料")

    issue_time = dataset.get("issue_time")
    if issue_time:
        st.caption(f"資料發布時間：{issue_time.strftime('%Y-%m-%d %H:%M')} (臺北時間)")

    weather_profile = dataset.get("weather_profile")
    if weather_profile:
        st.info(f"天氣概況：{weather_profile}")

    left_col, right_col = st.columns([1.1, 2.1], gap="large")
    with left_col:
        selected_location = render_location_selector(locations)
    with right_col:
        render_location_details(selected_location)


def initialize_theme_state() -> None:
    if "theme" not in st.session_state:
        st.session_state["theme"] = "light"


def apply_theme(mode: str) -> None:
    palette = {
        "light": {
            "background": "#F4F6FB",
            "text": "#0F172A",
            "card": "#FFFFFF",
            "muted": "#475569",
            "accent": "#0284C7",
        },
        "dark": {
            "background": "#0F172A",
            "text": "#F8FAFC",
            "card": "#1E293B",
            "muted": "#CBD5F5",
            "accent": "#38BDF8",
        },
    }
    colors = palette.get(mode, palette["light"])
    st.markdown(
        f"""
        <style>
        :root {{
            --dashboard-muted: {colors["muted"]};
            --dashboard-card: {colors["card"]};
        }}
        div[data-testid="stAppViewContainer"] {{
            background-color: {colors["background"]};
            color: {colors["text"]};
        }}
        div[data-testid="stSidebar"] {{
            background-color: {colors["card"]};
        }}
        .weather-card {{
            background-color: var(--dashboard-card);
            padding: 1rem;
            border-radius: 12px;
            margin-bottom: 0.5rem;
            border: 1px solid rgba(15, 23, 42, 0.06);
        }}
        .weather-card.active {{
            border: 1px solid {colors["accent"]};
            box-shadow: 0 8px 20px rgba(2, 132, 199, 0.15);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_forecast_data(api_key: str) -> Dict[str, Any]:
    payload, source, notice = retrieve_payload(api_key)
    locations = normalize_locations(payload)
    issue_time = infer_issue_time(payload)
    weather_profile = extract_weather_profile(payload)
    return {
        "locations": locations,
        "issue_time": issue_time,
        "weather_profile": weather_profile,
        "source": source,
        "notice": notice,
    }


def fetch_forecast(api_key: str) -> Dict[str, Any]:
    params = {
        "Authorization": api_key,
        "downloadType": "WEB",
        "format": "JSON",
    }
    response = requests.get(
        API_ENDPOINT,
        params=params,
        timeout=15,
        verify=certifi.where(),
    )
    response.raise_for_status()
    data = response.json()
    if "cwaopendata" not in data:
        raise RuntimeError("資料來源未回傳 cwaopendata 區塊")
    return data


def retrieve_payload(api_key: str) -> tuple[Dict[str, Any], str, Optional[str]]:
    ensure_database()
    try:
        payload = fetch_forecast(api_key)
    except Exception as exc:  # pylint: disable=broad-except
        cached = load_cached_payload()
        if cached is None:
            raise
        return cached, "cache", str(exc)
    persist_payload(payload)
    return payload, "live", None


def ensure_database() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS forecast_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset TEXT NOT NULL,
                payload TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )


def persist_payload(payload: Dict[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO forecast_cache (dataset, payload, fetched_at) VALUES (?, ?, ?)",
            (DATASET_ID, serialized, datetime.utcnow().isoformat()),
        )
        conn.commit()


def load_cached_payload() -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT payload FROM forecast_cache WHERE dataset=? ORDER BY id DESC LIMIT 1",
            (DATASET_ID,),
        ).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def normalize_locations(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    locations = extract_locations(payload)
    normalized = []
    for raw in locations:
        normalized_location = parse_location(raw)
        if normalized_location["timeline"]:
            normalized.append(normalized_location)
    return sorted(normalized, key=lambda item: item["name"])


def extract_locations(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    resource = extract_resource(payload)
    agr_data = ((resource or {}).get("data") or {}).get("agrWeatherForecasts") or {}
    forecasts = (agr_data.get("weatherForecasts") or {}).get("location") or []
    if isinstance(forecasts, dict):
        return [forecasts]
    if isinstance(forecasts, list):
        return forecasts
    return []


def extract_resource(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    resources = payload.get("cwaopendata", {}).get("resources")
    if isinstance(resources, dict):
        resource = resources.get("resource")
        if isinstance(resource, list):
            return resource[0]
        return resource
    if isinstance(resources, list) and resources:
        return resources[0]
    return None


def extract_weather_profile(payload: Dict[str, Any]) -> Optional[str]:
    resource = extract_resource(payload)
    agr_data = ((resource or {}).get("data") or {}).get("agrWeatherForecasts") or {}
    return agr_data.get("weatherProfile")


def parse_location(data: Dict[str, Any]) -> Dict[str, Any]:
    timeline = build_timeline(data.get("weatherElements", {}))
    return {
        "name": data.get("locationName", "未知地區"),
        "parameters": {},
        "timeline": timeline,
    }


def build_timeline(elements: Dict[str, Any]) -> List[Dict[str, Any]]:
    date_map: Dict[str, Dict[str, Any]] = {}
    for key, element in elements.items():
        daily = element.get("daily")
        if not isinstance(daily, list):
            continue
        for entry in daily:
            date_str = entry.get("dataDate")
            if not date_str:
                continue
            slot = date_map.setdefault(
                date_str,
                {
                    "startTime": parse_time(date_str),
                    "endTime": None,
                    "weather": None,
                    "weather_code": None,
                    "pop": None,
                    "min_temp": None,
                    "max_temp": None,
                    "apparent_temp": None,
                    "comfort": None,
                },
            )
            if key == "Wx":
                slot["weather"] = entry.get("weather")
                slot["weather_code"] = entry.get("weatherid")
            elif key == "MinT":
                slot["min_temp"] = to_float(entry.get("temperature"))
            elif key == "MaxT":
                slot["max_temp"] = to_float(entry.get("temperature"))
    for slot in date_map.values():
        temps = [temp for temp in [slot["min_temp"], slot["max_temp"]] if temp is not None]
        slot["avg_temp"] = sum(temps) / len(temps) if temps else None
    return [
        slot for _, slot in sorted(date_map.items(), key=lambda item: item[0])
    ]


def to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def infer_issue_time(payload: Dict[str, Any]) -> Optional[datetime]:
    resource = extract_resource(payload)
    metadata = (resource or {}).get("metadata") or {}
    temporal = metadata.get("temporal") or {}
    issue_time = temporal.get("issueTime")
    return parse_time(issue_time)


def render_location_selector(locations: List[Dict[str, Any]]) -> Dict[str, Any]:
    st.subheader("區域列表")
    query = st.text_input("搜尋地區", placeholder="輸入地區或關鍵字").strip()
    if query:
        normalized_query = query.lower()
        filtered = [
            loc
            for loc in locations
            if normalized_query in loc["name"].lower()
            or normalized_query in " ".join(loc.get("parameters", {}).values()).lower()
        ]
    else:
        filtered = locations
    if not filtered:
        st.info("沒有符合條件的地區")
        st.stop()
    indices = list(range(len(filtered)))
    default_index = 0
    for idx, loc in enumerate(filtered):
        if loc["name"] == DEFAULT_LOCATION:
            default_index = idx
            break
    default_index = min(default_index, len(filtered) - 1)
    selected_idx = st.radio(
        "選擇地區",
        options=indices,
        index=default_index,
        label_visibility="collapsed",
        format_func=lambda idx: format_location_label(filtered[idx]),
    )

    overview_df = build_overview_dataframe(filtered)
    st.dataframe(
        overview_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "地區": st.column_config.Column("地區"),
            "天氣": st.column_config.Column("天氣"),
            "最高溫": st.column_config.Column("最高溫"),
            "最低溫": st.column_config.Column("最低溫"),
            "平均溫度": st.column_config.Column("平均溫度"),
        },
    )
    return filtered[selected_idx]


def format_location_label(location: Dict[str, Any]) -> str:
    slot = location["timeline"][0]
    icon = resolve_icon(slot)
    temp_text = format_temperature(slot)
    weather = slot.get("weather") or ""
    return f"{icon} {location['name']}｜{temp_text}｜{weather}"


def build_overview_dataframe(locations: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for loc in locations:
        slot = loc["timeline"][0]
        rows.append(
            {
                "地區": loc["name"],
                "天氣": f"{resolve_icon(slot)} {slot.get('weather') or '—'}",
                "最高溫": format_temperature_value(slot.get("max_temp")),
                "最低溫": format_temperature_value(slot.get("min_temp")),
                "平均溫度": format_temperature_value(slot.get("avg_temp")),
            }
        )
    return pd.DataFrame(rows)


def render_location_details(location: Dict[str, Any]) -> None:
    st.subheader(f"{location['name']} 詳細預報")
    timeline = location["timeline"]
    if not timeline:
        st.warning("此地區暫無時間序列資料")
        return
    current_slot = timeline[0]
    metrics = st.columns(4)
    with metrics[0]:
        st.metric("最高溫", format_temperature_value(current_slot.get("max_temp")))
    with metrics[1]:
        st.metric("最低溫", format_temperature_value(current_slot.get("min_temp")))
    with metrics[2]:
        st.metric("平均溫度", format_temperature_value(current_slot.get("avg_temp")))
    with metrics[3]:
        st.metric("天氣現象", current_slot.get("weather") or "—")

    st.markdown("#### 日別預報卡片")
    card_cols = st.columns(len(timeline))
    for col, slot in zip(card_cols, timeline):
        with col:
            st.markdown(render_slot_card(slot), unsafe_allow_html=True)

    chart_df = build_chart_dataframe(timeline)
    if not chart_df.empty:
        st.markdown("#### 溫度趨勢")
        chart = (
            alt.Chart(chart_df)
            .transform_fold(
                ["最高溫", "最低溫", "平均溫度"],
                as_=["類型", "溫度"],
            )
            .mark_line(point=True)
            .encode(
                x=alt.X("時間:T", axis=alt.Axis(format="%m/%d")),
                y=alt.Y("溫度:Q", title="°C"),
                color="類型:N",
                tooltip=["時間:T", "類型:N", "溫度:Q"],
            )
        )
        st.altair_chart(chart, use_container_width=True)

    st.markdown("#### 詳細資料")
    table_df = build_details_dataframe(timeline)
    st.dataframe(
        table_df,
        hide_index=True,
        use_container_width=True,
    )


def build_chart_dataframe(timeline: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for slot in timeline:
        if not slot.get("startTime"):
            continue
        if (
            slot.get("avg_temp") is None
            and slot.get("min_temp") is None
            and slot.get("max_temp") is None
        ):
            continue
        rows.append(
            {
                "時間": slot["startTime"],
                "最高溫": slot.get("max_temp"),
                "最低溫": slot.get("min_temp"),
                "平均溫度": slot.get("avg_temp"),
            }
        )
    return pd.DataFrame(rows)


def build_details_dataframe(timeline: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for slot in timeline:
        rows.append(
            {
                "日期": format_time(slot.get("startTime")),
                "天氣": f"{resolve_icon(slot)} {slot.get('weather') or '—'}",
                "最低溫": format_temperature_value(slot.get("min_temp")),
                "最高溫": format_temperature_value(slot.get("max_temp")),
                "平均溫度": format_temperature_value(slot.get("avg_temp")),
            }
        )
    return pd.DataFrame(rows)


def render_slot_card(slot: Dict[str, Any]) -> str:
    icon = resolve_icon(slot)
    start = format_time(slot.get("startTime"))
    weather = slot.get("weather") or "—"
    temp_range = format_temp_range(slot.get("min_temp"), slot.get("max_temp"))
    avg = format_temperature_value(slot.get("avg_temp"))
    return f"""
    <div class="weather-card">
        <div style="font-size:0.9rem;color:var(--dashboard-muted, #475569);">{start}</div>
        <div style="font-size:2rem;line-height:1;margin:0.2rem 0;">{icon}</div>
        <div style="font-weight:600;font-size:1.1rem;">{weather}</div>
        <div style="margin-top:0.3rem;">溫度：{temp_range}</div>
        <div>平均：{avg}</div>
    </div>
    """


def format_temperature(slot: Dict[str, Any]) -> str:
    return format_temp_range(slot.get("min_temp"), slot.get("max_temp"))


def format_temp_range(min_temp: Optional[float], max_temp: Optional[float]) -> str:
    if min_temp is None and max_temp is None:
        return "—"
    if min_temp is None:
        return f"{max_temp:.1f}°C"
    if max_temp is None:
        return f"{min_temp:.1f}°C"
    if abs(max_temp - min_temp) < 0.1:
        return f"{(min_temp + max_temp) / 2:.1f}°C"
    return f"{min_temp:.1f}°C ~ {max_temp:.1f}°C"


def format_temperature_value(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}°C"


def format_time(value: Optional[datetime]) -> str:
    if not value:
        return "—"
    if value.hour == 0 and value.minute == 0:
        return value.strftime("%m/%d")
    return value.strftime("%m/%d %H:%M")


def resolve_icon(slot: Dict[str, Any]) -> str:
    code = slot.get("weather_code")
    if code:
        normalized = code.lstrip("0")
        if normalized in WEATHER_ICON_MAP:
            return WEATHER_ICON_MAP[normalized]
        if code in WEATHER_ICON_MAP:
            return WEATHER_ICON_MAP[code]
    text = (slot.get("weather") or "").strip()
    if "雷" in text:
        return "⛈️"
    if "雨" in text:
        return "🌧️"
    if "晴" in text:
        return "☀️"
    if "雲" in text or "陰" in text:
        return "☁️"
    if "雪" in text:
        return "❄️"
    return "🌡️"


if __name__ == "__main__":
    main()

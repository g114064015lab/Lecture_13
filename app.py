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
import pydeck as pdk
import streamlit as st
from dotenv import load_dotenv
from requests.packages.urllib3.exceptions import InsecureRequestWarning

load_dotenv()

API_ENDPOINT = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001"
DATASET_ID = "F-A0021-001"
CACHED_FALLBACK_API_KEY = "CWA-FE3705DB-3102-48DE-B396-30F5D45306C2"
CACHE_TTL_SECONDS = 60 * 15
DEFAULT_LOCATION = os.getenv("CWA_DEFAULT_LOCATION", "臺北市")
VERIFY_SSL = os.getenv("CWA_STRICT_SSL", "false").lower() == "true"
if not VERIFY_SSL:
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
DB_PATH = Path("data.db")
SAMPLE_JSON_PATH = Path(__file__).with_name("F-A0021-001.json")
WEATHER_ICON_MAP = {
    "1": "☀️",
    "01": "☀️",
    "2": "🌤️",
    "02": "🌤️",
    "3": "⛅",
    "03": "⛅",
    "4": "🌥️",
    "04": "🌥️",
    "5": "☁️",
    "05": "☁️",
    "6": "🌧️",
    "06": "🌧️",
    "7": "🌦️",
    "07": "🌦️",
    "8": "⛈️",
    "08": "⛈️",
    "9": "🌫️",
    "09": "🌫️",
    "10": "❄️",
    "11": "🌬️",
    "12": "🌨️",
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

    st.title("全臺 36 小時天氣預報儀表板")

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
        st.warning(f"即時資料取得失敗，切換至備援資料：{dataset['notice']}")

    if dataset.get("source") == "cache":
        st.info("顯示來自 SQLite 快取的資料")
    elif dataset.get("source") == "sample":
        st.info("顯示內建範例檔 F-A0021-001.json 的資料")

    issue_time = dataset.get("issue_time")
    if issue_time:
        st.caption(f"資料發布時間：{issue_time.strftime('%Y-%m-%d %H:%M')} (臺北時間)")

    render_overview_map(locations)

    left_col, right_col = st.columns([1.1, 2.1], gap="large")
    with left_col:
        selected_location = render_location_selector(locations)
    with right_col:
        render_location_map(selected_location)
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
    issue_time = infer_issue_time(locations)
    dataset_type = determine_dataset_type(locations)
    return {
        "locations": locations,
        "issue_time": issue_time,
        "dataset_type": dataset_type,
        "source": source,
        "notice": notice,
    }


def fetch_forecast(api_key: str) -> Dict[str, Any]:
    params = {
        "Authorization": api_key,
        "format": "JSON",
    }
    response = requests.get(
        API_ENDPOINT,
        params=params,
        timeout=15,
        verify=certifi.where() if VERIFY_SSL else False,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success", False):
        message = data.get("message") or "中央氣象署 API 回應失敗"
        raise RuntimeError(message)
    return data


def retrieve_payload(api_key: str) -> tuple[Dict[str, Any], str, Optional[str]]:
    ensure_database()
    try:
        payload = fetch_forecast(api_key)
    except Exception as exc:  # pylint: disable=broad-except
        cached = load_cached_payload()
        if cached is not None:
            return cached, "cache", str(exc)
        sample = load_sample_payload()
        if sample is not None:
            return sample, "sample", str(exc)
        raise
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


def load_sample_payload() -> Optional[Dict[str, Any]]:
    if SAMPLE_JSON_PATH.exists():
        return json.loads(SAMPLE_JSON_PATH.read_text(encoding="utf-8"))
    return None


def normalize_locations(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = payload.get("records", {}) if isinstance(payload, dict) else {}
    raw_locations = records.get("location", [])
    normalized: List[Dict[str, Any]] = []
    for raw in raw_locations:
        normalized_location = parse_location(raw)
        if normalized_location["timeline"]:
            normalized.append(normalized_location)
    if normalized:
        return sorted(normalized, key=lambda item: item["name"])

    tide_forecasts = extract_tide_forecasts(payload)
    tide_locations: List[Dict[str, Any]] = []
    for forecast in tide_forecasts:
        parsed = parse_tide_location(forecast)
        if parsed["timeline"]:
            tide_locations.append(parsed)
    return sorted(tide_locations, key=lambda item: item["name"])


def parse_location(data: Dict[str, Any]) -> Dict[str, Any]:
    element_map = {
        element.get("elementName"): element.get("time", [])
        for element in data.get("weatherElement", [])
        if element.get("elementName")
    }
    timeline = build_timeline(element_map)
    parameter_map = {
        param.get("parameterName"): param.get("parameterValue")
        for param in data.get("parameter", [])
        if param.get("parameterName")
    }
    return {
        "name": data.get("locationName", "未知地區"),
        "parameters": parameter_map,
        "timeline": timeline,
        "category": "weather",
    }


def build_timeline(elements: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    reference_series = get_reference_series(elements)
    timeline: List[Dict[str, Any]] = []
    for idx, reference_block in enumerate(reference_series):
        start_time = parse_time(reference_block.get("startTime") or reference_block.get("dataTime"))
        end_time = parse_time(reference_block.get("endTime"))
        weather_block = (
            reference_block
            if reference_block.get("parameter")
            else get_element_entry(elements, idx, ["Wx", "WeatherDescription"])
        )
        slot = {
            "startTime": start_time,
            "endTime": end_time,
            "weather": extract_text(weather_block),
            "weather_code": extract_value(weather_block, prefer_value="parameterValue"),
            "pop": to_float(extract_value(get_element_entry(elements, idx, ["PoP", "PoP12h"]))),
            "min_temp": to_float(extract_value(get_element_entry(elements, idx, ["MinT"]))),
            "max_temp": to_float(extract_value(get_element_entry(elements, idx, ["MaxT"]))),
            "apparent_temp": to_float(extract_value(get_element_entry(elements, idx, ["AT", "ApparentT"]))),
            "comfort": extract_text(get_element_entry(elements, idx, ["CI"])),
            "unit": "°C",
        }
        temps = [temp for temp in [slot["min_temp"], slot["max_temp"]] if temp is not None]
        slot["avg_temp"] = sum(temps) / len(temps) if temps else None
        timeline.append(slot)
    return timeline


def get_reference_series(elements: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    preferred_order = ["Wx", "WeatherDescription", "MinT", "MaxT"]
    for key in preferred_order:
        series = elements.get(key)
        if series:
            return series
    return next(iter(elements.values()), [])


def get_element_entry(
    elements: Dict[str, List[Dict[str, Any]]], index: int, candidates: List[str]
) -> Optional[Dict[str, Any]]:
    for key in candidates:
        series = elements.get(key)
        if series and 0 <= index < len(series):
            return series[index]
    return None


def extract_value(block: Optional[Dict[str, Any]], prefer_value: str = "parameterName") -> Optional[str]:
    if not block:
        return None
    parameter = block.get("parameter")
    if isinstance(parameter, dict):
        if prefer_value == "parameterValue":
            return parameter.get("parameterValue") or parameter.get("parameterName")
        return parameter.get("parameterName") or parameter.get("parameterValue")
    element_value = block.get("elementValue")
    if isinstance(element_value, list) and element_value:
        candidate = element_value[0]
        return candidate.get("value") or candidate.get("measures")
    return block.get("value")


def extract_text(block: Optional[Dict[str, Any]]) -> Optional[str]:
    value = extract_value(block)
    if value:
        return str(value)
    return None


def extract_tide_forecasts(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = payload.get("records")
    if isinstance(records, dict):
        forecasts = records.get("TideForecasts")
        if isinstance(forecasts, list):
            return forecasts
    cwa = payload.get("cwaopendata")
    if isinstance(cwa, dict):
        resources = cwa.get("Resources") or cwa.get("resources") or {}
        resource = resources.get("Resource") or resources.get("resource")
        if isinstance(resource, list):
            resource = resource[0]
        data = (resource or {}).get("Data") or (resource or {}).get("data")
        forecasts = data.get("TideForecasts") if isinstance(data, dict) else None
        if isinstance(forecasts, list):
            return forecasts
    return []


def parse_tide_location(forecast: Dict[str, Any]) -> Dict[str, Any]:
    location = forecast.get("Location") or {}
    daily_periods = (
        (location.get("TimePeriods") or {}).get("Daily") or []
    )
    timeline = build_tide_timeline(daily_periods)
    return {
        "name": location.get("LocationName", "未知地區"),
        "parameters": {
            "LocationId": location.get("LocationId"),
            "Latitude": location.get("Latitude"),
            "Longitude": location.get("Longitude"),
        },
        "timeline": timeline,
        "category": "tide",
    }


def build_tide_timeline(daily_periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    timeline: List[Dict[str, Any]] = []
    for daily in daily_periods[:3]:
        times = daily.get("Time") or []
        if not times:
            continue
        start_time = parse_time(times[0].get("DateTime"))
        end_time = parse_time(times[-1].get("DateTime"))
        heights = []
        for entry in times:
            tide_heights = entry.get("TideHeights") or {}
            heights.append(to_float(tide_heights.get("AboveTWVD")))
        heights = [h for h in heights if h is not None]
        min_height = convert_height_to_meters(min(heights)) if heights else None
        max_height = convert_height_to_meters(max(heights)) if heights else None
        avg_height = (
            convert_height_to_meters(sum(heights) / len(heights))
            if heights
            else None
        )
        slot = {
            "startTime": start_time,
            "endTime": end_time,
            "weather": f"{daily.get('TideRange', '')}潮",
            "weather_code": None,
            "pop": tide_range_to_probability(daily.get("TideRange")),
            "min_temp": min_height,
            "max_temp": max_height,
            "apparent_temp": avg_height,
            "comfort": describe_daily_tide(times),
            "unit": "m",
        }
        temps = [temp for temp in [min_height, max_height] if temp is not None]
        slot["avg_temp"] = sum(temps) / len(temps) if temps else avg_height
        timeline.append(slot)
    return timeline


def convert_height_to_meters(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value / 100  # convert centimeters to meters


def tide_range_to_probability(tide_range: Optional[str]) -> Optional[float]:
    if tide_range is None:
        return None
    mapping = {
        "大": 90,
        "中": 60,
        "小": 30,
    }
    return mapping.get(tide_range.strip())


def describe_daily_tide(events: List[Dict[str, Any]]) -> str:
    descriptions = []
    for entry in events[:3]:
        timestamp = parse_time(entry.get("DateTime"))
        tide = entry.get("Tide")
        if timestamp and tide:
            descriptions.append(f"{timestamp.strftime('%H:%M')}{tide}")
    return "、".join(descriptions) if descriptions else "—"


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


def infer_issue_time(locations: List[Dict[str, Any]]) -> Optional[datetime]:
    times = [
        slot["startTime"]
        for location in locations
        for slot in location.get("timeline", [])[:1]
        if slot.get("startTime")
    ]
    return min(times) if times else None


def determine_dataset_type(locations: List[Dict[str, Any]]) -> str:
    if not locations:
        return "unknown"
    if all(location.get("category") == "tide" for location in locations):
        return "tide"
    if all(location.get("category") == "weather" for location in locations):
        return "weather"
    return "mixed"


def render_location_selector(locations: List[Dict[str, Any]]) -> Dict[str, Any]:
    st.subheader("縣市列表")
    query = st.text_input("搜尋縣市", placeholder="輸入縣市或關鍵字").strip()
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
    selected_idx = st.selectbox(
        "選擇縣市",
        options=indices,
        index=default_index,
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
            "指標值": st.column_config.Column("潮高/溫度"),
            "指標(%)": st.column_config.Column("概率指標"),
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
                "指標值": format_temperature(slot),
                "指標(%)": format_percentage(slot.get("pop")),
            }
        )
    return pd.DataFrame(rows)


def render_location_map(location: Dict[str, Any]) -> None:
    lat = to_float(location.get("parameters", {}).get("Latitude"))
    lon = to_float(location.get("parameters", {}).get("Longitude"))
    center_lat, center_lon = (lat, lon) if lat and lon else (23.6978, 120.9605)
    zoom = 9 if lat and lon else 6
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=[
            {
                "lat": center_lat,
                "lon": center_lon,
                "name": location["name"],
                "value": location["timeline"][0].get("avg_temp"),
            }
        ],
        get_position="[lon, lat]",
        get_fill_color="[0, 122, 255, 180]",
        get_radius=15000,
        pickable=True,
    )
    tile_layer = pdk.Layer(
        "TileLayer",
        data="https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        min_zoom=0,
        max_zoom=19,
        tile_size=256,
    )
    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom,
        pitch=30,
    )
    deck = pdk.Deck(
        map_style=None,
        initial_view_state=view_state,
        layers=[tile_layer, layer],
        tooltip={"text": "{name}\n指標: {value}"},
    )
    st.pydeck_chart(deck, use_container_width=True)


def render_overview_map(locations: List[Dict[str, Any]]) -> None:
    points = []
    for loc in locations:
        lat = to_float(loc.get("parameters", {}).get("Latitude"))
        lon = to_float(loc.get("parameters", {}).get("Longitude"))
        if lat is None or lon is None:
            continue
        slot = loc["timeline"][0]
        points.append(
            {
                "lat": lat,
                "lon": lon,
                "name": loc["name"],
                "value": slot.get("avg_temp"),
                "category": loc.get("category", "weather"),
            }
        )
    if not points:
        return
    color_expr = [
        "case",
        ["==", ["get", "category"], "tide"],
        [0, 122, 255, 180],
        [
            "interpolate",
            ["linear"],
            ["coalesce", ["get", "value"], 0],
            0,
            [56, 189, 248, 180],
            15,
            [74, 222, 128, 180],
            25,
            [250, 204, 21, 180],
            35,
            [248, 113, 113, 180],
            40,
            [239, 68, 68, 200],
        ],
    ]
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=points,
        get_position="[lon, lat]",
        get_fill_color=color_expr,
        get_radius=12000,
        pickable=True,
    )
    tile_layer = pdk.Layer(
        "TileLayer",
        data="https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        min_zoom=0,
        max_zoom=19,
        tile_size=256,
    )
    view_state = pdk.ViewState(
        latitude=23.6978,
        longitude=120.9605,
        zoom=6,
        pitch=0,
    )
    deck = pdk.Deck(
        map_style=None,
        initial_view_state=view_state,
        layers=[tile_layer, layer],
        tooltip={"text": "{name}\n指標: {value}"},
    )
    st.markdown("### 臺灣概覽")
    map_col, legend_col = st.columns([4, 1])
    with map_col:
        st.pydeck_chart(deck, use_container_width=True)
    with legend_col:
        st.markdown(
            """
            <div style="padding:0.5rem 0;">
              <div style="font-weight:600;margin-bottom:0.25rem;">顏色圖例</div>
              <div style="display:flex;align-items:center;margin-bottom:6px;">
                <span style="display:inline-block;width:14px;height:14px;background:#007AFF;border-radius:4px;margin-right:6px;"></span>
                <span>潮汐點位</span>
              </div>
              <div style="display:flex;align-items:center;margin-bottom:6px;">
                <span style="display:inline-block;width:14px;height:14px;background:#38BDF8;border-radius:4px;margin-right:6px;"></span>
                <span>溫度 < 15°C</span>
              </div>
              <div style="display:flex;align-items:center;margin-bottom:6px;">
                <span style="display:inline-block;width:14px;height:14px;background:#4ADE80;border-radius:4px;margin-right:6px;"></span>
                <span>15–25°C</span>
              </div>
              <div style="display:flex;align-items:center;margin-bottom:6px;">
                <span style="display:inline-block;width:14px;height:14px;background:#FACC15;border-radius:4px;margin-right:6px;"></span>
                <span>25–35°C</span>
              </div>
              <div style="display:flex;align-items:center;">
                <span style="display:inline-block;width:14px;height:14px;background:#EF4444;border-radius:4px;margin-right:6px;"></span>
                <span>＞ 35°C</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_location_details(location: Dict[str, Any]) -> None:
    is_tide = location.get("category") == "tide"
    title_suffix = "潮汐預報" if is_tide else "詳細預報"
    st.subheader(f"{location['name']} {title_suffix}")
    timeline = location["timeline"]
    if not timeline:
        st.warning("此地區暫無時間序列資料")
        return
    current_slot = timeline[0]
    metrics = st.columns(4)
    unit = current_slot.get("unit", "°C")
    if is_tide:
        with metrics[0]:
            st.metric("平均潮高", format_temperature_value(current_slot.get("avg_temp"), unit))
        with metrics[1]:
            st.metric("最大潮高", format_temperature_value(current_slot.get("max_temp"), unit))
        with metrics[2]:
            st.metric("最小潮高", format_temperature_value(current_slot.get("min_temp"), unit))
        with metrics[3]:
            st.metric("潮汐強度", current_slot.get("weather") or current_slot.get("comfort") or "—")
    else:
        with metrics[0]:
            st.metric("平均溫度", format_temperature_value(current_slot.get("avg_temp"), unit))
        with metrics[1]:
            st.metric("體感溫度", format_temperature_value(current_slot.get("apparent_temp"), unit))
        with metrics[2]:
            st.metric("降雨機率", format_percentage(current_slot.get("pop")))
        with metrics[3]:
            st.metric("舒適度", current_slot.get("comfort") or "—")

    section_title = "潮汐卡片 (近 3 日)" if is_tide else "36 小時時段卡片"
    st.markdown(f"#### {section_title}")
    card_cols = st.columns(len(timeline))
    for col, slot in zip(card_cols, timeline):
        with col:
            st.markdown(render_slot_card(slot, is_tide), unsafe_allow_html=True)

    chart_df = build_chart_dataframe(timeline, "tide" if is_tide else "weather")
    if not chart_df.empty:
        chart_title = "潮高趨勢" if is_tide else "溫度 vs. 體感溫度"
        fold_fields = (
            ["平均潮高", "最大潮高"]
            if is_tide
            else ["平均溫度", "體感溫度"]
        )
        y_title = "m" if is_tide else "°C"
        st.markdown(f"#### {chart_title}")
        chart = (
            alt.Chart(chart_df)
            .transform_fold(
                fold_fields,
                as_=["類型", "溫度"],
            )
            .mark_line(point=True)
            .encode(
                x=alt.X("時間:T", axis=alt.Axis(format="%m/%d %H:%M")),
                y=alt.Y("溫度:Q", title=y_title),
                color="類型:N",
                tooltip=["時間:T", "類型:N", "溫度:Q"],
            )
        )
        st.altair_chart(chart, use_container_width=True)

    st.markdown("#### 詳細資料")
    table_df = build_details_dataframe(timeline, "tide" if is_tide else "weather")
    st.dataframe(
        table_df,
        hide_index=True,
        use_container_width=True,
    )


def build_chart_dataframe(timeline: List[Dict[str, Any]], dataset_type: str) -> pd.DataFrame:
    rows = []
    for slot in timeline:
        if dataset_type == "tide":
            if slot.get("avg_temp") is None and slot.get("max_temp") is None:
                continue
            rows.append(
                {
                    "時間": slot["startTime"],
                    "平均潮高": slot.get("avg_temp"),
                    "最大潮高": slot.get("max_temp"),
                }
            )
        else:
            if slot.get("avg_temp") is None and slot.get("apparent_temp") is None:
                continue
            rows.append(
                {
                    "時間": slot["startTime"],
                    "平均溫度": slot.get("avg_temp"),
                    "體感溫度": slot.get("apparent_temp"),
                }
            )
    return pd.DataFrame(rows)


def build_details_dataframe(timeline: List[Dict[str, Any]], dataset_type: str) -> pd.DataFrame:
    rows = []
    for slot in timeline:
        entry = {
            "起始": format_time(slot.get("startTime")),
            "結束": format_time(slot.get("endTime")),
            "描述": f"{resolve_icon(slot)} {slot.get('weather') or '—'}",
            "指標值": format_temperature(slot),
            "補充": slot.get("comfort") or "—",
        }
        if dataset_type == "tide":
            entry["潮汐強度(%)"] = format_percentage(slot.get("pop"))
        else:
            entry["體感/降雨"] = f"{format_temperature_value(slot.get('apparent_temp'))} / {format_percentage(slot.get('pop'))}"
        rows.append(entry)
    return pd.DataFrame(rows)


def render_slot_card(slot: Dict[str, Any], is_tide: bool) -> str:
    icon = resolve_icon(slot)
    start = format_time(slot.get("startTime"))
    end = format_time(slot.get("endTime"))
    weather = slot.get("weather") or "—"
    temp_range = format_temperature(slot)
    pop = format_percentage(slot.get("pop"))
    apparent = format_temperature_value(slot.get("apparent_temp"), slot.get("unit", "°C"))
    second_line = "平均潮高" if is_tide else "體感"
    third_line = "潮汐指標" if is_tide else "降雨機率"
    metric_label = "潮高" if is_tide else "溫度"
    return f"""
    <div class="weather-card">
        <div style="font-size:0.9rem;color:var(--dashboard-muted, #475569);">{start} – {end or '—'}</div>
        <div style="font-size:2rem;line-height:1;margin:0.2rem 0;">{icon}</div>
        <div style="font-weight:600;font-size:1.1rem;">{weather}</div>
        <div style="margin-top:0.3rem;">{metric_label}：{temp_range}</div>
        <div>{second_line}：{apparent}</div>
        <div>{third_line}：{pop}</div>
    </div>
    """


def format_temperature(slot: Dict[str, Any]) -> str:
    unit = slot.get("unit", "°C")
    return format_temp_range(slot.get("min_temp"), slot.get("max_temp"), unit)


def format_temp_range(min_temp: Optional[float], max_temp: Optional[float], unit: str = "°C") -> str:
    if min_temp is None and max_temp is None:
        return "—"
    if min_temp is None:
        return f"{max_temp:.1f}{unit}"
    if max_temp is None:
        return f"{min_temp:.1f}{unit}"
    if abs(max_temp - min_temp) < 0.1:
        return f"{(min_temp + max_temp) / 2:.1f}{unit}"
    return f"{min_temp:.1f}{unit} ~ {max_temp:.1f}{unit}"


def format_temperature_value(value: Optional[float], unit: str = "°C") -> str:
    if value is None:
        return "—"
    return f"{value:.1f}{unit}"


def format_percentage(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{round(value)}%"


def format_time(value: Optional[datetime]) -> str:
    if not value:
        return "—"
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
    if "潮" in text:
        return "🌊"
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

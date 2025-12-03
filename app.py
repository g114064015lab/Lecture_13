from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import altair as alt
import certifi
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_ENDPOINT = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001"
CACHED_FALLBACK_API_KEY = "CWA-FE3705DB-3102-48DE-B396-30F5D45306C2"
CACHE_TTL_SECONDS = 60 * 15
DEFAULT_LOCATION = os.getenv("CWA_DEFAULT_LOCATION", "臺北市")
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

    issue_time = dataset.get("issue_time")
    if issue_time:
        st.caption(f"資料發布時間：{issue_time.strftime('%Y-%m-%d %H:%M')} (臺北時間)")

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
    payload = fetch_forecast(api_key)
    locations = normalize_locations(payload)
    issue_time = infer_issue_time(locations)
    return {
        "locations": locations,
        "issue_time": issue_time,
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
        verify=certifi.where(),
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success", False):
        message = data.get("message") or "中央氣象署 API 回應失敗"
        raise RuntimeError(message)
    return data


def normalize_locations(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = payload.get("records", {})
    raw_locations = records.get("location", [])
    normalized = []
    for raw in raw_locations:
        normalized_location = parse_location(raw)
        if normalized_location["timeline"]:
            normalized.append(normalized_location)
    return sorted(normalized, key=lambda item: item["name"])


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
    }


def build_timeline(elements: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    reference_series = get_reference_series(elements)
    timeline: List[Dict[str, Any]] = []
    for idx, reference_block in enumerate(reference_series):
        start_time = parse_time(reference_block.get("startTime") or reference_block.get("dataTime"))
        end_time = parse_time(reference_block.get("endTime"))
        weather_block = reference_block if reference_block.get("parameter") else get_element_entry(elements, idx, ["Wx", "WeatherDescription"])
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
    elements: Dict[str, List[Dict[str, Any]]], index: int, candidates: Iterable[str]
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
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z"):
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
    selected_idx = st.radio(
        "選擇縣市",
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
            "溫度": st.column_config.Column("溫度"),
            "降雨機率": st.column_config.Column("降雨機率"),
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
                "溫度": format_temperature(slot),
                "降雨機率": format_percentage(slot.get("pop")),
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
        st.metric("平均溫度", format_temperature(current_slot))
    with metrics[1]:
        st.metric("體感溫度", format_temperature_value(current_slot.get("apparent_temp")))
    with metrics[2]:
        st.metric("降雨機率", format_percentage(current_slot.get("pop")))
    with metrics[3]:
        st.metric("舒適度", current_slot.get("comfort") or "—")

    st.markdown("#### 36 小時時段卡片")
    card_cols = st.columns(len(timeline))
    for col, slot in zip(card_cols, timeline):
        with col:
            st.markdown(render_slot_card(slot), unsafe_allow_html=True)

    chart_df = build_chart_dataframe(timeline)
    if not chart_df.empty:
        st.markdown("#### 溫度 vs. 體感溫度")
        chart = (
            alt.Chart(chart_df)
            .transform_fold(
                ["平均溫度", "體感溫度"],
                as_=["類型", "溫度"],
            )
            .mark_line(point=True)
            .encode(
                x=alt.X("時間:T", axis=alt.Axis(format="%m/%d %H:%M")),
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


def build_details_dataframe(timeline: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for slot in timeline:
        rows.append(
            {
                "起始": format_time(slot.get("startTime")),
                "結束": format_time(slot.get("endTime")),
                "天氣": f"{resolve_icon(slot)} {slot.get('weather') or '—'}",
                "溫度": format_temp_range(slot.get("min_temp"), slot.get("max_temp")),
                "體感溫度": format_temperature_value(slot.get("apparent_temp")),
                "降雨機率": format_percentage(slot.get("pop")),
                "舒適度": slot.get("comfort") or "—",
            }
        )
    return pd.DataFrame(rows)


def render_slot_card(slot: Dict[str, Any]) -> str:
    icon = resolve_icon(slot)
    start = format_time(slot.get("startTime"))
    end = format_time(slot.get("endTime"))
    weather = slot.get("weather") or "—"
    temp_range = format_temp_range(slot.get("min_temp"), slot.get("max_temp"))
    pop = format_percentage(slot.get("pop"))
    apparent = format_temperature_value(slot.get("apparent_temp"))
    return f"""
    <div class="weather-card">
        <div style="font-size:0.9rem;color:var(--dashboard-muted, #475569);">{start} – {end or '—'}</div>
        <div style="font-size:2rem;line-height:1;margin:0.2rem 0;">{icon}</div>
        <div style="font-weight:600;font-size:1.1rem;">{weather}</div>
        <div style="margin-top:0.3rem;">溫度：{temp_range}</div>
        <div>體感：{apparent}</div>
        <div>降雨機率：{pop}</div>
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

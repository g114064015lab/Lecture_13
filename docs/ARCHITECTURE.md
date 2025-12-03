# 架構與資料流說明

此文件整理 Streamlit 儀表板的技術面向：資料來源、程式模組、UI 組件、快取策略與部署流程，協助後續維護與新功能開發。

## 1. 系統概觀
1. 使用者開啟 Streamlit 頁面後，`app.py` 會載入 `.env`，檢查必填的 `CWA_API_KEY`。
2. 呼叫 `load_forecast_data`（包裝於 `st.cache_data`）從中央氣象署 REST API 抓取 JSON。
3. 將原始資料轉換為 `location -> timeline` 的結構，供卡片、指標與視覺化元件共用。
4. 左欄提供縣市列表與搜尋功能，右欄顯示詳情（指標、卡片、折線圖、表格）。

## 2. 模組分工
| 區塊 | 函式/模組 | 說明 |
| --- | --- | --- |
| 入口 | `main()` | 初始化頁面、處理佈局與互動按鈕。 |
| 主題設定 | `initialize_theme_state`, `apply_theme` | 控制深/淺色模式、CSS 變數。 |
| 資料快取 | `load_forecast_data` | 封裝資料抓取 + 正規化；TTL 15 分鐘。 |
| API 呼叫 | `fetch_forecast` | 向 `https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001` 發送 GET 請求。 |
| 正規化 | `normalize_locations`, `parse_location`, `build_timeline` | 將氣象元素（MinT、MaxT、Wx、PoP...）組成統一時間軸。 |
| UI：左欄 | `render_location_selector` | 搜尋、單選、概覽表格。 |
| UI：右欄 | `render_location_details` | 指標卡、時段卡、Altair 圖、詳細表格。 |
| 視覺化 | `build_chart_dataframe` 等 | 將時間序列轉成 Pandas DataFrame。 |

## 3. API 欄位對應
- `Wx` / `WeatherDescription` → 天氣描述與現象碼（搭配 `WEATHER_ICON_MAP`）。
- `PoP` / `PoP12h` → 降雨機率（採整數百分比）。
- `MinT` / `MaxT` → 12 小時時段的最低/最高溫度。
- `AT` / `ApparentT` → 體感溫度。
- `CI` → 舒適度指標文字。
- `startTime` / `endTime` → 每個時段的起迄時間（36 小時含 3 個時段）。

若 API 變更欄位，只需在 `build_timeline` 中調整候選名稱或解析邏輯即可。

## 4. UI 與互動
1. **頂部列**：標題、主題切換、資料更新時間、重新整理按鈕。
2. **縣市列表**：`st.radio` + `st.dataframe` 呈現，支援模糊搜尋與預設地區 (`CWA_DEFAULT_LOCATION`)。
3. **指標卡**：採 `st.metric` 顯示平均溫度、體感溫度、降雨機率、舒適度。
4. **時段卡**：以自訂 HTML/CSS 呈現圖示、溫度區間與降雨機率。
5. **折線圖**：使用 Altair 繪製平均溫度 vs 體感溫度；支援 Tooltip。
6. **詳細表格**：列出 36 小時內所有欄位，方便導出或比對。

## 5. 快取與錯誤處理
- `CACHE_TTL_SECONDS = 900`：減少 API 呼叫，同時保證資料不會太舊。
- 使用者按下「重新整理資料」會呼叫 `load_forecast_data.clear()` 重置快取。
- HTTP 錯誤、授權失敗或 JSON 結構異常時會以 `st.error` 顯示訊息並停止執行，避免畫面殘缺。

## 6. 部署指引
### 本地開發
1. 建立虛擬環境，安裝 `requirements.txt`。
2. 將 `.env`（或系統環境變數）設定 `CWA_API_KEY`、`CWA_DEFAULT_LOCATION`。
3. `streamlit run app.py`。

### Streamlit Community Cloud
1. Fork/Push 此專案到 GitHub。
2. 於 Streamlit Cloud 建立 app，指向 `app.py`。
3. 在「Secrets」設定 `CWA_API_KEY` 與可選的 `CWA_DEFAULT_LOCATION`。
4. 如需自動更新，可搭配 GitHub Actions 或手動重新部署。

### 其他雲端（Docker / VM）
1. 以 `python:3.11-slim` 建 Docker 映像並安裝 requirements。
2. 對外開放 `streamlit` 預設的 `8501` port，或配合反向代理（Nginx）。
3. 重要機密建議透過 Docker secrets 或環境變數注入。

## 7. 後續擴充建議
- 加入更多資料集（例如觀測站或警特報）並整合於相同 UI。
- 支援地圖視覺化（`pydeck` 或 `leafmap`）呈現各地預報。
- 允許使用者切換時區或顯示英文版文字。
- 將快取改為 Redis / SQLite，以備多實例部署。

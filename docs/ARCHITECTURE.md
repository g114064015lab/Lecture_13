# 架構與資料流說明

此文件整理 Streamlit 儀表板的技術面向：資料來源、程式模組、UI 組件、快取策略與部署流程，協助後續維護與新功能開發。

## 1. 系統概觀
1. 使用者開啟 Streamlit 頁面後，`app.py` 會載入 `.env`，確認 `CWA_API_KEY`（預設為官方提供之測試金鑰）。
2. `load_forecast_data`（加上 `st.cache_data`）呼叫中央氣象署 F-A0021-001 REST API（`.../api/v1/rest/datastore/F-A0021-001?format=JSON`）。
3. 每次回傳都完整儲存到 SQLite `data.db`，之後解析為 `location -> 36hr timeline` 結構供卡片與圖表使用。
4. 左欄提供縣市列表與搜尋，右欄顯示 36 小時預報的指標、卡片、折線圖與資料表。

## 2. 模組分工
| 區塊 | 函式/模組 | 說明 |
| --- | --- | --- |
| 入口 | `main()` | 初始化頁面、處理佈局與互動按鈕。 |
| 主題設定 | `initialize_theme_state`, `apply_theme` | 控制深/淺色模式、CSS 變數。 |
| 資料快取 | `load_forecast_data`, `retrieve_payload` | 管理 API 呼叫＋SQLite 快取＋15 分鐘解析快取。 |
| API 呼叫 | `fetch_forecast` | 向 `https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001` 發送 GET 請求。 |
| 正規化 | `normalize_locations`, `build_timeline` | 將 `weatherElement` 內的 `Wx`, `PoP`, `MinT`, `MaxT`, `AT`, `CI` 等欄位合併為統一時段。 |
| UI：左欄 | `render_location_selector` | 搜尋、單選、概覽表格。 |
| UI：右欄 | `render_location_details` | 指標卡、時段卡、Altair 圖、詳細表格。 |
| 視覺化 | `build_chart_dataframe` 等 | 將時間序列轉成 Pandas DataFrame。 |

## 3. API 欄位對應
- `weatherElement -> elementName = Wx`：每 12 小時天氣描述與現象碼（搭配 `WEATHER_ICON_MAP`）。
- `weatherElement -> elementName = PoP/PoP12h`：降雨機率（%）。
- `weatherElement -> elementName = MinT/MaxT`：最低／最高溫度（°C）。
- `weatherElement -> elementName = AT/ApparentT`：體感溫度（°C）。
- `weatherElement -> elementName = CI`：舒適度指標文字。
- `time.startTime`, `time.endTime`：各時段起訖時間（36 小時共 3 筆）。

若 API 結構調整，只需於 `build_timeline` 或欄位對應處調整即可。

## 4. UI 與互動
1. **頂部列**：標題、主題切換、資料發布時間、資料來源提示（即時／快取）、重新整理按鈕。
2. **縣市列表**：`st.radio` + `st.dataframe` 呈現，支援模糊搜尋與預設縣市 (`CWA_DEFAULT_LOCATION`)。
3. **指標卡**：以 `st.metric` 顯示平均溫度、體感溫度、降雨機率、舒適度。
4. **36 小時卡片**：自訂 HTML 呈現圖示、溫度範圍、體感溫度、降雨機率。
5. **折線圖**：Altair 折線圖比較平均溫度與體感溫度的時間序列。
6. **詳細表格**：列出每段時區的起訖時間、天氣、溫度範圍、體感溫度與舒適度。

## 5. 快取與錯誤處理
- `CACHE_TTL_SECONDS = 900`：Streamlit 端減少重複解析。
- SQLite `forecast_cache` 保留每次呼叫的完整 JSON，可離線重新載入或除錯。
- 若即時 API 失敗，會自動載入資料庫最新一筆並顯示提醒。
- 使用者按下「重新整理資料」會 `load_forecast_data.clear()`，迫使重新抓取。

## 6. 部署指引
### 本地開發
1. 建立虛擬環境，安裝 `requirements.txt`。
2. 設定 `.env`（或環境變數）`CWA_API_KEY`、`CWA_DEFAULT_LOCATION`（預設 `臺北市`）。
3. `streamlit run app.py`，即會在專案根目錄產生 `data.db`，可用 `sqlite3 data.db` 檢視快取。

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

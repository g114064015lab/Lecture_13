# OpenSpec：資料流與備援設計

## 1. 目標
- 提供 CWA F-A0021-001 資料的 36 小時預報視覺化，並在 API 或網路不可用時仍能展示內容。

## 2. 資料來源與優先序
1) **Live API**：`https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001?Authorization={API_KEY}&format=JSON`
2) **SQLite 快取**：`data.db` 的 `forecast_cache`（每次成功呼叫後完整儲存 JSON）
3) **內建樣本**：`F-A0021-001.json`（專案根目錄，官方提供範例）

> 快取 TTL：15 分鐘（`st.cache_data`）；即使 cache 過期，資料庫快照仍可使用。

## 3. 安全與網路
- **TLS 驗證**：`CWA_STRICT_SSL`（預設 false）。false 時 `verify=False`，避免缺少 SKI 的憑證阻斷；true 時使用 `certifi` 驗證。
- **金鑰管理**：`CWA_API_KEY` 預設 `CWA-FE3705DB-3102-48DE-B396-30F5D45306C2`，可於 `.env` 或環境變數覆寫。

## 4. 模組行為
- `fetch_forecast`：呼叫 API，失敗則拋出，交由 `retrieve_payload` 決策。
- `retrieve_payload`：依序嘗試 Live → SQLite → Sample，並標記 `source`（live/cache/sample）與 `notice`（錯誤訊息）。
- `persist_payload`：將完整 JSON 寫入 `forecast_cache`（欄位：dataset、payload、fetched_at）。
- `normalize_locations`：先嘗試 weather `records.location`，若無資料則解析 `TideForecasts`（潮汐）。
- `build_timeline`：對 weather 組合 Wx/PoP/MinT/MaxT/AT/CI；對 tide 轉換潮高為公尺、設定潮汐強度指標。

## 5. UI 規格
- **縣市/地區**：`selectbox` + 資料表（地區、天氣、指標值、指標%）。
- **指標卡**：
  - Weather：平均溫度、體感溫度、降雨機率、舒適度
  - Tide：平均/最大/最小潮高、潮汐強度
- **卡片**：依類型顯示溫度或潮高、體感/平均潮高、降雨或潮汐指標。
- **圖表**：Altair 折線圖；Weather → 平均溫度 vs 體感溫度；Tide → 平均潮高 vs 最大潮高。
- **表格**：時間/描述/指標值/補充；Weather 額外顯示體感/降雨，Tide 顯示潮汐強度%。
- **狀態提示**：顯示資料來源（live/cache/sample），若 API 失敗則警告。

## 6. 部署與檔案
- 主要檔案：`app.py`, `requirements.txt`, `data.db`, `F-A0021-001.json`, `README.md`, `docs/ARCHITECTURE.md`, `docs/CONVERSATION_LOG.md`.
- 部署：`streamlit run app.py`；或於 Streamlit Cloud 設定 Secrets（`CWA_API_KEY`, `CWA_DEFAULT_LOCATION`, `CWA_STRICT_SSL`）。

## 7. 既知限制
- CWA 憑證鏈可能缺少 SKI，需允許非嚴格驗證才能在部分環境運作。
- 內建樣本為潮汐資料（非氣象），故 UI 會自動切換為潮汐模式；若需純天氣示例，需另行提供符合 `records.location` 結構的 JSON。

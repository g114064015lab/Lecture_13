# 臺灣36小時天氣預報儀表板（Streamlit）

- Streamlit：https://lecture13-aimfjpyesmq5enlwh5cdgz.streamlit.app/
- 以中央氣象署開放資料集 [F-A0021-001 三十六小時天氣預報](https://opendata.cwa.gov.tw/dataset/forecast/F-A0021-001) 為基礎，參考官方 [OBS_Temp](https://www.cwa.gov.tw/V8/C/W/OBS_Temp.html) 的呈現方式，打造一個具備快取、離線備援的本機 Streamlit 儀表板，可視覺化全臺各地未來 36 小時的溫度、降雨機率與體感指標。

## 資料來源與參考
- 觀摩網頁：<https://www.cwa.gov.tw/V8/C/W/OBS_Temp.html>
- 氣象資料平台登入：<https://opendata.cwa.gov.tw/userLogin>
- API 來源：<https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001?Authorization=CWA-FE3705DB-3102-48DE-B396-30F5D45306C2&format=JSON>
- 專案預設金鑰：`CWA-FE3705DB-3102-48DE-B396-30F5D45306C2`（可於 `.env` 覆寫）。

## 功能亮點
- 串接中央氣象署 REST API，解析各縣市的三時段（12 小時）預報資訊。
- 以互動式側欄列出所有縣市，點選後顯示詳細天氣指標與時序圖。
- 顯示資料更新時間並提供手動重新整理按鈕；背景自動快取 15 分鐘以減少 API 呼叫。
- 內建錯誤提示與空資料處理，確保非預期狀況下仍能提供使用回饋。
- 可自訂 API 金鑰與預設顯示縣市。
- 每次呼叫自動寫入 SQLite `data.db`，API 失敗時仍可顯示最後快照。

## 環境需求
- Python 3.9+
- pip

## 安裝與執行
1. 取得中央氣象署開放資料平臺 API 金鑰。
2. 於專案根目錄建立 `.env` 檔或於系統環境變數設定（若未設定則會使用預設金鑰 `CWA-FE3705DB-3102-48DE-B396-30F5D45306C2`）：
   ```
   CWA_API_KEY=你的金鑰
   ```
3. 安裝依賴：
   ```bash
   pip install -r requirements.txt
   ```
4. 啟動服務：
   ```bash
   streamlit run app.py
   ```

## 專案結構
```
├─app.py               # Streamlit 主程式：資料抓取、視覺化、互動控制
├─requirements.txt     # Python 依賴
├─data.db              # SQLite 快取（執行後自動建立）
├─F-A0021-001.json     # 官方示例資料（API/快取皆無法使用時的備援）
├─README.md            # 使用與部署說明
└─docs
   └─ARCHITECTURE.md   # 深入技術文件：模組、資料流與部署筆記
```

## 指令介面說明
- **縣市列表**：側欄列出所有地區，顯示當前時段的溫度與降雨機率，支援搜尋與預設縣市切換。
- **主要區塊**：顯示選取地區的平均溫度、體感溫度、降雨機率與舒適度指標。
- **36 小時卡片**：以卡片形式呈現每 12 小時時段的天氣描述、溫度區間與降雨機率。
- **時序視覺化**：使用折線圖比較平均溫度與體感溫度。
- **詳細表格**：列出各時段的起訖時間、天氣、溫度、體感溫度與舒適度。
- **全臺概覽**：臺灣地圖概覽以顏色分級呈現潮汐/溫度指標，並附圖例。

## 資料流程與快取策略
1. 以 `CWA_API_KEY` 向 F-A0021-001 REST API 發送請求 (`.../api/v1/rest/datastore/F-A0021-001?format=JSON`)。
2. 將完整 JSON 儲存於 SQLite `data.db` 的 `forecast_cache`，保留歷史快照。
3. 解析結果再由 `st.cache_data` 快取 15 分鐘，減少重複處理。
4. 若 API 失敗，UI 會自動切換至資料庫最新快照並顯示警示訊息。
5. 可利用下列指令檢視快照：
   ```bash
   sqlite3 data.db "SELECT dataset, fetched_at FROM forecast_cache ORDER BY id DESC LIMIT 5;"
   ```
6. 若 API 與 SQLite 快取皆不可用，系統會載入專案根目錄的 `F-A0021-001.json` 作為預設示例預覽，確保畫面仍能展示內容。

## UI/UX 重點
- H1 標題搭配資料發布時間與「重新整理資料」按鈕。
- 內建淺色／深色模式切換，偏好存於 `st.session_state`。
- 36 小時卡片搭配折線圖呈現平均與體感溫度趨勢。
- 明確顯示資料來源（即時或 SQLite 快取）與錯誤提示。

## 設定
| 環境變數 | 預設 | 說明 |
| --- | --- | --- |
| `CWA_API_KEY` | CWA-FE3705DB-3102-48DE-B396-30F5D45306C2 | 預設使用此金鑰，可自行於 `.env` 覆寫 |
| `CWA_DEFAULT_LOCATION` | 臺北市 | 選擇頁面載入時預設顯示的縣市 |
| `CWA_STRICT_SSL` | false | 設為 `true` 可強制使用 CA 驗證；若因憑證缺少 SKI 導致 SSL 失敗，可維持預設 `false` 來忽略驗證 |

## 開發提示
- `app.py` 為主要入口，整合資料抓取、快取與 UI 邏輯，可依需求拆分模組。
- 若需部署到雲端（如 Streamlit Community Cloud），請將 `CWA_API_KEY` 及其他機密值放於 `secrets.toml` 或專案設定中的 Secrets。
- 進一步的資料欄位對應、快取策略與部署建議可參考 `docs/ARCHITECTURE.md`。


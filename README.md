# 臺灣農業一週氣象儀表板（Streamlit）

以中央氣象署開放資料集 [F-A0010-001 一週農業氣象預報](https://opendata.cwa.gov.tw/dataset/forecast/F-A0010-001) 為基礎，結合官方觀測頁面 [OBS_Temp](https://www.cwa.gov.tw/V8/C/W/OBS_Temp.html) 的資訊呈現概念，打造可以在本機 Streamlit 介面檢視各地區未來 7 日天氣與溫度走勢的儀表板。

## 資料來源與參考
- 觀摩網頁：<https://www.cwa.gov.tw/V8/C/W/OBS_Temp.html>
- 氣象資料平台登入：<https://opendata.cwa.gov.tw/userLogin>
- API 來源：<https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/F-A0010-001?Authorization=CWA-1FFDDAEC-161F-46A3-BE71-93C32C52829F&downloadType=WEB&format=JSON>
- 若需其他授權金鑰，可於氣象資料平台註冊後自行建立；專案預設值為 `CWA-1FFDDAEC-161F-46A3-BE71-93C32C52829F`，亦可於 `.env` 覆寫。

## 功能亮點
- 串接中央氣象署 REST API，解析各縣市的三時段（12 小時）預報資訊。
- 以互動式側欄列出所有縣市，點選後顯示詳細天氣指標與時序圖。
- 顯示資料更新時間並提供手動重新整理按鈕；背景自動快取 15 分鐘以減少 API 呼叫。
- 內建錯誤提示與空資料處理，確保非預期狀況下仍能提供使用回饋。
- 可自訂 API 金鑰與預設顯示縣市。

## 環境需求
- Python 3.9+
- pip

## 安裝與執行
1. 取得中央氣象署開放資料平臺 API 金鑰。
2. 於專案根目錄建立 `.env` 檔或於系統環境變數設定（若未設定則會使用預設金鑰 `CWA-1FFDDAEC-161F-46A3-BE71-93C32C52829F`）：
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
├─README.md            # 使用與部署說明
└─docs
   └─ARCHITECTURE.md   # 深入技術文件：模組、資料流與部署筆記
```

## 指令介面說明
- **縣市列表**：側欄列出所有縣市，包含當前時段的溫度與天氣描述。支援搜尋與排序。
- **主要區塊**：顯示選定縣市的最新溫度、體感溫度、降雨機率以及文字化天氣概述。
- **時序視覺化**：使用折線圖呈現 36 小時內的溫度與體感溫度變化；下方表格列出各時段的降雨機率與天氣描述。
- **資料更新**：畫面上方顯示資料取得時間；按下重新整理按鈕可立即呼叫 API。

## 資料流程與快取策略
1. 以 `CWA_API_KEY` 向 F-A0010-001 檔案 API (`downloadType=WEB&format=JSON`) 發送請求。
2. 回傳資料完整儲存於 SQLite `data.db` 的 `forecast_cache` 資料表，方便離線查閱。
3. UI 解析儲存的 JSON，轉成 `地區 -> 日期` 的資料結構，用於卡片、表格與折線圖。
4. `st.cache_data` 再快取 15 分鐘的解析結果；若 API 失敗則自動 fallback 至資料庫最新資料並顯示提示。
5. 若需擷取畫面或驗證資料，可直接查看 `data.db`，例如：
   ```bash
   sqlite3 data.db "SELECT dataset, fetched_at FROM forecast_cache ORDER BY id DESC LIMIT 5;"
   ```

## UI/UX 重點
- H1 標題搭配資料發布時間、天氣概況與「重新整理資料」按鈕。
- 內建淺色／深色模式切換，偏好存於 `st.session_state`。
- 日別預報卡片與折線圖呈現 7 日的最高／最低／平均溫度。
- 表格提供日期、天氣描述與高低溫，方便比對或截圖備查。

## 設定
| 環境變數 | 預設 | 說明 |
| --- | --- | --- |
| `CWA_API_KEY` | CWA-1FFDDAEC-161F-46A3-BE71-93C32C52829F | 預設使用此金鑰，可自行於 `.env` 覆寫 |
| `CWA_DEFAULT_LOCATION` | 北部地區 | 選擇頁面載入時預設顯示的區域 |

## 開發提示
- `app.py` 為主要入口，整合資料抓取、快取與 UI 邏輯，可依需求拆分模組。
- 若需部署到雲端（如 Streamlit Community Cloud），請將 `CWA_API_KEY` 及其他機密值放於 `secrets.toml` 或專案設定中的 Secrets。
- 進一步的資料欄位對應、快取策略與部署建議可參考 `docs/ARCHITECTURE.md`。

## 授權
此專案以 MIT License 發佈。使用時請遵守中央氣象署開放資料使用規範。

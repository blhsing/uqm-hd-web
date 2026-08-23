# 來源、修改與致謝

本倉庫是《The Ur-Quan Masters HD Beta 1》的非官方繁體中文本地化版本，與
Toys for Bob、原始著作權人、The Ur-Quan Masters 專案、UQM-HD 專案及
SourceForge 均無從屬、贊助或背書關係。名稱與商標屬各自權利人所有。

## 上游作品與本地化

- 原始遊戲由 Toys for Bob 製作；程式、文字、圖像、音樂、語音及其他素材的
  著作權歸 Toys for Bob 或各自創作者所有。
- 感謝 The Ur-Quan Masters 與 UQM-HD 歷年貢獻者保存、移植及改良本作。
- 繁體中文翻譯由 OpenAI Codex 語言模型重新翻譯，保留在
  `localization/records.llm-zh-TW.json`、最終工作區及稽核紀錄中。它已通過格式、
  資源契約與封裝驗證，但尚未經完整母語人工校訂及全流程人工通關。
- 選單背景與船艦圖片是上游遊戲內容的本地化或擷取版本，依
  CC BY-NC-SA 2.5 提供，不得作商業用途。
- Noto Sans TC 用於產生繁中字形；相關字型軟體依 SIL OFL 1.1 授權。

## 來源建置的執行環境與程式修改

本網頁版以 Marti Raudsepp 維護的 `intgr/uqm-wasm` Emscripten 移植工作為基礎，
再套用至 UQM-HD Beta 1 及本專案的繁中來源樹。網頁專屬修改位於 `engine/wasm/`、
`app/`、`server/` 與 `scripts/`，包括 WebAssembly 建置、IndexedDB 存檔、雙語
啟動器、觸控按鈕、跨畫面返回、瀏覽器網路超級對戰配對中繼及 Azure 虛擬應用
部署。WebSocket 中繼使用 MIT 授權的 `ws` 套件，其授權檔會隨 Azure 建置輸出
一併部署。

大型原版內容、音樂、語音、高解析度圖像及產生後的繁中 `.uqm` 套件不放入 Git
歷史；建置者需合法取得 UQM-HD Beta 1 內容。正式非商業部署重用相同來源內容，
並遵循其 CC BY-NC-SA 2.5 條款。

以下段落保留本網頁版所沿用之 Windows 繁中桌面版的來源與稽核歷史。

v0.3.2 的首選 Windows x86 執行環境由本倉庫中的 UQM-HD 原始碼建置，不再只靠
修改官方執行檔。相對於官方 Beta 1，發行版的程式變更包括：

1. 主選單目前項目採明亮黃色脈衝，並支援滑鼠停駐與點選。
2. SDL 輸入層提供執行緒安全的邏輯畫布滑鼠座標；移動滑鼠會顯示游標，按鍵或
   按下滑鼠鍵會隱藏游標。
3. Super Melee 的隊伍設定、船艦格、右側控制、船艦總覽與開戰前選船均支援
   滑鼠。停駐或鍵盤選取船艦時會顯示船員、能量、費用、極速、加速、轉向、
   回能與武器／特殊能力消耗。
4. Super Melee 選船器兩側的 `PICK SHIP`／`SHIP INFO` 區域可直接點選，行為
   分別等同 `Enter`／`Alt`；船艦資料頁的可視範圍內任意左鍵點擊皆會返回選船
   器。點擊世代與去彈跳狀態只在船艦資料頁啟用及消耗，不會洩漏到其他畫面。
5. 本機 Super Melee 對戰中，實體 `Esc` 只結束目前一局並回到隊伍設定，不
   改變劇情戰鬥及 `CHECK_ABORT` 語義；開戰前選船的 `Esc` 則與紅色 X 共用
   確認返回流程。
6. 玩家一特殊能力保留右 `Shift` 與數字鍵盤 `0`，並增加右 `Alt` 作為第三個
   綁定。

v0.3.2 的船艦資料頁產生器會從相鄰面板取樣 `CREW`／`BATT` 的替換背景，把
「船員／能量」固定在量表下方，且保留量表、右側分隔線及底部分隔線的每個原始
像素。README 的船艦圖鑑以單一、不折疊的表格比較 25 艘 Super Melee 船艦，
各項數值分欄顯示；戰役專用的先驅者旗艦則另設圖文介紹。

相關來源分布於 `engine/src/uqm/restart.c`、`engine/src/uqm/battle.c`、
`engine/src/uqm/supermelee/` 與 `engine/src/libs/` 的輸入／SDL 圖形層；不是只有
兩個 C 檔。`engine/build/msvc6/UrQuanMasters.vcproj` 的上游開發者絕對資源
路徑亦改為可重現的相對路徑；未使用的個人設定及二進位 JAR 沒有納入倉庫。

v0.3.2 發行壓縮檔包含 GPL-2.0-or-later 的來源建置 `uqm-hd.exe`、其 19 個
執行階段 DLL，以及對應授權文件；安裝時執行檔會映射成 `uqm.exe`。它**不包含
上游遊戲的原始內容**，使用者仍須自行提供官方 Beta 1 的已解壓內容樹。每個
DLL 的實際授權與來源套件由 `runtime-manifest.json` 及隨附 `LICENSES/` 精確
記錄。

若未提供來源建置的 runtime，安裝器才會使用相容模式：依序在目的地副本套用
四項雜湊鎖定 PE 補丁（黃色選取、對戰中 `Esc`、玩家一 RightAlt、選船
`Esc`）。補丁工具會同時檢查已知 SHA-256、唯一指令特徵、固定檔案位移及 PE
checksum；未知版本一律拒絕。此相容路徑不含來源版的完整滑鼠與船艦資料功能。

## 可重現來源與發行雜湊

| 項目 | SHA-256 |
|---|---|
| 官方 UQM-HD Beta 1 原始碼壓縮檔 | `9a94cce18e039a0447a758abed52e72694b279279d7a7eea19a93dfe667f0e73` |
| 官方 Windows Beta 1 安裝程式 | `17ba52347dde55c3103bdaf566c1511e88d509ad7eb50eda60e4f2912f108bde` |
| 官方 `hires4x.zip` | `76af440bd845a63bd42b88913347374eb62c40c149d0bea37045a10bd0bd6618` |
| 官方未修改 `uqm.exe` | `c43c258aa41c4effe5d092c8541560a517cdd7be91e3c576a10a4ad306f776d3` |
| v0.3.2 來源建置 `uqm-hd.exe`（3,022,388 bytes） | `6f33a1b73a38ce5e4a7045a67a5f520eaaa15a8c16eaa8f169d0cff5ecc2364f` |
| v0.3.2 `runtime-manifest.json`（27,388 bytes） | `478bfc840a080977ca65fa366502b04d57d4e473405a93504e7c4c0a5bd58f5c` |
| `zh_TW.uqm`（22,455,949 bytes） | `1a1b2bd13d6c8e1a8475c16a15c706602d62b7cab1a20fe395c9b931aa707942` |
| `hires2x-zh_TW.uqm`（42,596,373 bytes） | `edef271c9034827bfab29e37c1d37b568ecc779285adc6b5d7730abd5cb1f098` |
| `hires4x-zh_TW.uqm`（64,579,231 bytes） | `03f8491bdf5e84251a305dd73d52e353ac66efee717a9b336f3d152dc38c5749` |

runtime 取自來源 commit
`7981479c611b60af041d05ec01a40791eb993f51` 的乾淨 1,043 檔桌面引擎
樹。其 manifest 驗證 20 個 PE32 payload、27 份授權文件與零個未解析的非系統
匯入。最終 59 項自動化測試及 17 項安裝驗證均通過；完整建置流程見
`docs/BUILD-WINDOWS.md`。

完整授權文本與上游歸屬見 `LICENSE`、`LICENSES/UPSTREAM-COPYING.txt`、
`LICENSES/OFL-1.1-NotoSansCJK.txt`、`engine/COPYING` 及個別來源檔頭。

# Windows x86 執行環境建置與稽核

本文件說明如何由本儲存庫的 `game/` 原始碼建置 UQM-HD 的 32 位元 Windows
執行檔，遞迴收集實際需要的 DLL，附上授權文字，並產生可交給安裝器與發行封裝器
驗證的 `runtime-manifest.json`。

## 已驗證的工具鏈

建置配方使用可攜式 MSYS2 的 `MINGW32` 環境，不使用主機上的 Visual Studio、
全域 GCC 或任意 PATH 內容。這次實際驗證的 bootstrap 檔案如下；檔案不收進 Git：

| 項目 | 值 |
|---|---|
| 檔名 | `msys2-base-x86_64-20260611.sfx.exe` |
| 大小 | `52,898,952` bytes |
| SHA-256 | `c105946e64e08f099ac0e4647461ce762b95333ad211777666476a9a41451d65` |
| 驗證日期 | 2026-08-19 |

bootstrap 使用固定日期檔名與 SHA-256；完整環境另由以下檔案鎖定：

- `tools/build/windows-x86/msys2-packages.lock`：完整 `pacman -Q` 套件與版本。
- `tools/build/windows-x86/msys2-explicit-packages.lock`：完整 `pacman -Qqe` 明確安裝集合。
- `tools/build/windows-x86/toolchain-bootstrap.json`：bootstrap 檔名、大小、來源與 hash。
- `tools/build/windows-x86/runtime-packages.json`：DLL 與套件、授權來源的固定對應。

配方會先比對完整套件鎖；任何缺件或版本差異都會停止。預設連額外套件也不允許，
以避免未記錄的工具覆蓋 PATH。`-AllowAdditionalPackages` 只適合本機除錯，正式發行
不應使用。

若需日後離線重建，應連同上述 bootstrap 以及該次
`var/cache/pacman/pkg/*.pkg.tar.zst` 保存於可信任的成品保存區。MSYS2 是 rolling
release；鎖檔能偵測差異，但無法保證舊套件永遠留在公開鏡像。配方刻意不自動執行
`pacman -Syu` 或下載套件，避免「重建」悄悄換成不同編譯器。

這個環境最初使用的明確安裝集合是：

```text
make pkgconf mingw-w64-i686-gcc mingw-w64-i686-pkgconf
mingw-w64-i686-SDL mingw-w64-i686-SDL_image
mingw-w64-i686-libogg mingw-w64-i686-libvorbis
mingw-w64-i686-zlib mingw-w64-i686-ntldd
```

請以鎖檔中的完整版本為準，而不是直接在新的 rolling 鏡像執行上述名稱清單。

## 正式建置命令

請從儲存庫根目錄執行。`WorkDir` 與 `OutputDir` 必須不存在或是空目錄；配方不會
替使用者遞迴刪除舊目錄。路徑可自行更換，但不要放在 `game/` 之下。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\build\Build-WindowsX86Runtime.ps1 `
  -Msys2Root C:\Tools\msys64 `
  -WorkDir C:\build\uqm-hd-win32 `
  -OutputDir C:\build\uqm-hd-win32-runtime `
  -RequireCleanSource
```

`-RequireCleanSource` 會在 `game/` 有修改、刪除或未追蹤檔案時停止，應固定用於
公開發行。配方實際執行的上游命令是：

```sh
./build.sh uqm reprocess_config
./build.sh uqm depend
./build.sh uqm
```

第一個命令讀取已納入版控的 `tools/build/windows-x86/config.state`，不開互動式選單。
目前固定為 release、OpenGL、內建 MixSDL 音效、Xiph Vorbis、完整 netplay、joystick、
ZIP I/O、x86 asm 加速與 SDL thread。`BUILD_WORK` 必須使用 `C:/...` mixed path；配方
會自行透過 `cygpath` 產生，避免舊建置系統把 `/c/...` 誤解。上游原始碼需要的
`svnversion` 也由已納入版控的固定 wrapper 提供，產生 revision `1347M`。

舊版 configure 會逐項編譯小型 probe，數分鐘沒有新主控台輸出並不代表當機；不要用
一分鐘的外層 timeout 終止正式建置。若必須中止，應同時確認沒有遺留該次 work path
的 `bash`／`sh` 子程序，再換一個空 `WorkDir` 重跑。

配方把 Git commit time 設為 `SOURCE_DATE_EPOCH`。建置完成後，它會確認 `game/`
指紋未在建置期間改變，再將所有成品檔案時間正規化為同一時間。

## 原始碼指紋與 provenance

配方對 `game/` 底下每一個 regular file（包括未追蹤但實際存在的輸入）計算 SHA-256，
以 `StringComparer.Ordinal` 排序相對路徑，再雜湊以下 UTF-8、LF-only 資料：

```text
<小寫檔案 SHA-256><兩個空白><使用 / 的 game/ 相對路徑>\n
```

`runtime-manifest.json` 會記錄：

- 完整 40 位 Git commit；
- `clean` 或 `dirty` 的真實 `game/` 狀態；
- 檔案數、輸入樹指紋與算法；
- 編譯器套件版本、release flags 與套件鎖 SHA-256。

若 `game/` 確實乾淨，manifest 會寫 `sourceTreeState: "clean"`，不會因儲存庫其他區域
有 README 或封裝變更而誤標 dirty。若允許開發中建置，它會如實寫 `dirty`，而輸入樹
指紋仍精確描述實際檔案。manifest 只使用 `game`、`mingw32/bin/...` 等相對 provenance；
輸出前另有檢查，禁止寫入 `C:/...` 這類主機絕對路徑。

## DLL 閉包、PE 與授權檢查

建置後不是使用手寫 DLL 清單直接複製。配方會從 `uqm-hd.exe` 開始，以 pinned
`objdump -p` 遞迴讀取每一層 import：

1. 每個 EXE/DLL 必須是 `pei-i386` 且 PE optional-header magic 必須是 `010b`
   （PE32，不是 PE32+）。
2. Windows 系統 DLL 只能來自 `runtime-packages.json` 的固定 allowlist。
3. 其他 import 必須能在 `mingw32/bin` 找到、列在固定 DLL-to-package 對應內，且
   該套件的本機 pacman `files` 資料庫確實宣告擁有該檔。
4. 新找到的 DLL 會繼續被檢查，直到閉包完整；任何未解析非系統 import 都會失敗。

manifest 會保存完整 import graph、每個 payload 的大小與 SHA-256，並宣告
`unresolvedNonSystemImports: 0`。目前驗證閉包共有 20 個 payload：一個 EXE 加
19 個 DLL；OpenAL 雖存在於建置環境，因目前 MixSDL 成品沒有 import 它，所以不會
被多餘地封裝。

每個實際使用的 DLL 套件會把 MSYS2 安裝的授權目錄複製到
`LICENSES/<package>/`。MSYS2 的 SDL 1.2 與 libvorbis binary packages 沒有安裝授權
檔，因此其上游授權文字已固定收在 `tools/build/windows-x86/licenses/`；UQM-HD
本身使用 `game/COPYING`。manifest 中的 `licenseFiles` 只引用已存在的相對檔案。

輸出根目錄只會有 payload、`runtime-manifest.json` 與 `LICENSES/`；不會把建置時的
`stdout.txt`、`stderr.txt` 或工作目錄資料帶進發行包。

## 驗證與發行封裝

成功後可先用專案的 runtime loader 驗證，再交給發行封裝器：

```powershell
C:\path\to\python.exe .\scripts\build_release.py `
  --packs-dir C:\build\localized-packs `
  --runtime-dir C:\build\uqm-hd-win32-runtime `
  --output C:\build\uqm-hd-zh-tw-v0.5.0.zip `
  --version 0.5.0
```

`scripts/build_release.py` 會再次驗證 manifest schema、每個 EXE/DLL 的大小與 hash、
全部引用的授權檔，以及沒有未列入 manifest 的額外 binary。

如只想稽核既有 EXE，可省略 `WorkDir` 並使用：

```powershell
.\tools\build\Build-WindowsX86Runtime.ps1 `
  -Msys2Root C:\Tools\msys64 `
  -ExecutablePath C:\build\existing\uqm-hd.exe `
  -OutputDir C:\build\audit-runtime
```

這條路徑會在 provenance 明確寫入 `caller-supplied-executable` 及
`buildPerformedByRecipe: false`。它能驗證 PE、DLL、授權與封裝格式，卻不能證明 EXE
就是由當前 source tree 編譯，因此不得拿來製作正式公開發行。

## 可重現性的界線

- 套件鎖、非互動設定、`SOURCE_DATE_EPOCH`、排序、LF/UTF-8 manifest、相同 mtime、
  import 閉包及 license staging 都是確定性的。
- 這是舊式自製 build system；不同 Windows/MSYS2/NTFS 實作仍可能令 linker output
  不同。故本配方不宣稱跨主機必然 byte-for-byte 相同，而是讓每次輸入與成品 hash
  都可稽核。
- 本配方只建置 `windows-x86` runtime，不包含原版遊戲內容或繁中 `.uqm` packs。
- 不可用 64 位元 DLL 取代閉包中的 32 位元 DLL；PE 檢查會拒絕架構混用。

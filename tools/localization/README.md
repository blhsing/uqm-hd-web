# UQM HD Traditional-Chinese localization pipeline

This directory contains the content-only localization pipeline used for the
**The Ur-Quan Masters HD Beta 1** v0.4.1 Traditional-Chinese release. It does not
call a translation API and does not modify the game installation. It exports
protected JSON, merges translated `{id,text}` records, handles the engine's
unusual text formats, generates bitmap glyphs from Noto Sans TC, and builds
one self-contained 4x `.uqm` add-on. The separate source-built Windows runtime is
documented in `../../docs/BUILD-WINDOWS.md`.

## Requirements

- Python 3.10 or newer.
- The extracted Beta 1 `content` directory, including `base`, `uqm.rmp`, and the
  stock `content/addons/hires2x.zip`, `hires4x.zip`, and `3dovoice.zip` packages.
- `NotoSansTC-VF.ttf`. This host provides it at
  `C:\Windows\Fonts\NotoSansTC-VF.ttf`.
- Pillow for TTF rasterization:

```powershell
python -m pip install -r .\tools\localization\requirements.txt
```

Before redistributing generated fonts, preserve and review the SIL Open Font
License for Noto Sans TC. Do not substitute a Microsoft system font for a
redistributable package unless its license explicitly permits that use.

## Complete workflow

The examples assume the extracted game is in this repository's `staging`
directory. Output paths must be new or empty so a typo cannot overwrite an
existing translation.

### 1. Export protected entry JSON

```powershell
python .\tools\localization\uqm_localize.py export `
  --content-root .\staging\UQM-HD\content `
  --output .\translation-workspace
```

This exports all 104 `STRTAB`/`CONVERSATION` resources referenced by `uqm.rmp`
and recursively discovers the three scripts called by the ending wrapper. On
the verified Beta 1 content this is 107 documents and 6,806 engine entries.

Each `resources/**/*.json` entry contains immutable label/audio/template fields
and an editable `translation` field. Only edit `translation`. The manifest's
contract hashes deliberately reject changed labels, audio tokens, entry order,
script commands, timing, paths, or source templates.

### 2. Make a flat translation-service bundle

```powershell
python .\tools\localization\uqm_localize.py bundle `
  --workspace .\translation-workspace `
  --output .\zh-TW-source.jsonl `
  --jsonl
```

The verified source yields 5,177 translatable `{id,text}` records. Immutable
slideshow commands and other control records are omitted. Send only `text` for
translation and preserve each `id` exactly.

Merge a complete returned array (`.json`) or JSONL response:

```powershell
python .\tools\localization\uqm_localize.py merge `
  --workspace .\translation-workspace `
  --response .\zh-TW-response.jsonl `
  --output .\translation-workspace-zh-TW
```

By default every exported ID must be returned exactly once. Use
`--allow-partial` only for an intentional batch, and then merge into the same
working copy with `--in-place` for subsequent batches.

### 3. Add safe Chinese break opportunities

UQM HD's dialogue wrapper recognizes only ASCII spaces and hard newlines. A
normal unspaced Chinese sentence can therefore make the engine's wrapping loop
stop making progress. This command adds conservative ASCII break spaces to CJK
tokens and hard-wraps physical UTF-8 lines below the parser limit:

```powershell
python .\tools\localization\uqm_localize.py wrap `
  --workspace .\translation-workspace-zh-TW `
  --in-place `
  --max-cjk-token 12 `
  --max-line-bytes 900
```

Dialogue is wrapped by default. `--all-text` also modifies non-dialogue payloads
and should only be used after visual review. Human translators can get better
typography by inserting semantic ASCII break spaces themselves; the validator
only requires that no CJK engine word exceed the selected limit.

### 4. Validate and optionally materialize text files

```powershell
python .\tools\localization\uqm_localize.py validate `
  --workspace .\translation-workspace-zh-TW

python .\tools\localization\uqm_localize.py import `
  --workspace .\translation-workspace-zh-TW `
  --output .\translated-text-preview
```

Validation checks, among other things:

- UTF-8 without a BOM, no NUL/CR, and no code point above `U+FFFF`;
- at most 2,048 entries and at most 1,023 encoded bytes per physical line;
- exact entry order, labels, original header whitespace, and audio clip tokens;
- balanced/preserved `$` font-switch marker counts used by Orz dialogue;
- setup-menu list cardinality and credits column limits;
- lossless reparse of every rendered text file;
- immutable slideshow commands, timing, animation paths, and font paths.

The intro and ending/final files are command scripts disguised as string tables.
Only the visible payload following `TFI` is exported for translation. `DIMS`,
`FONT*`, `ANI*`, `CALL`, `SYNC`, `WAIT`, and every other command remain protected.
Called ending scripts are installed through `shadow-content`, so their literal
`CALL base/...` paths do not need to be rewritten.

### 5. Build the 4x package

```powershell
python .\tools\localization\uqm_localize.py build `
  --content-root .\staging\UQM-HD\content `
  --workspace .\translation-workspace-zh-TW `
  --output .\localized-build `
  --font C:\Windows\Fonts\NotoSansTC-VF.ttf `
  --menu-background .\localization\menu-assets\source\newgame4x-clean-imagegen.png
```

The result is:

```text
localized-build/packages/hires4x-zh_TW.uqm
```

The finalized v0.4.1 content artifact is unchanged from v0.4.0:

| Pack | Bytes | SHA-256 |
| --- | ---: | --- |
| `hires4x-zh_TW.uqm` | 91,567,383 | `b535d19283cf4afdb4482fc517eeef247c53ab6f5bb53b78996470ad035bd7e2` |

The v0.4.1 release reuses the audited Windows runtime first shipped in v0.3.2:

| Runtime file | Bytes | SHA-256 |
| --- | ---: | --- |
| `runtime/windows-x86/uqm-hd.exe` | 3,022,388 | `6f33a1b73a38ce5e4a7045a67a5f520eaaa15a8c16eaa8f169d0cff5ecc2364f` |
| `runtime/windows-x86/runtime-manifest.json` | 27,388 | `478bfc840a080977ca65fa366502b04d57d4e473405a93504e7c4c0a5bd58f5c` |

The resource maps are generated from the installed official maps, not copied
from the incomplete Japanese pack:

- `hires4x-zh_TW`: 614 stock HD graphics + 104 text + 39 fonts = 757.

Original Latin/punctuation glyphs are copied into every mapped and directly
loaded cutscene font directory. A shadow-mounted `.fon` directory replaces the
stock resource instead of merging with it, so omitting the original glyphs can
leave presentations on a blank frame.
Only the Traditional-Chinese subsets needed by each font role are rasterized.
The generator explicitly selects Noto Sans TC Medium/500 and renders every Han
glyph at four times its final dimensions before a Lanczos downsample. This
preserves fine strokes and open counters while removing only the sub-visible
ringing that UQM would otherwise count as bitmap ink. Generic HD UI fonts receive
engine-safe Han canvases, while other fonts continue to use the source font's
observed capital-letter metrics. It emits lowercase,
five-digit Unicode filenames such as `04e00.png`. Directly loaded cutscene fonts
are augmented using `shadow-content`, which keeps their script paths immutable.

The five main-menu choices are baked into animation PNGs rather than string
tables. The build therefore creates the localized `newgame4x` frame set inside
a nested archive placed in the add-on's
`shadow-content` directory (UQM mounts nested `.uqm`/`.zip` archives there, not
loose files). A clean 4:3 menu background supplies the artwork; the exact labels
`新遊戲`, `載入遊戲`, `超級對戰`, `設定`, and `離開` are rendered deterministically
with Noto Sans TC Medium/500 and no synthetic outline.

The Super Melee setup screen is another 39-frame baked animation. Text-free 4x
templates under `localization/menu-assets/source/super-melee/` preserve the
upstream nebula, metal controls, portraits, and selection lighting. The builder
generates localized 4x title, control-mode, network, save/load, battle,
and quit frames, while retaining the stock animation manifest and hotspots.
Those clean templates can be reproduced from the upstream Translation Pack
PSDs when `psd-tools` is installed:

```powershell
python .\tools\localization\extract_super_melee_sources.py `
  --translation-pack 'C:\path\to\Translation Pack' `
  --output .\localization\menu-assets\source\super-melee
```

The combat `CREW`/`BATT` sprites are also generated as `船員`/`能量`. Each
4x uses a fixed optical size and 350/16 px weight so dense Han strokes remain
separated. The generated RGBA/RGB-key
pair blends into the stock gray status panel during normal rendering, retains
a glyph-only alpha mask for the low-energy recolor, and confines label removal
to half-open regions that do not overwrite gauges, dividers, or separators.

The Super Melee ship-picker panel is rebuilt with `選擇船艦` and `船艦資料`.
The source-built runtime makes both labels clickable and lets a left click
anywhere inside the visible viewport dismiss a ship-information presentation. All 25 ship-information presentations
are generated deterministically from reviewable Traditional-Chinese source data
at native 1280x960 resolution. Their localized cards
cover crew, battery, cost, movement, weapons, special abilities, and tactics
while preserving upstream ship artwork and animation manifests. The top-level
Traditional-Chinese player guide compares the 25 Super Melee craft in a single
uncollapsed, per-stat-column table and introduces the campaign flagship separately.

Packages use only ZIP Deflate, disable ZIP64, reject 65,535 or more files, and
are written deterministically. The single package contains all translated
resources, fonts, and shadow-mounted image assets without cross-add-on references. Each
pack's mounted shadow archive contains 5,357 normal entries and no padding
entry; package QA compares every generated entry byte-for-byte.

## Install and launch

Copy `hires4x-zh_TW.uqm` to the game's `content\addons` directory:

```powershell
# 1280x960 content
uqm.exe -x -r 1280x960 -w --resfactor=2 --addon hires4x-zh_TW

# Recommended legible fullscreen profile for a 1920x1080 display
uqm.exe -o -r 1920x1080 -f -k -c none --resfactor=2 --addon hires4x-zh_TW
```

## Scope and visual QA

This pipeline localizes engine text, bitmap glyph coverage, the five baked
main-menu choices, the visible Super Melee setup controls, ship picker, all 25
ship-information pages, and combat status labels. The repository's preferred source-built runtime separately implements
the yellow menu selection, main-menu and Super Melee mouse controls, cursor
visibility switching, detailed vessel-stat cards, picker and in-bout Escape
handling, and Player 1's additional RightAlt special-ability binding. The v0.4.1
release bundles that GPL runtime and its dependency licenses, but does not
bundle the upstream game's original content. A polished localization still
benefits from a full playthrough. In particular, visually check the intro/final
subtitles, credits, setup menu, every alien conversation font, the 21 lander
reports copied into each high-resolution tree, save/load screens, and name
entry.

## Tests

```powershell
python -m unittest discover `
  -s .\tools\localization\tests `
  -v
```

The finalized v0.4.1 tree passes all 60 automated tests.

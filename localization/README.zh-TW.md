# UQM-HD Traditional Chinese localization

This workspace contains the v0.5.0 Traditional Chinese (`zh-TW`) localization of
The Ur-Quan Masters HD Beta 1, finalized on 2026-08-19.

## Translation provenance

- The shipped translation was authored by OpenAI Codex as an LLM translation.
- It covers all 5,177 translatable records exported from 107 resource documents
  (6,806 engine entries in total).
- The source and translated record sets are `records.en.json` and
  `records.llm-zh-TW.json`.
- A previously interrupted Google Translate experiment was quarantined in a
  local `machine-translation.backup` directory and is intentionally not
  published; none of it was merged into the shipped packs.
- Proper names and recurring lore terminology were normalized through
  `glossary.zh_TW.json`.

This is an LLM-authored localization, not a professional human translation.
The structural and automated linguistic checks pass, but a native-speaker
editor may still wish to polish tone or word choice.

## Built add-on packs

| Pack | Bytes | SHA-256 |
| --- | ---: | --- |
| `native1080-zh_TW.uqm` | 189,687,374 | `f24d1f55e326fe20bb577c53eb12836ecff71af7a8b34ea2520537ec4ef1aef2` |

The self-contained native-1080p archive passed ZIP integrity and exact
resource-mapping audits. The
merged workspace passed UTF-8, engine-line-length, wrapping, CJK glyph, record
identity, protected-token, and placeholder checks.

Every override was compared byte-for-byte with its generated shadow tree after
the nested-archive refresh. The eight
direct cutscene fonts contain both the generated Traditional-Chinese subset and
all 95–100 original glyphs from the corresponding stock font; package QA
explicitly checks space, digits, uppercase/lowercase Latin, and `一` before
installation.

## Legibility and menu artwork

- In-game Chinese glyphs are rasterized from `NotoSansTC-VF.ttf` at explicit
  optical sizes and weights onto a 2560x1920 logical canvas. The canvas is
  bilinearly supersampled to the 1440x1080 4:3 viewport on this host, avoiding
  the blocky nearest-neighbor output of the retired 4x tier. Direct cutscene fonts retain every
  original Latin/punctuation glyph because a shadow-mounted `.fon` directory
  replaces, rather than merges with, the stock resource.
- Native UI font cells and metrics are doubled from the prior 4x artwork before
  GPU downsampling. Tiny and StarCon bounds deliberately match the SIS HUD's
  fixed text bands and font gradients, preventing Chinese rows from being
  clipped while retaining open counters and readable strokes.
- The five baked main-menu choices are localized as `新遊戲`, `載入遊戲`,
  `超級對戰`, `設定`, and `離開`. Unselected choices are steady light gray;
  the selected choice now remains yellow through a positive-only additive
  pulse, so it never crosses through the unselected gray or the stock red.
  These labels use Medium/500 without a synthetic outline; the heavier
  Bold/700 setting remains limited to the smaller in-game bitmap fonts.
- The preferred v0.5 Windows runtime is built from the checked-in source. Its
  `restart.c` menu pulse is `3..6/16`; physical `Escape` ends only an active
  local Super Melee bout, while campaign combat and `CHECK_ABORT` semantics are
  unchanged. `Escape` also follows the red-X confirmation path in the
  pre-battle vessel picker. Player 1 keeps Right Shift and keypad `0` for the
  special ability and gains Right Alt as a third binding.
- The main menu, Super Melee team setup, fleet slots, vessel grid, right-side
  controls, and pre-battle vessel picker accept mouse input. Moving the mouse
  reveals the cursor; a keyboard or mouse-button press hides it. Hovering a
  vessel shows its crew, battery, point cost, top speed, acceleration, turning,
  energy regeneration, and weapon/special costs.
- The Super Melee build picker's rendered `選擇船艦` and `船艦資料` action labels
  are directly clickable: the first confirms the current vessel and the second
  opens its full-screen information page. Pressing Enter or Escape, or left-clicking
  anywhere inside the visible page viewport, returns to the picker.
- If a custom runtime is unavailable, the compatibility installer can instead
  apply exactly four hash-, offset-, signature-, and PE-checksum-gated patches
  to the supported upstream PE32 executable: menu highlight, in-bout Escape,
  Player 1 RightAlt, and pre-battle picker Escape. Unknown binaries are refused.
- A permanent main-menu hint documents `↑`/`↓` navigation and `Enter` to
  confirm. The native starmap key-help panel documents the old-map/constellation,
  zoom, and star-search bindings in full Traditional Chinese.
- The PC-style combat HUD bitmaps show the full `船員` and `能量` labels in the
  native tier without changing stock frame hotspots or crossing HUD clip
  boundaries. Status-label weight is 350, so the small Han counters remain open;
  the RGB/alpha encoding restores the stock gray panel during normal rendering
  while retaining a glyph-only mask for the low-energy recoloring effect.
- The Super Melee build picker localizes `PICK SHIP` and `SHIP INFO` as
  `選擇船艦` and `船艦資料`. All 25 ship-information presentations are rebuilt
  at 2560x1920 with Traditional-Chinese names,
  movement statistics, weapons, special abilities, and tactics. English-style
  abbreviated ship-table fields reuse the full Han name so they cannot end in
  a misleading full stop.
- On those ship-information pages, the replacement `船員` and `能量` captions
  blend into the stock gray panel. Their redraw boxes preserve the gauges,
  vertical dividers, and lower separators in the native tier.
- The top-level README compares the 25 Super Melee vessels in one uncollapsed
  table with individually separated statistics. The campaign-only Precursor
  Flagship has its own illustrated section below the table.
- OpenAI's built-in image editor was used only to remove the five baked English
  labels while preserving the 4:3 space/panel composition. The edit prompt was:
  "Remove only the New Game, Load Game, Super Melee!, Setup, and Quit labels;
  preserve the scene, panel, composition, and crop, and add no replacement
  text." Exact Chinese text was then rendered deterministically by the build,
  rather than generated inside the image model.
- The clean source artwork is
  `menu-assets/source/newgame4x-clean-imagegen.png`. Visual QA renders are under
  `qa/font-legibility-contact-sheet.png` and
  `qa/native1080-main-menu.png`, `qa/native1080-super-melee.png`, and the
  `qa/key-help-*-preview.png` renders.

## Host installation

- Game: `C:\Games\UQM-HD-TW`
- Isolated profile and saves: `%APPDATA%\UQM-HD-zh_TW`
- Default and only supported visual mode: native-1080p OpenGL fullscreen
  (`native1080-zh_TW`) at 1920x1080, using a 2560x1920 supersampled canvas,
  bilinear downsampling, and a centered 1440x1080 4:3 viewport

The installed marker, every managed file hash, the native pack, two fullscreen
shortcuts, and a hidden runtime smoke test are covered by the verifier. The
smoke log must confirm `native1080-zh_TW`, resolution factor 3, bilinear scaling,
and a 1920x1080 fullscreen surface with no fatal diagnostic. Visible runtime
passes additionally confirmed the always-yellow selection,
the `新遊戲` transition into the opening sequence instead of a stalled black
screen, localized opening credits, and the `船員`/`能量` Super Melee combat HUD.
Live input QA also confirmed that Right Alt activates Player 1's special ability
and that the picker Escape confirmation returns to team setup. The 1x, 2x, and
4x launch tiers are intentionally absent from this release.

## Source-built Windows runtime

The v0.5.0 release bundles the updated GPL source-built Windows x86 runtime and
includes its exact dependency licenses. It does **not** include the upstream game's original
content; users must provide an extracted official Beta 1 tree. The manifest
closes over every PE32 payload, stages the corresponding license files, and records
zero unresolved non-system imports. See `../docs/BUILD-WINDOWS.md` for the
pinned MSYS2 recipe and provenance checks.

| Runtime artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `uqm-hd.exe` | 3,013,822 | `7b80cd4c741371b98776784e91a0971920e28382443a459174d88cbf69596c5c` |
| `runtime-manifest.json` | 27,388 | `737c044b8b4d82f5a563833e9152b027792e06145eb58804ed2bc9f3cc18dcac` |

Shortcut filenames use ASCII because this host's legacy Windows shortcut API
cannot reliably create Unicode paths. This does not affect the Traditional
Chinese game UI or content.

## Upstream and licenses

The base game was obtained from the official
[UQM-HD SourceForge project](https://sourceforge.net/projects/urquanmastershd/).
See upstream's [COPYING file](https://sourceforge.net/p/urquanmastershd/git-new/ci/master/tree/COPYING)
for the game code and content licenses. Bundled Noto CJK font files are covered
by the SIL Open Font License; a copy is stored in
`../LICENSES/OFL-1.1-NotoSansCJK.txt`.

from __future__ import annotations

import argparse
from pathlib import Path


CONTROL_LAYERS = ("HUMAN", "WEAK", "GOOD", "AWESOME", "Network")


def _load_psd(path: Path):
    try:
        from psd_tools import PSDImage  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "PSD source extraction requires psd-tools: python -m pip install psd-tools"
        ) from exc
    return PSDImage.open(path)


def _hide_translation_groups(psd) -> None:
    for layer in psd:
        if layer.name in {"English", "Russian"}:
            layer.visible = False


def extract_sources(translation_pack: Path, output: Path, *, force: bool) -> None:
    sources = {
        "background-4x.png": translation_pack / "meleemenu-000.psd",
        "battle-4x.png": translation_pack / "meleemenu-025.psd",
    }
    required = [*sources.values(), translation_pack / "melee-cyborg-human.psd"]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing upstream PSD source: " + str(missing[0]))
    expected = [*sources, *(
        f"{name.lower()}-{state}-4x.png"
        for name in CONTROL_LAYERS
        for state in ("normal", "selected")
    )]
    existing = [output / name for name in expected if (output / name).exists()]
    if existing and not force:
        raise FileExistsError(
            f"refusing to overwrite {existing[0]}; pass --force to replace all outputs"
        )
    output.mkdir(parents=True, exist_ok=True)

    for name, path in sources.items():
        psd = _load_psd(path)
        _hide_translation_groups(psd)
        image = psd.composite(force=True)
        # psd-tools synthesizes an ICC profile with volatile header bytes.
        # The clean templates only need RGBA pixels, so omit that metadata to
        # make repeated extractions byte-for-byte reproducible.
        image.info.clear()
        image.save(output / name, format="PNG", optimize=True)
        image.close()

    controls = translation_pack / "melee-cyborg-human.psd"
    for selected in (False, True):
        for control in CONTROL_LAYERS:
            psd = _load_psd(controls)
            _hide_translation_groups(psd)
            for layer in psd:
                if layer.name == "UNLIT BG":
                    layer.visible = not selected
                if layer.name.startswith("UNLIT-") or layer.name.startswith("LIT-"):
                    layer.visible = False
            target = ("LIT-" if selected else "UNLIT-") + control
            matches = [layer for layer in psd if layer.name == target]
            if len(matches) != 1:
                raise ValueError(f"expected one PSD layer named {target!r}")
            matches[0].visible = True
            image = psd.composite(force=True)
            image.info.clear()
            state = "selected" if selected else "normal"
            name = f"{control.lower()}-{state}-4x.png"
            image.save(output / name, format="PNG", optimize=True)
            image.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract text-free 4x Super Melee PNG templates from upstream PSDs."
    )
    parser.add_argument("--translation-pack", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    extract_sources(
        args.translation_pack.resolve(), args.output.resolve(), force=args.force
    )
    print(f"wrote {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

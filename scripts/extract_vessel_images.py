from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import tempfile
import zipfile


HIRES4X_SHA256 = "76af440bd845a63bd42b88913347374eb62c40c149d0bea37045a10bd0bd6618"


VESSELS = {
    "precursor-flagship.png": "hires4x/ships/flagship/flagship-big-000.png",
    "androsynth-guardian.png": "hires4x/ships/androsynth/guardian-big-000.png",
    "arilou-skiff.png": "hires4x/ships/arilou/skiff-big-000.png",
    "chenjesu-broodhome.png": "hires4x/ships/chenjesu/broodhome-big-000.png",
    "chmmr-avatar.png": "hires4x/ships/chmmr/avatar-big-000.png",
    "druuge-mauler.png": "hires4x/ships/druuge/mauler-big-000.png",
    "earthling-cruiser.png": "hires4x/ships/human/cruiser-big-000.png",
    "ilwrath-avenger.png": "hires4x/ships/ilwrath/avenger-big-000.png",
    "kohr-ah-marauder.png": "hires4x/ships/kohrah/marauder-big-000.png",
    "melnorme-trader.png": "hires4x/ships/melnorme/trader-big-000.png",
    "mmrnmhrm-x-form.png": "hires4x/ships/mmrnmhrm/xform-big-000.png",
    "mycon-podship.png": "hires4x/ships/mycon/podship-big-000.png",
    "orz-nemesis.png": "hires4x/ships/orz/nemesis-big-000.png",
    "pkunk-fury.png": "hires4x/ships/pkunk/fury-big-000.png",
    "shofixti-scout.png": "hires4x/ships/shofixti/scout-big-000.png",
    "slylandro-probe.png": "hires4x/ships/slylandro/probe-big-000.png",
    "spathi-eluder.png": "hires4x/ships/spathi/eluder-big-000.png",
    "supox-blade.png": "hires4x/ships/supox/blade-big-000.png",
    "syreen-penetrator.png": "hires4x/ships/syreen/penetrator-big-000.png",
    "thraddash-torch.png": "hires4x/ships/thraddash/torch-big-000.png",
    "umgah-drone.png": "hires4x/ships/umgah/drone-big-000.png",
    "ur-quan-dreadnought.png": "hires4x/ships/urquan/dreadnought-big-000.png",
    "utwig-jugger.png": "hires4x/ships/utwig/jugger-big-000.png",
    "vux-intruder.png": "hires4x/ships/vux/intruder-big-000.png",
    "yehat-terminator.png": "hires4x/ships/yehat/terminator-big-000.png",
    "zoq-fot-pik-stinger.png": "hires4x/ships/zoqfotpik/stinger-big-000.png",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract(source: Path, output: Path, *, force: bool) -> None:
    actual_hash = sha256_file(source)
    if actual_hash != HIRES4X_SHA256:
        raise ValueError(
            "refusing unverified hires4x archive: "
            f"expected {HIRES4X_SHA256}, got {actual_hash}"
        )
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        missing = sorted(set(VESSELS.values()) - set(archive.namelist()))
        if missing:
            raise ValueError(f"missing expected HD vessel entries: {missing}")
        for filename, member in VESSELS.items():
            destination = output / filename
            if destination.exists() and not force:
                raise FileExistsError(f"refusing to overwrite {destination}")
            payload = archive.read(member)
            if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError(f"archive member is not PNG: {member}")
            with tempfile.NamedTemporaryFile(
                prefix=f".{filename}.", suffix=".tmp", dir=output, delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(payload)
            temporary_path.replace(destination)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract the campaign flagship and 25 Super Melee vessel frames."
    )
    parser.add_argument("hires_zip", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    extract(args.hires_zip.resolve(), args.output.resolve(), force=args.force)
    print(f"extracted {len(VESSELS)} vessel images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

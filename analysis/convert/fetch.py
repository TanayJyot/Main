"""Download only the clips needed for the pilot glosses.

Neither dataset is downloaded whole:

  ASL Citizen  one 42.8 GB zip on download.microsoft.com. The server honours
               HTTP Range, so remotezip reads the central directory and pulls
               individual mp4s (~0.5 MB each).
  PopSign v1.0 1.1 TB, served as one uncompressed tar per
               category/split/sign. Only non-game/{train,val} is used (the
               deliberate recordings, not in-game attempts), and from those
               only one clip per signer, read out of the tar with Range
               requests.

Which labels to fetch per pilot gloss comes from labels.py (the mapping
table, narrowed to exact matches where they exist). All variants of an
allowed label are fetched; select.py records which one won.

Research use only (ASL Citizen: MSR licence; PopSign: CC BY 4.0). Everything
lands in data/, which is gitignored. Re-running skips what is already there.

Usage:
    python fetch.py [--aslc] [--popsign]      (default: both)
    python fetch.py --popsign-all --max-signers 6
"""

from __future__ import annotations

import argparse
import csv
import math
import tarfile
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from labels import candidate_labels

HERE = Path(__file__).parent
DATA = HERE / "data"

ASLC_URL = "https://download.microsoft.com/download/b/8/8/b88c0bae-e6c1-43e1-8726-98cf5af36ca4/ASL_Citizen.zip"
POPSIGN_URL = "https://signdata.cc.gatech.edu/data/popsign_v1_0/non-game/{split}/{sign}.tar"


def aslc_rows() -> list[dict]:
    """Split CSVs, fetched once from the zip."""
    out = DATA / "aslc"
    out.mkdir(parents=True, exist_ok=True)
    names = ["train.csv", "val.csv", "test.csv", "use.txt"]
    if not all((out / n).exists() for n in names):
        from remotezip import RemoteZip
        with RemoteZip(ASLC_URL, support_suffix_range=False) as z:
            for n in names:
                member = f"ASL_Citizen/{n}" if n == "use.txt" else f"ASL_Citizen/splits/{n}"
                (out / n).write_bytes(z.read(member))
    rows = []
    for split in ["train", "val", "test"]:
        with open(out / f"{split}.csv", encoding="utf8") as f:
            for r in csv.DictReader(f):
                r["split"] = split
                rows.append(r)
    return rows


def fetch_aslc(labels: set[str], workers: int = 8) -> None:
    rows = [r for r in aslc_rows() if r["Gloss"] in labels]
    videos = DATA / "aslc" / "videos"
    videos.mkdir(parents=True, exist_ok=True)
    todo = [r["Video file"] for r in rows if not (videos / r["Video file"]).exists()]
    print(f"ASL Citizen: {len(rows)} clips for {len(labels)} labels, {len(todo)} to fetch")

    from remotezip import RemoteZip

    def worker(chunk: list[str]) -> int:
        # One RemoteZip per thread: each holds its own HTTP session and the
        # parsed central directory.
        z = retry(lambda: RemoteZip(ASLC_URL, support_suffix_range=False))
        for i, name in enumerate(chunk):
            tmp = videos / (name + ".part")
            tmp.write_bytes(retry(lambda: z.read(f"ASL_Citizen/videos/{name}")))
            tmp.replace(videos / name)
            if i % 100 == 0:
                print(f"  {name}", flush=True)
        z.close()
        return len(chunk)

    chunks = [todo[i::workers] for i in range(workers)]
    with ThreadPoolExecutor(workers) as pool:
        done = sum(pool.map(worker, [c for c in chunks if c]))
    print(f"ASL Citizen: fetched {done}")


def retry(fn, attempts: int = 6):
    """Call fn(), retrying with backoff: long runs over a laptop connection
    drop mid-read (IncompleteRead) every few thousand requests."""
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - re-raised on the last attempt
            if getattr(e, "code", None) == 404 or attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)


def _range(url: str, start: int, length: int) -> bytes:
    def once() -> bytes:
        req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{start + length - 1}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            if r.status != 206:
                raise IOError(f"{url}: expected 206, got {r.status}")
            return r.read()
    return retry(once)


def tar_members(url: str) -> list[tuple[str, int, int]]:
    """(name, data offset, size) for every file in a remote, uncompressed tar,
    read header by header with Range requests instead of downloading it."""
    members, off = [], 0
    while True:
        block = _range(url, off, 512)
        if not any(block):  # two zero blocks end a tar
            return members
        info = tarfile.TarInfo.frombuf(block, "utf-8", "surrogateescape")
        if info.type in (tarfile.REGTYPE, tarfile.AREGTYPE):
            members.append((info.name, off + 512, info.size))
        off += 512 + math.ceil(info.size / 512) * 512


def signer(name: str) -> str:
    # 4a.8053-on-2023_01_28_19_29_39.608-0.mp4 -> 4a.8053
    return Path(name).name.split("-")[0].removeprefix("gtsignstudy")


def fetch_popsign(signs: list[str], per_signer: int = 1, max_signers: int = 12) -> None:
    """PopSign's full non-game tars for these glosses total ~19 GB. Instead,
    list each tar remotely and pull the first clip (by filename) per signer,
    up to max_signers signers per gloss: ~1.5 GB. The rule never looks at clip
    content, so it cannot bias selection."""
    print(f"PopSign: {len(signs)} labels, <= {max_signers} signers each")

    def one(sign: str) -> None:
        dest = DATA / "popsign" / sign
        if (dest / ".done").exists():
            return
        dest.mkdir(parents=True, exist_ok=True)
        by_signer: dict[str, list] = defaultdict(list)
        for split in ["train", "val"]:
            if len(by_signer) >= max_signers:
                break  # train alone already has enough signers
            url = POPSIGN_URL.format(split=split, sign=sign)
            try:
                members = tar_members(url)
            except Exception as e:  # noqa: BLE001 - a missing split is normal
                print(f"  {split}/{sign}: {e}")
                continue
            for name, off, size in members:
                if name.endswith(".mp4"):
                    by_signer[signer(name)].append((name, url, off, size))
        chosen = [sorted(v)[:per_signer] for _, v in sorted(by_signer.items())][:max_signers]
        for name, url, off, size in (c for group in chosen for c in group):
            out = dest / Path(name).name
            if not out.exists():
                out.write_bytes(_range(url, off, size))
        (dest / ".done").touch()
        print(f"  {sign}: {len(by_signer)} signers, kept {len(chosen)}", flush=True)

    # Labels in parallel: listing a tar is one small request per member, so a
    # single label is latency-bound.
    with ThreadPoolExecutor(16) as pool:
        list(pool.map(one, signs))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aslc", action="store_true")
    ap.add_argument("--popsign", action="store_true")
    ap.add_argument("--popsign-all", action="store_true",
                    help="every PopSign label, not just the pilot ones (the PopSign-only prototype)")
    ap.add_argument("--max-signers", type=int, default=12)
    args = ap.parse_args()
    if args.popsign_all:
        glosses = HERE.parent / "coverage" / "popsign_glosses.txt"
        fetch_popsign([l.strip() for l in glosses.read_text(encoding="utf8").splitlines() if l.strip()],
                      max_signers=args.max_signers)
        return
    both = not (args.aslc or args.popsign)
    cands = candidate_labels().values()
    if args.popsign or both:
        fetch_popsign(sorted({l for c in cands for l in c["popsign"]}))
    if args.aslc or both:
        fetch_aslc({l for c in cands for l in c["citizen"]})


if __name__ == "__main__":
    main()

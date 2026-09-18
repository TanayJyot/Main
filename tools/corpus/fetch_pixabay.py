"""
Fetch full-body human photos from Pixabay, recording provenance as it goes.

Pixabay is used because its content licence explicitly permits AI/ML training —
see DATA_LICENSES.md section 4a for why Pexels is excluded and why Unsplash is
only usable through its Lite Dataset.

One honest limitation: the Pixabay API does not expose the per-contributor
AI-training opt-out. Every record is therefore written with
ai_training_optout="unknown" and clean_to_images.py will refuse to build a
training archive from it. Resolving that queue is manual work — see
provenance.check_optout and `--print_optout_queue` below.

    export PIXABAY_API_KEY=...
    python fetch_pixabay.py --output_dir corpus/downloaded \
        --manifest corpus/provenance.jsonl --target 5000
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import Iterator, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from provenance import Manifest, Record, check_optout, now_iso  # noqa: E402

API_URL = "https://pixabay.com/api/"
MAX_PER_PAGE = 200

# Queries chosen to match SHHQ's content: whole people, standing, plain
# backgrounds. filter_candidates.py does the real work; these just bias the
# pool so less is thrown away.
DEFAULT_QUERIES = (
    "full body person standing",
    "full body portrait",
    "person standing white background",
    "full length woman standing",
    "full length man standing",
    "person standing studio",
)


def search(api_key: str, query: str, page: int, per_page: int = MAX_PER_PAGE) -> dict:
    params = {
        "key": api_key,
        "q": query,
        "image_type": "photo",
        "orientation": "vertical",  # SHHQ is 1024x512 portrait crops
        "safesearch": "true",
        "per_page": per_page,
        "page": page,
        "min_width": 800,
        "min_height": 1200,
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        import json
        return json.loads(response.read().decode("utf-8"))


def iter_hits(api_key: str, queries: List[str], target: int, delay: float = 0.5) -> Iterator[dict]:
    """Page through each query until `target` unique hits have been yielded."""
    seen = set()
    yielded = 0
    for query in queries:
        page = 1
        while yielded < target:
            try:
                payload = search(api_key, query, page)
            except Exception as error:  # network, rate limit, malformed page
                print(f"  query {query!r} page {page} failed: {error}")
                break
            hits = payload.get("hits", [])
            if not hits:
                break
            for hit in hits:
                if hit["id"] in seen:
                    continue
                seen.add(hit["id"])
                yielded += 1
                yield hit
                if yielded >= target:
                    return
            page += 1
            time.sleep(delay)  # Pixabay rate-limits; be a good citizen


def download(url: str, destination: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=60) as response, open(destination, "wb") as handle:
            handle.write(response.read())
        return True
    except Exception as error:
        print(f"  download failed {url}: {error}")
        if os.path.exists(destination):
            os.remove(destination)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Pixabay photos with provenance records.")
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--target", type=int, default=5000, help="How many images to fetch")
    parser.add_argument("--queries", nargs="*", default=list(DEFAULT_QUERIES))
    parser.add_argument("--api_key", default=os.environ.get("PIXABAY_API_KEY", ""))
    parser.add_argument("--print_optout_queue", action="store_true",
                        help="Print image ids still needing a manual opt-out check, then exit")
    args = parser.parse_args()

    manifest = Manifest(args.manifest)

    if args.print_optout_queue:
        queue = check_optout(manifest)
        print(f"{len(queue)} image(s) need a contributor opt-out check:")
        for image_id in queue:
            record = manifest.get(image_id)
            print(f"  {image_id}  {record.source_url}")
        return

    if not args.api_key:
        parser.error("set PIXABAY_API_KEY or pass --api_key")

    os.makedirs(args.output_dir, exist_ok=True)
    fetched = 0

    for hit in iter_hits(args.api_key, args.queries, args.target):
        image_id = f"pixabay-{hit['id']}"
        if image_id in manifest:
            continue

        destination = os.path.join(args.output_dir, f"{image_id}.jpg")
        # largeImageURL is the biggest size the free API returns.
        if not download(hit.get("largeImageURL") or hit["webformatURL"], destination):
            continue

        manifest.add(Record(
            image_id=image_id,
            source="pixabay",
            source_url=hit["pageURL"],
            licence="pixabay-content-license",
            retrieved_at=now_iso(),
            author=hit.get("user"),
            ai_training_optout="unknown",
            notes="Opt-out not exposed by the API; confirm on the page before training.",
            extra={"width": hit.get("imageWidth"), "height": hit.get("imageHeight")},
        ))
        fetched += 1
        if fetched % 100 == 0:
            print(f"  {fetched} fetched")

    print(f"fetched {fetched} new images -> {args.output_dir}")
    print(f"manifest now holds {len(manifest)}: {manifest.summary()}")
    pending = check_optout(manifest)
    if pending:
        print(f"\n{len(pending)} image(s) need a manual opt-out check before training.")
        print("Run with --print_optout_queue for the list.")


if __name__ == "__main__":
    main()

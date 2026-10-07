"""Fetch one sign video per word from the dictionary sites that gave ASLytics permission.

    python showcase/fetch_sites.py --list
    python showcase/fetch_sites.py                       # every site with a fetcher, in order
    python showcase/fetch_sites.py --sites signingsavvy --limit 50

Words come from showcase/target_words.txt, most-used first. Each site's videos
land in .work/<site>/videos/ as <word>.mp4, which showcase/video_lexicon.py
turns into a lexicon. Nothing here is committed: each folder carries a
.gitignore of "*".

It is written to be a polite guest:

  - one request a second per site at most (--delay), more if the site's
    robots.txt asks for more, and nothing robots.txt rules out;
  - only the words still missing: Signing Savvy is asked for every word, the
    later sites only for words no earlier source (or --have lexicon) signs;
  - it identifies itself, resumes where it stopped, records each video's page
    in manifest.csv, and gives up on a site that refuses or stops answering.

Each site is first tried on a few common words. If none of them yields a
video, the site's pages have probably changed and it is skipped, not hammered.

Only the Python standard library is needed, plus Pillow and OpenCV (already
installed for MediaPipe) to turn Lifeprint's animated GIFs into video.
"""

from __future__ import annotations

import argparse
import csv
import html as htmllib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sources  # noqa: E402

USER_AGENT = ("ASLytics-lexicon-builder/1.0 (+https://github.com/TanayJyot/Main; "
              "non-commercial sign lexicon, by permission)")
WORD = re.compile(r"^[a-z0-9]+$")
PROBE_WORDS = ["book", "water", "help", "family", "school"]
GIVE_UP_AFTER = 10            # consecutive failed lookups before a site is abandoned


class Blocked(Exception):
    """The site refused us (robots.txt, 401/403, or repeated 429): stop asking."""


# -- HTTP: throttled, robots-aware, retrying ------------------------------------------

class Http:
    def __init__(self, delay: float = 1.0, user_agent: str = USER_AGENT, timeout: float = 30.0,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.delay, self.user_agent, self.timeout = delay, user_agent, timeout
        self.sleep, self.clock = sleep, clock
        self._last: Dict[str, float] = {}
        self._robots: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        self.requests = 0

    def _open(self, url: str) -> Tuple[int, bytes, Dict[str, str]]:
        """One request: (status, body, headers). Network errors raise OSError."""
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, b"", dict(error.headers or {})

    def _wait(self, host: str, delay: float) -> None:
        last = self._last.get(host)
        if last is not None and (remaining := delay - (self.clock() - last)) > 0:
            self.sleep(remaining)
        self._last[host] = self.clock()

    def _rules(self, host: str) -> Optional[urllib.robotparser.RobotFileParser]:
        if host not in self._robots:
            rules: Optional[urllib.robotparser.RobotFileParser] = None
            try:
                self._wait(host, self.delay)
                self.requests += 1
                status, body, _ = self._open(f"https://{host}/robots.txt")
                if status == 200:
                    rules = urllib.robotparser.RobotFileParser()
                    rules.parse(body.decode("utf-8", "replace").splitlines())
                elif status in (401, 403) or status >= 500:
                    raise Blocked(f"{host}: robots.txt answered {status}")
            except OSError:
                rules = None                      # unreachable robots.txt: nothing is ruled out
            self._robots[host] = rules
        return self._robots[host]

    def get(self, url: str) -> Optional[bytes]:
        """The body, or None for 404. Raises Blocked or OSError."""
        host = urllib.parse.urlsplit(url).netloc
        rules = self._rules(host)
        delay = self.delay
        if rules is not None:
            if not rules.can_fetch(self.user_agent, url):
                raise Blocked(f"{host}: robots.txt rules out {urllib.parse.urlsplit(url).path}")
            delay = max(delay, float(rules.crawl_delay(self.user_agent) or 0))
        error: Exception = OSError("no attempt made")
        for attempt in range(4):
            self._wait(host, delay)
            self.requests += 1
            try:
                status, body, headers = self._open(url)
            except OSError as failure:
                error = failure
                self.sleep(2 ** (attempt + 1))
                continue
            if status == 200:
                return body
            if status in (404, 410):
                return None
            if status in (401, 403):
                raise Blocked(f"{host} answered {status} for {url}")
            if status == 429:
                wait = headers.get("Retry-After", "")
                self.sleep(min(300.0, float(wait)) if wait.isdigit() else 30.0 * (attempt + 1))
                error = Blocked(f"{host} keeps answering 429 (too many requests)")
                continue
            error = OSError(f"{host} answered {status} for {url}")
            self.sleep(2 ** (attempt + 1))
        raise error

    def text(self, url: str) -> Optional[str]:
        body = self.get(url)
        return None if body is None else body.decode("utf-8", "replace")


# -- what a lookup returns ---------------------------------------------------------------

@dataclass(frozen=True)
class Found:
    video_url: str
    page_url: str
    note: str = ""
    kind: str = "mp4"          # "mp4", or "gif" (converted to mp4 after download)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


# -- Signing Savvy -------------------------------------------------------------------------
# /search/<word> is either the sign's own page (a <video> with an .mp4) or, for
# a word with several meanings, a list of sign pages "sign/<word>/<id>/1" with
# "(as in ...)" notes. Links are relative to the site root.

SAVVY = "https://www.signingsavvy.com"
_SAVVY_MP4 = re.compile(r'(?:src|href)="([^"]+\.mp4)"')
_SAVVY_ITEM = re.compile(r'<li>\s*<a\s+href="(sign/[^"]+)"[^>]*>([^<]+)</a>(?:\s*<em>(.*?)</em>)?', re.S)
_SAVVY_CURRENT = re.compile(r'<a class="current"[^>]*>(.*?)</a>', re.S)
_SAVVY_HEAD = re.compile(r'class="signing_header">\s*<h2>(.*?)</h2>', re.S)


def savvy_video(page: str) -> Optional[str]:
    """The sign video on a sign page; None if there is none or it is only fingerspelled."""
    current = _SAVVY_CURRENT.search(page)
    if current and "finger" in _clean(current.group(1)).lower():
        return None
    match = _SAVVY_MP4.search(page)
    return urllib.parse.urljoin(SAVVY + "/", match.group(1)) if match else None


_SAVVY_NOT_A_SIGN = re.compile(r'as in "the letter"|fingerspell', re.I)


def savvy_meanings(page: str, word: str) -> List[Tuple[str, str]]:
    """[(sign page URL, "as in" note)] for the entries spelled exactly like the word.

    The letter of the alphabet (I, A) and fingerspelled entries are left out:
    the fingerspelling layer covers those, and they are not the word's sign.
    """
    out = []
    for href, label, note in _SAVVY_ITEM.findall(page):
        note = _clean(note).strip("()")
        if _clean(label).lower() == word and not _SAVVY_NOT_A_SIGN.fullmatch(note):
            out.append((SAVVY + "/" + href.lstrip("/"), note))
    return out


def savvy_lookup(word: str, http: Http, limit: int) -> List[Found]:
    search = f"{SAVVY}/search/{urllib.parse.quote(word)}"
    page = http.text(search)
    if page is None:
        return []
    if video := savvy_video(page):
        head = _SAVVY_HEAD.search(page)
        headword = _clean(head.group(1)).lower() if head else word
        return [Found(video, search, "" if headword == word else f"listed under {headword.upper()}")]
    found = []
    meanings = savvy_meanings(page, word)
    for number, (url, note) in enumerate(meanings[:limit], 1):
        sign = http.text(url)
        if sign and (video := savvy_video(sign)):
            if len(meanings) > 1:                 # for a signer to review: the site's order decided
                note = f"{note}; meaning {number} of {len(meanings)}"
            found.append(Found(video, url, note))
    return found


# -- SpreadTheSign ------------------------------------------------------------------------
# /en.us/search/?q=<word> lists /en.us/word/<id>/<slug>/0/ pages; each has one
# <video src="https://media.spreadthesign.com/video/mp4/...">.

STS = "https://www.spreadthesign.com"
_STS_RESULT = re.compile(r'href="(/en\.us/word/(\d+)/([^/"]+)/\d+/)[^"]*"[^>]*>(.*?)</a>', re.S)
_STS_VIDEO = re.compile(r'<video[^>]*\ssrc="(https://media\.spreadthesign\.com/[^"]+\.mp4)"')


def sts_results(page: str, word: str) -> List[Tuple[str, str]]:
    """[(word page URL, label such as "book Noun")] for entries spelled exactly like the word."""
    out, seen = [], set()
    for path, entry, slug, label in _STS_RESULT.findall(page):
        if slug.lower() == word and entry not in seen:
            seen.add(entry)
            out.append((STS + path, _clean(label)))
    return out


def sts_video(page: str) -> Optional[str]:
    match = _STS_VIDEO.search(page)
    return match.group(1) if match else None


def sts_lookup(word: str, http: Http, limit: int) -> List[Found]:
    page = http.text(f"{STS}/en.us/search/?q={urllib.parse.quote(word)}")
    found = []
    for url, label in sts_results(page or "", word)[:limit]:
        entry = http.text(url)
        if entry and (video := sts_video(entry)):
            found.append(Found(video, url, label))
    return found


# -- ASL Signbank clips on SignASL.org -----------------------------------------------------
# SignASL.org has no signs of its own: /sign/<word> shows other people's
# videos, each under media.signbsl.com/videos/asl/<owner>/mp4/. Only owners
# whose licence or permission covers us are taken. By default that is ASL
# Signbank alone (CC BY-NC-SA 4.0). Its files are named <GLOSS>-<id>.mp4.

SIGNASL = "https://www.signasl.org"
SIGNASL_OWNERS = ("aslsignbank",)
_SIGNASL_VIDEO = re.compile(r'(https://media\.signbsl\.com/videos/asl/([^/"\s]+)/mp4/([^"/\s]+)\.mp4)')
_SIGNBANK_FILE = re.compile(r"^(.*?)-(\d+)$")


def signasl_videos(page: str, word: str, owners: Sequence[str] = SIGNASL_OWNERS) -> List[Tuple[str, str]]:
    """[(video URL, note)] from the allowed owners, exact gloss before numbered variants."""
    ranked, seen = [], set()
    for position, (url, owner, stem) in enumerate(_SIGNASL_VIDEO.findall(page)):
        if owner not in owners or url in seen:
            continue
        seen.add(url)
        if owner == "aslsignbank":
            match = _SIGNBANK_FILE.match(stem)
            gloss = (match.group(1) if match else stem).lower()
            if gloss == word:
                rank = 0
            elif re.fullmatch(re.escape(word) + r"[_-]?\d+", gloss):
                rank = 1
            else:
                continue                              # OPEN-BOOK is not BOOK
            ranked.append((rank, position, url, f"ASL Signbank gloss {gloss.upper()}"))
        else:
            ranked.append((0, position, url, f"from {owner}"))
    return [(url, note) for _, _, url, note in sorted(ranked)]


def signasl_lookup(word: str, http: Http, limit: int,
                   owners: Sequence[str] = SIGNASL_OWNERS) -> List[Found]:
    url = f"{SIGNASL}/sign/{urllib.parse.quote(word)}"
    page = http.text(url)
    return [Found(video, url, note) for video, note in signasl_videos(page or "", word, owners)[:limit]]


# -- Lifeprint / ASL University --------------------------------------------------------------
# The sign pages are listed in /asl101/index/<letter>.htm. Their videos are on
# YouTube, which we do not download from; the animated GIFs kept on
# lifeprint.com itself (gifs/<letter>/<word>.gif) are what we take.

LIFEPRINT = "https://www.lifeprint.com"
_LP_LINK = re.compile(r'href="[^"]*pages-signs/([a-z0-9])/([^"/]+)\.htm"[^>]*>(.*?)</a>', re.S | re.I)
_LP_GIF = re.compile(r'["\'=]([^"\'\s>]*gifs/[a-z0-9]/([^"\'/\s>]+)\.gif)', re.I)


def lifeprint_index(page: str) -> Dict[str, str]:
    """word -> sign page path, from one index page. Cross-references ("see ...") are skipped."""
    out: Dict[str, str] = {}
    for letter, stem, label in _LP_LINK.findall(page):
        label = _clean(label).lower()
        if "[" in label or " see " in f" {label} ":
            continue
        path = f"/asl101/pages-signs/{letter.lower()}/{stem}.htm"
        for name in [part.strip() for part in label.split("/")]:
            if WORD.match(name):
                out.setdefault(name, path)
    return out


def lifeprint_gif(page: str, page_url: str) -> Optional[str]:
    """The page's own sign GIF: <stem>.gif, else <stem>-<n>.gif. Related signs are not taken."""
    stem = page_url.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
    exact = numbered = None
    for path, name in _LP_GIF.findall(page):
        name = name.lower()
        if name == stem and exact is None:
            exact = path
        elif re.fullmatch(re.escape(stem) + r"-\d+", name) and numbered is None:
            numbered = path
    chosen = exact or numbered
    return urllib.parse.urljoin(page_url, chosen) if chosen else None


class Lifeprint:
    def __init__(self) -> None:
        self.index: Optional[Dict[str, str]] = None

    def load_index(self, http: Http) -> Dict[str, str]:
        if self.index is None:
            index: Dict[str, str] = {}
            for letter in "abcdefghijklmnopqrstuvwxyz":
                page = http.text(f"{LIFEPRINT}/asl101/index/{letter}.htm")
                for word, path in lifeprint_index(page or "").items():
                    index.setdefault(word, path)
            self.index = index
        return self.index

    def __call__(self, word: str, http: Http, limit: int) -> List[Found]:
        path = self.load_index(http).get(word)
        if not path:
            return []
        url = LIFEPRINT + path
        page = http.text(url)
        gif = lifeprint_gif(page or "", url)
        return [Found(gif, url, "animated GIF", kind="gif")] if gif else []


LOOKUPS: Dict[str, Callable[[str, Http, int], List[Found]]] = {
    "signingsavvy": savvy_lookup,
    "spreadthesign": sts_lookup,
    "signbank": signasl_lookup,
    "lifeprint": Lifeprint(),
}
FULL_SITES = ("signingsavvy",)      # asked for every word; the rest only fill gaps


# -- saving videos ---------------------------------------------------------------------------

def gif_to_mp4(gif: Path, mp4: Path, min_frames: int = 4, min_height: int = 480) -> bool:
    """Write an animated GIF as an mp4 MediaPipe can read. False if it is a still image."""
    import cv2
    import numpy as np
    from PIL import Image, ImageSequence

    with Image.open(gif) as image:
        frames, durations = [], []
        for frame in ImageSequence.Iterator(image):
            durations.append(frame.info.get("duration", 100) or 100)
            frames.append(np.array(frame.convert("RGB")))
    if len(frames) < min_frames:
        return False
    height, width = frames[0].shape[:2]
    scale = max(1.0, min_height / height)
    size = (int(round(width * scale / 2)) * 2, int(round(height * scale / 2)) * 2)
    fps = min(30.0, max(5.0, 1000.0 / sorted(durations)[len(durations) // 2]))
    part = mp4.with_suffix(".part.mp4")
    writer = cv2.VideoWriter(str(part), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    try:
        for frame in frames:
            writer.write(cv2.resize(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), size,
                                    interpolation=cv2.INTER_CUBIC))
    finally:
        writer.release()
    part.replace(mp4)
    return True


def _looks_like_video(data: bytes, kind: str) -> bool:
    if len(data) < 2000:
        return False
    if kind == "gif":
        return data[:6] in (b"GIF87a", b"GIF89a")
    return data[4:8] in (b"ftyp", b"styp", b"moov", b"free", b"mdat", b"wide")


def save(found: Found, target: Path, http: Http) -> str:
    """Download one video to target (.mp4). Returns "" on success, else why not."""
    data = http.get(found.video_url)
    if data is None:
        return "video missing (404)"
    if not _looks_like_video(data, found.kind):
        return "not a video file"
    target.parent.mkdir(parents=True, exist_ok=True)
    if found.kind == "gif":
        gif = target.with_suffix(".gif")
        gif.write_bytes(data)
        try:
            animated = gif_to_mp4(gif, target)
        finally:
            gif.unlink(missing_ok=True)
        return "" if animated else "still image, not a sign video"
    part = target.with_suffix(".part")
    part.write_bytes(data)
    part.replace(target)
    return ""


# -- one site ------------------------------------------------------------------------------

def read_words(path: Path) -> List[str]:
    words, seen = [], set()
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.strip().lower()
        if word and not word.startswith("#") and WORD.match(word) and word not in seen:
            seen.add(word)
            words.append(word)
    return words


def lexicon_words(folder: Path) -> Set[str]:
    return {p.stem for p in folder.glob("*.pose") if not p.stem.startswith("fs_")}


def video_words(folder: Path) -> Set[str]:
    return {p.stem.split("__")[0] for p in folder.glob("*.mp4")} if folder.is_dir() else set()


def _history(path: Path) -> Dict[str, str]:
    """word -> its last recorded outcome ("ok", "none", "error")."""
    seen: Dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
                seen[entry["word"]] = entry["status"]
            except (ValueError, KeyError):
                continue
    return seen


def fetch_site(key: str, words: Iterable[str], folder: Path, http: Http, variants: int = 1,
               lookup: Optional[Callable[[str, Http, int], List[Found]]] = None,
               log: Callable[[str], None] = print) -> Dict[str, object]:
    """Fetch the given words from one site into folder/videos. Safe to re-run."""
    lookup = lookup or LOOKUPS[key]
    videos = folder / "videos"
    videos.mkdir(parents=True, exist_ok=True)
    (folder / ".gitignore").write_text("*\n", encoding="utf-8")
    history_path, manifest_path = folder / "lookups.jsonl", folder / "manifest.csv"
    history = _history(history_path)
    new_manifest = not manifest_path.exists()

    todo = [w for w in words if history.get(w) not in ("ok", "none")]
    probing = "ok" not in history.values()
    if probing:                                  # no video from this site yet: try common words first
        todo = PROBE_WORDS + [w for w in todo if w not in PROBE_WORDS]
    counts = {"ok": 0, "none": 0, "error": 0}
    stopped, failures, probed = "", 0, 0
    log(f"{key}: {len(todo)} words to look up")

    with open(history_path, "a", encoding="utf-8") as history_file, \
            open(manifest_path, "a", encoding="utf-8", newline="") as manifest_file:
        manifest = csv.writer(manifest_file)
        if new_manifest:
            manifest.writerow(["word", "variant", "file", "page_url", "video_url", "note", "fetched_utc"])
        for i, word in enumerate(todo, 1):
            status, note = "none", ""
            try:
                saved = 0
                for found in lookup(word, http, variants):
                    name = f"{word}.mp4" if saved == 0 else f"{word}__{saved + 1}.mp4"
                    problem = save(found, videos / name, http)
                    if problem:
                        note = problem
                        continue
                    saved += 1
                    manifest.writerow([word, saved, name, found.page_url, found.video_url, found.note,
                                       datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")])
                    manifest_file.flush()
                status = "ok" if saved else "none"
                failures = 0
            except Blocked as refusal:
                stopped = str(refusal)
            except Exception as error:  # noqa: BLE001 - one bad word must not stop the run
                status, note = "error", f"{type(error).__name__}: {error}"
                failures += 1
            if stopped:
                break
            counts[status] += 1
            history_file.write(json.dumps({"word": word, "status": status, "note": note}) + "\n")
            history_file.flush()
            if probing and i <= len(PROBE_WORDS):
                probed += 1
                if probed == len(PROBE_WORDS) and counts["ok"] == 0:
                    stopped = (f"none of {', '.join(PROBE_WORDS)} gave a video: the site's pages "
                               "have probably changed, so its fetcher needs updating")
                    break
            if failures >= GIVE_UP_AFTER:
                stopped = f"{GIVE_UP_AFTER} lookups in a row failed; last: {note}"
                break
            if i % 100 == 0:
                log(f"{key}: {i}/{len(todo)} looked up, {counts['ok']} found")

    summary = {"site": key, "found": counts["ok"], "not_there": counts["none"], "errors": counts["error"],
               "videos": len(list(videos.glob("*.mp4"))), "stopped": stopped}
    log(f"{key}: {counts['ok']} found, {counts['none']} not there, {counts['error']} errors"
        + (f". STOPPED: {stopped}" if stopped else ""))
    (folder / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


# -- all sites, best first --------------------------------------------------------------------

def run(site_keys: Sequence[str], words: Sequence[str], have: Iterable[str] = (),
        root: Optional[Path] = None, http: Optional[Http] = None, variants: int = 1,
        log: Callable[[str], None] = print) -> List[Dict[str, object]]:
    """Fetch from each site in turn. Sites after FULL_SITES only get the words still missing."""
    root = root or sources.REPO_ROOT / ".work"
    http = http or Http()
    covered: Set[str] = set()
    have = set(have)
    summaries = []
    for key in site_keys:
        folder = root / key
        if key in FULL_SITES:
            todo = list(words)
        else:
            covered |= have
            todo = [w for w in words if w not in covered]
        summaries.append(fetch_site(key, todo, folder, http, variants, log=log))
        covered |= video_words(folder / "videos")
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    default_sites = [s.key for s in sources.fetched()]
    parser.add_argument("--sites", default=",".join(default_sites),
                        help=f"Comma-separated, best first (default: {','.join(default_sites)})")
    parser.add_argument("--words", type=Path, default=HERE / "target_words.txt")
    parser.add_argument("--limit", type=int, help="Only the first N words of the list")
    parser.add_argument("--have", action="append", type=Path, default=[],
                        help="A lexicon folder whose words the gap-filling sites should skip; repeat")
    parser.add_argument("--have-file", type=Path, help="A file of words to skip, one per line")
    parser.add_argument("--variants", type=int, default=1,
                        help="Signs to keep per word when a site lists several (default 1: its first)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests to one site")
    parser.add_argument("--root", type=Path, default=sources.REPO_ROOT / ".work")
    parser.add_argument("--list", action="store_true", help="List the sources and stop")
    args = parser.parse_args()

    if args.list:
        for source in sources.SOURCES:
            how = {sources.FETCHED: "fetched by this script", sources.FILES: "needs files from the owner",
                   sources.BUILT: "built by its own script"}[source.how]
            print(f"{source.key:15s} {source.name}: {how}"
                  + ("; non-commercial" if source.non_commercial else ""))
            if source.why_no_fetcher:
                print(f"{'':15s} {source.why_no_fetcher}")
        return 0

    keys = [k.strip() for k in args.sites.split(",") if k.strip()]
    for key in keys:
        if key not in LOOKUPS:
            reason = getattr(sources.get(key), "why_no_fetcher", "") or "unknown source"
            parser.error(f"no fetcher for {key}: {reason}")
    words = read_words(args.words)[: args.limit]
    have: Set[str] = set()
    for folder in args.have:
        have |= lexicon_words(folder)
    if args.have_file and args.have_file.exists():
        have |= set(read_words(args.have_file))
    summaries = run(keys, words, have, args.root, Http(delay=max(0.5, args.delay)), args.variants)
    print("\n".join(f"{s['site']:15s} {s['videos']:5d} videos" + (f"  STOPPED: {s['stopped']}" if s["stopped"] else "")
                    for s in summaries))
    return 0


if __name__ == "__main__":
    sys.exit(main())

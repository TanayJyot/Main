"""Tests for the dictionary-site fetcher and the one-command build.

    python showcase/test_fetch_sites.py

No network: pages are small copies of each site's real markup (October 2026),
served by a stand-in for the HTTP layer.
"""

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_all  # noqa: E402
import fetch_sites as fs  # noqa: E402
import sources  # noqa: E402

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4000

SAVVY_SIGN = """<div class="sign_module"> <div class="signing_header"> <h2>BOOK</h2> <ul>
<li><a class="current" href="javascript:;">ASL<br>1</a></li><li><a href="sign/book/9549/2"
title="Show variation 2 of sign">ASL<br>2</a></li><li><a href="sign/book/9549/3">finger<br>spell</a></li>
</ul> </div> <div class="signing_body"> <div class="videocontent"><link rel="preload" as="video"
href="https://www.signingsavvy.com/media2/mp4-ld/20/20983.mp4"><video preload="auto"
src="https://www.signingsavvy.com/media2/mp4-ld/20/20983.mp4"> <source
src="https://www.signingsavvy.com/media2/mp4-ld/20/20983.mp4" type="video/mp4"></video>"""

SAVVY_LIST = """<h2>Search Results for RUN</h2><div class="search_results"><ul><li><a
href="sign/run/10423/1">RUN</a> <em>(as in &quota motor running&quot)</em></li><li><a
href="sign/run/4403/1">RUN</a> <em>(as in &quotmoving quickly on feet&quot)</em></li><li><a
href="sign/run+away/4407/1">RUN AWAY</a> <em>(as in &quotrun away&quot)</em></li><li><a
href="sign/RUN/0/fingerspell">Show Fingerspelled</a></li></ul></div>"""

SAVVY_SPELLED = SAVVY_SIGN.replace('<a class="current" href="javascript:;">ASL<br>1</a>',
                                   '<a class="current" href="javascript:;">finger<br>spell</a>')

STS_SEARCH = """<a href="/en.us/word/1752/book/0/?q=book"> book <small>Verb</small></a>
<a href="/en.us/word/1881/book/0/?q=book"> book <small>Noun</small></a>
<a href="/en.us/word/3293/guide-book/0/?q=book"> guide book <small>Noun</small></a>
<a href="/en.us/word/1752/book/0/?q=book">again</a>"""

STS_WORD = """<h2> book </h2> <div class="result-description"> to reserve something </div>
<video class="js-enforce-speed" src="https://media.spreadthesign.com/video/mp4/13/399297.mp4"
poster="https://media.spreadthesign.com/video/jpg/13/399297.jpg" muted loop></video>"""

SIGNASL = """<video><source src="https://media.signbsl.com/videos/asl/startasl/mp4/book.mp4"></video>
<source src="https://media.signbsl.com/videos/asl/aslsignbank/mp4/OPEN-BOOK-1540.mp4">
<source src="https://media.signbsl.com/videos/asl/aslsignbank/mp4/BOOK2-77.mp4">
<source src="https://media.signbsl.com/videos/asl/aslsignbank/mp4/BOOK-418.mp4">
<a href="https://media.signbsl.com/videos/asl/aslsignbank/mp4/BOOK-418.mp4">Link to video</a>
<source src="https://media.signbsl.com/videos/asl/youtube/mp4/V27JKBneHgk.mp4">"""

LP_INDEX = """<a href="../pages-signs/b/bee.htm">BEE</a> <a href="../pages-signs/b/begin.htm">begin / start</a>
<a href="../pages-signs/w/with.htm">behind-[see WITH]</a> <a href="../pages-signs/b/book.htm">BOOK</a>
<a href="../pages-signs/b/boyfriend.htm">boy friend</a>"""

LP_PAGE = """<img src="../../gifs/b/book-open.gif"> <img src="../../images-signs/book.gif">
<img src="../../gifs/b/book.gif"> <iframe src="https://www.youtube.com/embed/SUlKivg4SDg"></iframe>"""


class FakeHttp:
    """Serves pages from a dict; counts requests; raises what a value says to raise."""

    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url):
        self.asked.append(url)
        value = self.pages.get(url)
        if isinstance(value, Exception):
            raise value
        return value.encode() if isinstance(value, str) else value

    def text(self, url):
        body = self.get(url)
        return None if body is None else body.decode("utf-8", "replace")


def test_signing_savvy_sign_page_and_meaning_list():
    assert fs.savvy_video(SAVVY_SIGN) == "https://www.signingsavvy.com/media2/mp4-ld/20/20983.mp4"
    assert fs.savvy_video(SAVVY_SPELLED) is None            # fingerspelled only: not a sign
    assert fs.savvy_video(SAVVY_LIST) is None
    meanings = fs.savvy_meanings(SAVVY_LIST, "run")
    assert [url for url, _ in meanings] == ["https://www.signingsavvy.com/sign/run/10423/1",
                                            "https://www.signingsavvy.com/sign/run/4403/1"]
    assert meanings[0][1] == 'as in "a motor running"'      # RUN AWAY and the fingerspelling are not "run"
    letter = ('<li><a href="sign/i/5828/1">I</a> <em>(as in &quotthe letter&quot)</em></li>'
              '<li><a href="sign/i/209/1">I</a> <em>(as in &quotme&quot)</em></li>')
    assert fs.savvy_meanings(letter, "i") == [("https://www.signingsavvy.com/sign/i/209/1", 'as in "me"')]


def test_signing_savvy_lookup_follows_the_first_meaning_only():
    http = FakeHttp({"https://www.signingsavvy.com/search/run": SAVVY_LIST,
                     "https://www.signingsavvy.com/sign/run/10423/1": SAVVY_SIGN,
                     "https://www.signingsavvy.com/search/book": SAVVY_SIGN})
    found = fs.savvy_lookup("run", http, 1)
    assert len(found) == 1 and found[0].page_url.endswith("/sign/run/10423/1")
    assert found[0].note == 'as in "a motor running"; meaning 1 of 2'
    assert len(http.asked) == 2                              # the search and one sign page
    assert fs.savvy_lookup("book", http, 1)[0].note == ""
    assert fs.savvy_lookup("zzqxv", http, 1) == []


def test_spreadthesign_takes_entries_spelled_like_the_word():
    results = fs.sts_results(STS_SEARCH, "book")
    assert [url for url, _ in results] == ["https://www.spreadthesign.com/en.us/word/1752/book/0/",
                                           "https://www.spreadthesign.com/en.us/word/1881/book/0/"]
    assert results[0][1] == "book Verb"
    assert fs.sts_video(STS_WORD) == "https://media.spreadthesign.com/video/mp4/13/399297.mp4"
    assert fs.sts_video("<h2>book</h2>") is None


def test_signasl_keeps_only_signbank_clips_of_the_exact_gloss():
    videos = fs.signasl_videos(SIGNASL, "book")
    assert [url.rsplit("/", 1)[1] for url, _ in videos] == ["BOOK-418.mp4", "BOOK2-77.mp4"]
    assert videos[0][1] == "ASL Signbank gloss BOOK"
    assert fs.signasl_videos(SIGNASL, "open") == []
    both = fs.signasl_videos(SIGNASL, "book", owners=("aslsignbank", "startasl"))
    assert both[0][0].endswith("/startasl/mp4/book.mp4")     # page order within the same rank


def test_lifeprint_index_and_its_own_gif():
    index = fs.lifeprint_index(LP_INDEX)
    assert index == {"bee": "/asl101/pages-signs/b/bee.htm", "begin": "/asl101/pages-signs/b/begin.htm",
                     "start": "/asl101/pages-signs/b/begin.htm", "book": "/asl101/pages-signs/b/book.htm"}
    url = "https://www.lifeprint.com/asl101/pages-signs/b/book.htm"
    assert fs.lifeprint_gif(LP_PAGE, url) == "https://www.lifeprint.com/asl101/gifs/b/book.gif"
    assert fs.lifeprint_gif(LP_PAGE.replace("gifs/b/book.gif", "gifs/b/book-2.gif"), url).endswith("/book-2.gif")
    assert fs.lifeprint_gif('<img src="../../gifs/b/book-open.gif">', url) is None


def _savvy_site(words):
    pages = {}
    for i, word in enumerate(words):
        video = f"https://www.signingsavvy.com/media2/mp4-ld/1/{i}.mp4"
        pages[f"https://www.signingsavvy.com/search/{word}"] = SAVVY_SIGN.replace(
            "https://www.signingsavvy.com/media2/mp4-ld/20/20983.mp4", video).replace("BOOK", word.upper())
        pages[video] = MP4
    return pages


def test_fetch_site_saves_records_and_resumes():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "signingsavvy"
        http = FakeHttp(_savvy_site(fs.PROBE_WORDS + ["dog"]))
        summary = fs.fetch_site("signingsavvy", ["dog", "zzqxv"], folder, http, log=lambda _: None)
        assert summary["found"] == 6 and summary["not_there"] == 1 and not summary["stopped"]
        assert (folder / "videos" / "dog.mp4").read_bytes() == MP4
        assert (folder / ".gitignore").read_text() == "*\n"
        rows = (folder / "manifest.csv").read_text().splitlines()
        assert rows[0].startswith("word,variant,file,page_url,video_url")
        assert any(r.startswith("dog,1,dog.mp4,https://www.signingsavvy.com/search/dog,") for r in rows)

        again = FakeHttp(_savvy_site(["cat"]))
        fs.fetch_site("signingsavvy", ["dog", "zzqxv", "cat"], folder, again, log=lambda _: None)
        assert again.asked[0].endswith("/search/cat")        # dog and zzqxv are not asked again
        assert len(again.asked) == 2


def test_a_site_whose_pages_changed_is_skipped_after_the_probe():
    with tempfile.TemporaryDirectory() as tmp:
        http = FakeHttp({})                                  # every page 404s
        words = [f"w{i}" for i in range(50)]
        summary = fs.fetch_site("signingsavvy", words, Path(tmp) / "s", http, log=lambda _: None)
        assert "probably changed" in summary["stopped"]
        assert len(http.asked) == len(fs.PROBE_WORDS)


def test_a_refusal_stops_the_site_at_once():
    with tempfile.TemporaryDirectory() as tmp:
        pages = _savvy_site(fs.PROBE_WORDS)
        pages["https://www.signingsavvy.com/search/dog"] = fs.Blocked("signingsavvy.com answered 403")
        http = FakeHttp(pages)
        summary = fs.fetch_site("signingsavvy", ["dog", "cat"], Path(tmp) / "s", http, log=lambda _: None)
        assert "403" in summary["stopped"] and not any(u.endswith("/cat") for u in http.asked)


def test_later_sites_are_only_asked_for_words_still_missing():
    with tempfile.TemporaryDirectory() as tmp:
        pages = _savvy_site(fs.PROBE_WORDS + ["dog"])
        for word in fs.PROBE_WORDS + ["cat", "owl"]:
            pages[f"https://www.spreadthesign.com/en.us/search/?q={word}"] = \
                f'<a href="/en.us/word/7/{word}/0/?q={word}">{word}</a>'
            pages[f"https://www.spreadthesign.com/en.us/word/7/{word}/0/"] = STS_WORD
        pages["https://media.spreadthesign.com/video/mp4/13/399297.mp4"] = MP4
        http = FakeHttp(pages)
        fs.run(["signingsavvy", "spreadthesign"], ["dog", "cat", "owl"], have={"owl"},
               root=Path(tmp), http=http, log=lambda _: None)
        asked = [u for u in http.asked if "spreadthesign.com/en.us/search" in u]
        assert not any(u.endswith("q=dog") or u.endswith("q=owl") for u in asked)   # dog fetched, owl held
        assert (Path(tmp) / "spreadthesign" / "videos" / "cat.mp4").exists()
        assert fs.video_words(Path(tmp) / "signingsavvy" / "videos") >= {"dog", "book"}


def test_http_obeys_robots_waits_between_requests_and_stops_when_refused():
    slept, now = [], [0.0]

    class Stub(fs.Http):
        def __init__(self, answers):
            super().__init__(delay=1.0, sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)),
                             clock=lambda: now[0])
            self.answers = answers

        def _open(self, url):
            return self.answers.get(url, (404, b"", {}))

    robots = b"User-agent: *\nDisallow: /private/\nCrawl-delay: 3\n"
    http = Stub({"https://x.org/robots.txt": (200, robots, {}), "https://x.org/a": (200, b"A", {}),
                 "https://x.org/b": (403, b"", {})})
    assert http.get("https://x.org/a") == b"A"
    assert http.get("https://x.org/missing") is None
    assert slept == [3.0, 3.0]                               # robots' crawl-delay, not our shorter one
    for url in ("https://x.org/private/c", "https://x.org/b"):
        try:
            http.get(url)
            raise AssertionError("expected Blocked")
        except fs.Blocked:
            pass


def test_animated_gif_becomes_a_video_and_a_still_does_not():
    import cv2
    import numpy as np
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        frames = [Image.fromarray(np.full((120, 161, 3), i * 20, dtype=np.uint8)) for i in range(8)]
        gif, mp4 = Path(tmp) / "a.gif", Path(tmp) / "a.mp4"
        frames[0].save(gif, save_all=True, append_images=frames[1:], duration=100, loop=0)
        assert fs.gif_to_mp4(gif, mp4)
        video = cv2.VideoCapture(str(mp4))
        assert int(video.get(cv2.CAP_PROP_FRAME_COUNT)) == 8
        assert int(video.get(cv2.CAP_PROP_FRAME_HEIGHT)) == 480 and round(video.get(cv2.CAP_PROP_FPS)) == 10
        video.release()
        still = Path(tmp) / "s.gif"
        frames[0].save(still)
        assert not fs.gif_to_mp4(still, Path(tmp) / "s.mp4")


def test_every_source_has_what_its_route_needs():
    assert sources.ORDER.index("signingsavvy") < sources.ORDER.index("aslc") < sources.ORDER.index("popsign")
    assert sources.ORDER[-1] == "fingerspelling"
    for source in sources.SOURCES:
        if source.how == sources.FETCHED:
            assert source.key in fs.LOOKUPS, source.key
        if source.how == sources.FILES:
            assert source.why_no_fetcher and source.key not in fs.LOOKUPS
        if source.how in (sources.FETCHED, sources.FILES):
            assert source.license and source.credit and source.non_commercial
    assert {s.key for s in sources.SOURCES if not s.non_commercial} == {"popsign", "fingerspelling"}


def test_report_counts_words_per_source_and_lists_gaps():
    with tempfile.TemporaryDirectory() as tmp:
        community = Path(tmp) / "community"
        community.mkdir()
        for word in ("and", "you", "fs_a"):
            (community / f"{word}.pose").write_bytes(b"x")
        (community / "lexicon.json").write_text(json.dumps(
            {"non_commercial": True, "letters": ["a"], "words_per_source": {"Signing Savvy": 2}}))
        text = build_all.report_text(community, ["and", "in", "you"], Path(tmp) / "work")
        assert "**2 words**, letters: a" in text and "NON-COMMERCIAL USE ONLY." in text
        assert "| Signing Savvy | 2 |" in text
        assert "## The most-used words still without a sign\n\nin\n" in text
        assert "Ask Handspeak to send the video files" in text


if __name__ == "__main__":
    failed = 0
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
                print(f"ok    {name}")
            except Exception as error:  # noqa: BLE001
                failed += 1
                print(f"FAIL  {name}: {type(error).__name__}: {error}")
    sys.exit(1 if failed else 0)

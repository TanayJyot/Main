"""The sign sources the community lexicon is built from, best first.

One place for each source's name, credit line, licence wording and how its
signs reach us, so the fetcher, the build and the pages all say the same thing.
DATA_LICENSES.md section 0 is the record of who gave permission and when; this
file must not claim more than that section does.

Every source here except PopSign and the fingerspelling letters is marked
non-commercial. A source stays non-commercial until its owner's written
permission says commercial use is allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

FETCHED = "fetched"      # fetch_sites.py downloads it, one sign per word
FILES = "files"          # the owner has to send the videos; drop them in the videos folder
BUILT = "built"          # built by its own script (PopSign, ASL Citizen, fingerspelling)


@dataclass(frozen=True)
class Source:
    key: str                 # folder name: .work/<key>/videos and lexicon/<key>
    name: str                # shown on pages and videos
    how: str                 # FETCHED, FILES or BUILT
    license: str = ""
    credit: str = ""
    non_commercial: bool = True
    why_no_fetcher: str = ""

    @property
    def videos(self) -> Path:
        return REPO_ROOT / ".work" / self.key / "videos"

    @property
    def lexicon(self) -> Path:
        return REPO_ROOT / "lexicon" / self.key


# Best first: where two sources sign the same word, the earlier one is used.
# Sources with written permission come before those whose written note is
# still on its way; within each group, studio recordings come first.
SOURCES: List[Source] = [
    Source("signingsavvy", "Signing Savvy", FETCHED,
           license="Non-commercial use only, by permission of Signing Savvy",
           credit="Signs from Signing Savvy (signingsavvy.com), used with permission for "
                  "non-commercial purposes."),
    Source("aslc", "ASL Citizen (Microsoft Research)", BUILT),
    Source("popsign", "PopSign ASL v1.0", BUILT, non_commercial=False),
    Source("handspeak", "Handspeak", FILES,
           license="Non-commercial use only, by permission of Handspeak (written note pending)",
           credit="Signs from Handspeak (handspeak.com), used with permission for "
                  "non-commercial purposes.",
           why_no_fetcher="handspeak.com turns automated readers away (robots.txt), so there is "
                          "no fetcher. Ask Handspeak to send the video files, named by word."),
    Source("spreadthesign", "SpreadTheSign", FETCHED,
           license="Non-commercial use only, by permission of SpreadTheSign (written note pending)",
           credit="Signs from SpreadTheSign (spreadthesign.com, European Sign Language Centre), "
                  "used with permission for non-commercial purposes."),
    Source("signbank", "ASL Signbank (copies hosted by SignASL.org)", FETCHED,
           license="CC BY-NC-SA 4.0 (ASL Signbank); fetched from SignASL.org by permission",
           credit="Signs from ASL Signbank (Hochgesang, Crasborn and Lillo-Martin, "
                  "aslsignbank.com), licensed CC BY-NC-SA 4.0: non-commercial, and anything "
                  "made from them is shared under the same licence. Copies fetched from "
                  "SignASL.org."),
    Source("lifeprint", "Lifeprint / ASL University", FETCHED,
           license="Non-commercial use only, by permission of Lifeprint (written note pending)",
           credit="Signs from Lifeprint / ASL University (lifeprint.com, Dr. Bill Vicars), used "
                  "with permission for non-commercial purposes."),
    Source("aslcore", "ASLCORE (RIT/NTID)", FILES,
           license="Non-commercial use only, by permission of ASLCORE, RIT/NTID (written note pending)",
           credit="Signs from ASLCORE (aslcore.org, Rochester Institute of Technology / NTID), "
                  "used with permission for non-commercial purposes.",
           why_no_fetcher="ASLCORE's videos are streamed from Vimeo, not kept on aslcore.org, and "
                          "its robots.txt asks for 60 seconds between requests. Ask RIT/NTID to "
                          "send the video files, named by word."),
    Source("fingerspelling", "Fingerspelling letters", BUILT, non_commercial=False),
]

BY_KEY: Dict[str, Source] = {source.key: source for source in SOURCES}
ORDER: List[str] = [source.key for source in SOURCES]


def get(key: str) -> Optional[Source]:
    return BY_KEY.get(key)


def fetched() -> List[Source]:
    return [source for source in SOURCES if source.how == FETCHED]


def dictionary() -> List[Source]:
    """Sources turned into a lexicon by video_lexicon.py from a folder of videos."""
    return [source for source in SOURCES if source.how in (FETCHED, FILES)]

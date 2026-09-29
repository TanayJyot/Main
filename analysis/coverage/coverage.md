# Coverage check — English caption vocabulary vs sign lexicons

Frequency proxy: `wordfreq` English, top 50,000 surface forms, lemmatised. Includes OpenSubtitles, the nearest public stand-in for caption text.

**Token coverage** = share of running words (by frequency mass) that have a sign. **Signable** excludes articles, copulas and auxiliaries that `text-to-gloss` drops (28 tokens, listed in `coverage.py`). Names are not handled; they would be fingerspelled.

| lexicon | concepts | tokens covered (all) | tokens covered (signable) | of top-1,000 lemmas | of top-5,000 lemmas |
|---|---|---|---|---|---|
| Old lexicon (deployed, 842 files) | 823 | 32.2% | **33.3%** | 307/1000 | 655/5000 |
| PopSign ASL v1.0 (CC BY 4.0) | 256 | 16.4% | **19.1%** | 117/1000 | 213/5000 |
| ASL Citizen (needs Microsoft email) | 2,271 | 57.7% | **63.3%** | 610/1000 | 1489/5000 |
| PopSign + ASL Citizen | 2,307 | 58.7% | **64.6%** | 623/1000 | 1510/5000 |
| PopSign + ASL Citizen + old | 2,445 | 64.4% | **66.2%** | 655/1000 | 1592/5000 |

## Most frequent old-lexicon signs that PopSign lacks

and, in, i, at, from, get, one, know, new, people, also, come, only, day, over, back, thing, most, very, great, off, love, game, never, long, last, help, keep, change, play, end, less, house, little, live, big, family, ask, become, number

## Most frequent old-lexicon signs that PopSign + ASL Citizen still lack

also, only, little, guy, post, level, force, american, deal, allow, five, cover, almost, build, international, forget, official, produce, ground, individual, activity, protect, chief, lord, notice, approach, compare, establish, female, operate, prepare, okay, chinese, absolutely, connect, driver, cent, depend, physical, payment

## Most frequent signable lemmas in no lexicon at all (top 300 by frequency)

as, by, just, their, her, would, its, could, may, too, life, through, part, such, include, around, company, during, service, fuck, second, mr, lot, case, let, ever, might, base, thought, set, someone, report, care, job, real, large, question, issue, however, low

## Pilot list

`pilot_200.txt`: 100 head + 100 tail glosses from the old lexicon (805 of its 823 concepts appear in the top 50,000). Every one has a baseline `.pose` to score a synthetic sign against.

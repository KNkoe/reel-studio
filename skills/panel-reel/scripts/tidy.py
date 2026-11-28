"""Take the ums, stumbles and repeats out of a talking cut.

    python3 -I tidy.py <project>                    the kept speech as a script, and what to look at
    python3 -I tidy.py <project> --words 70 80      every word between two seconds of the recording
    python3 -I tidy.py <project> --check            after cutting: lost words and leftover fillers

reel.json "cut": "fillers": true removes um, uh, er and hmm by itself. Anything else is chosen
by whoever edits, as "drop": [[12.40, "so the,", "said twice"], ...]: the time of the first
word in work/words_main.json, the words exactly as heard, and why. For a sound the transcript
missed, give the stretch instead: [18.9, 19.5, "um"]. cut.py removes them, placing each word cut
in the nearest pause, or at the quietest moment where there is none, then listens to each join
and moves the cut if a neighbouring word went with it.

Read the script first (run cut.py --plan once to transcribe). Times are the recording's.
"""
import array
import argparse
import difflib
import json
import math
import re
import subprocess
import wave
from pathlib import Path

RATE, STEP = 16000, 0.01
FILLER = re.compile(r"u+m+|u+h+m*|e+r+m*|h+m+|m{2,}")
RESTARTS = ("i mean", "or rather", "sorry", "let me start", "start again", "wait no", "scratch that", "what i meant")
OPEN_ENDS = {"the", "a", "an", "to", "and", "of", "with", "but", "because", "or", "is", "my", "your", "their", "for"}


def norm(text):
    return re.sub(r"[^a-z0-9']", "", text.lower().replace("’", "'"))


def is_filler(text):
    return bool(FILLER.fullmatch(norm(text)))


def dropped(settings, words):
    """{word index: why} for every word to leave out."""
    out = {}
    if settings.get("fillers"):
        out = {i: "filler" for i, w in enumerate(words) if is_filler(w[2])}
    for entry in settings.get("drop", []):
        if not isinstance(entry[1], str):
            continue
        at, phrase, why = float(entry[0]), entry[1], entry[2] if len(entry) > 2 else ""
        wanted = [t for t in map(norm, phrase.split()) if t]
        first = next((i for i, w in enumerate(words) if abs(w[0] - at) < 0.015), None)
        if first is None:
            raise SystemExit(f'drop [{at}, "{phrase}"]: no word starts at {at}. List them with tidy.py --words.')
        there = [norm(w[2]) for w in words[first:first + len(wanted)]]
        if not wanted or there != wanted:
            heard = " ".join(w[2] for w in words[first:first + max(len(wanted), 1)])
            raise SystemExit(f'drop [{at}, "{phrase}"]: the words there are "{heard}"')
        out.update({i: why or "dropped" for i in range(first, first + len(wanted))})
    return out


def runs(indices):
    """Neighbouring word numbers as [first, last] pairs."""
    out = []
    for i in sorted(indices):
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return out


class Sound:
    """Loudness of the recording in 10 ms steps, and where it pauses."""
    def __init__(self, path):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                             capture_output=True, check=True).stdout
        audio, size = array.array("h", raw), int(RATE * STEP)
        self.db = []
        for i in range(0, len(audio) - size + 1, size):
            part = audio[i:i + size]
            self.db.append(10 * math.log10(sum(v * v for v in part) / size / 32768 ** 2 + 1e-12))
        ranked = sorted(self.db)
        self.floor = ranked[int(len(ranked) * 0.9)] - 24 if ranked else -60.0
        self.pauses, start = [], None
        for i, level in enumerate(self.db + [0.0]):
            if level < self.floor and start is None:
                start = i
            elif level >= self.floor and start is not None:
                if (i - start) * STEP >= 0.08:
                    self.pauses.append((start * STEP, i * STEP))
                start = None

    def voiced(self, a, b):
        """Seconds of sound between two times."""
        return STEP * sum(1 for v in self.db[max(0, int(a / STEP)):max(0, int(b / STEP))] if v >= self.floor)

    def quietest(self, a, b, near):
        """The quietest moment between a and b, preferring ones close to near."""
        first, last = max(0, int(a / STEP)), min(len(self.db) - 1, int(b / STEP))
        if last <= first:
            return max(0.0, near)
        best = min(range(first, last), key=lambda i: (self.db[i] + self.db[i + 1]) / 2 + 25 * abs((i + 1) * STEP - near))
        return (best + 1) * STEP


def span(sound, start, end, leave, following=None):
    """Where to cut so the words from start to end go and their neighbours stay whole.

    A word's timing often begins with the silence before it, so the edges are looked for in the
    audio: in the pause on each side if there is one, else at the quietest moment nearby.
    """
    before = [p for p in sound.pauses
              if p[1] > start - 0.05 and p[0] < start + min(0.9, 0.75 * (end - start))
              and sound.voiced(start + 0.03, p[0]) <= 0.15 and sound.voiced(p[1], end + 0.05) >= 0.08]
    if before:
        p = before[0]
        a = p[0] + min(leave, max(0.0, p[1] - p[0] - 0.02))
    else:
        a = sound.quietest(start - 0.22, start + 0.08, start)

    def parts_them(p):
        """A pause a little late still counts if the next word is yet to be heard after it."""
        if p[0] < end + 0.12:
            return True
        return (following is not None and p[0] < end + 0.6 and p[1] < following - 0.05
                and sound.voiced(p[1], following + 0.05) >= 0.1)

    after = [p for p in sound.pauses
             if p[1] > end - 0.3 and p[0] > a and parts_them(p) and sound.voiced(p[1], end) <= 0.12]
    if after:
        p = after[-1]
        b = p[1] - min(leave, max(0.0, p[1] - p[0] - 0.02))
    else:
        b = sound.quietest(max(a, end - 0.15), end + 0.1, end)
    return a, b


# ---------------------------------------------------------------- listening to each join

# other places to try when a neighbour is lost or the sound is still there: (start, end) shifts
SHIFTS = ((0, 0), (0, -0.1), (0.1, 0), (0, -0.2), (0.1, -0.1), (0, 0.15), (-0.12, 0), (0.22, 0), (0.1, -0.22))
AROUND, GAP = (1.6, 3.2), 1.2        # seconds heard each side of a join, twice over


def transcriber(work):
    binary = work / "transcribe"
    if not binary.exists():
        subprocess.run(["swiftc", "-O", str(Path(__file__).resolve().parent / "transcribe.swift"), "-o", str(binary)],
                       check=True)
    return binary


def listen(work, audio, pieces, locale):
    """Transcribe many short stretches in one pass. Each is a list of (from, to) joined together."""
    quiet, data, windows = bytes(int(GAP * RATE) * 2), bytearray(), []
    for piece in pieces:
        start = len(data) / 2 / RATE
        for a, b in piece:
            data += audio[max(0, int(a * RATE)) * 2:max(0, int(b * RATE)) * 2]
        windows.append((start, len(data) / 2 / RATE))
        data += quiet
    joined, result = work / "joins.wav", work / "joins.json"
    with wave.open(str(joined), "wb") as out:
        out.setparams((1, 2, RATE, 0, "NONE", "NONE"))
        out.writeframes(bytes(data))
    subprocess.run([str(transcriber(work)), str(joined), str(result), locale], check=True, capture_output=True)
    heard = json.loads(result.read_text())
    return [[norm(t) for a, b, t in heard if x - GAP / 2 <= (a + b) / 2 < y + GAP / 2 and norm(t)] for x, y in windows]


def matched(wanted, heard):
    return sum(m.size for m in difflib.SequenceMatcher(None, wanted, heard, autojunk=False).get_matching_blocks())


def tune(work, mic, words, gone, cuts, locale):
    """Try each cut by ear. cuts: [(a, b, first word, last word)]. Returns [(a, b)] and doubts."""
    audio = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mic), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                           capture_output=True, check=True).stdout
    neighbours = []
    for a, b, first, last in cuts:
        before = [i for i in range(max(0, first - 6), first) if i not in gone][-2:]
        after = [i for i in range(last + 1, min(len(words), last + 7)) if i not in gone][:2]
        neighbours.append([norm(words[i][2]) for i in before + after])
    # what the transcriber makes of the untouched audio: it cannot be asked to hear more than this
    untouched = listen(work, audio, [[(a - n, b + n)] for a, b, _, _ in cuts for n in AROUND], locale)
    reachable = [[matched(neighbours[k], untouched[k * len(AROUND) + j]) for j in range(len(AROUND))]
                 for k in range(len(cuts))]

    def context(k, a, b):
        """The stretch from a to b as it will play: without the other cuts."""
        pieces, start = [], a
        for other, (x, y, _, _) in enumerate(cuts):
            if other != k and y > start and x < b:
                if x > start:
                    pieces.append((start, x))
                start = y
        return pieces + ([(start, b)] if start < b else [])

    best = [None] * len(cuts)
    for shift_a, shift_b in SHIFTS:
        trying = []
        for k, (a, b, _, _) in enumerate(cuts):
            x, y = a + shift_a, b + shift_b
            if (best[k] is None or best[k][0] < (sum(reachable[k]), 0)) and y - x >= 0.1:
                trying.append((k, x, y))
        if not trying:
            break
        results = listen(work, audio, [context(k, x - n, x) + context(k, y, y + n)
                                       for k, x, y in trying for n in AROUND], locale)
        for number, (k, x, y) in enumerate(trying):
            heard = results[number * len(AROUND):(number + 1) * len(AROUND)]
            kept = sum(min(matched(neighbours[k], h), reachable[k][j]) for j, h in enumerate(heard))
            score = (kept, -sum(1 for h in heard for t in h if FILLER.fullmatch(t)))
            if best[k] is None or score > best[k][0]:
                best[k] = (score, x, y)
    out, doubts = [], []
    for k, (a, b, first, last) in enumerate(cuts):
        score, x, y = best[k] or ((0, 0), a, b)
        out.append((x, y))
        if score < (sum(reachable[k]), 0):
            doubts.append([round(words[first][0], 2), " ".join(words[i][2] for i in range(first, last + 1)),
                           "a word beside it may be clipped" if score[0] < sum(reachable[k]) else "still audible"])
    return out, doubts


def removals(settings, words, mic, locale="en-US"):
    """(stretches of the recording to take out, {word index: why}). Writes work/doubts.json."""
    gone = dropped(settings, words)
    stretches = [(float(e[0]), float(e[1])) for e in settings.get("drop", []) if not isinstance(e[1], str)]
    for i, w in enumerate(words):                     # a word wholly inside a stretch goes with it
        if any(a - 0.02 <= w[0] and w[1] <= b + 0.02 for a, b in stretches):
            gone.setdefault(i, "dropped")
    named = dropped(settings, words)
    keep = settings.get("keep", [])
    wanted = [(first, last) for first, last in runs(named)            # only what the cut would play
              if any(words[last][1] > a and words[first][0] < b for _, a, b in keep)]
    doubts = []
    if wanted:
        work = Path(mic).parent
        leave = min(settings.get("leave", 0.17), 0.12)
        key = json.dumps([wanted, leave, locale, Path(mic).stat().st_mtime_ns, SHIFTS, AROUND])
        cache = work / "tuned.json"
        saved = json.loads(cache.read_text()) if cache.exists() else {}
        if saved.get("key") != key:
            sound, first_try = Sound(mic), []
            for first, last in wanted:
                following = words[last + 1][1] if last + 1 < len(words) else None
                first_try.append((*span(sound, words[first][0], words[last][1], leave, following), first, last))
            print(f"listening to {len(first_try)} joins…", flush=True)
            placed, unsure = tune(work, mic, words, named, first_try, locale)
            saved = {"key": key, "cuts": placed, "doubts": unsure}
            cache.write_text(json.dumps(saved))
        stretches += [tuple(c) for c in saved["cuts"]]
        doubts = saved["doubts"]
    (Path(mic).parent / "doubts.json").write_text(json.dumps(doubts))
    out = []
    for a, b in sorted(stretches):
        if b - a < 0.05:
            continue
        if out and a <= out[-1][1] + 0.05:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out, gone


def subtract(a, b, out, words, gone):
    """The parts of a..b that remain; a scrap with no kept word in it goes too."""
    pieces, start = [], a
    for x, y in out:
        if y <= start or x >= b:
            continue
        if x > start:
            pieces.append((start, x))
        start = y
    if start < b:
        pieces.append((start, b))

    def holds_a_word(p, q):
        return any(i not in gone and p <= (w[0] + w[1]) / 2 < q for i, w in enumerate(words))

    return [(p, q) for p, q in pieces if q - p >= 0.5 or (q - p >= 0.1 and holds_a_word(p, q))]


# ---------------------------------------------------------------- reading the script

def sentences(numbers, words):
    out = []
    for i in numbers:
        if not out or words[out[-1][-1]][2].rstrip()[-1:] in ".?!" or i != out[-1][-1] + 1 or len(out[-1]) >= 30:
            out.append([])
        out[-1].append(i)
    return out


def suspects(lines, words, gone):
    """Places worth a second look, as (seconds, what, words). Only a person can judge them."""
    found = []
    left = [i for line in lines for i in line if i not in gone]
    text = [norm(words[i][2]) for i in left]
    covered = -1
    for k in range(len(left)):
        for size in (6, 5, 4, 3, 2, 1):
            if k > covered and k + 2 * size <= len(left) and text[k:k + size] == text[k + size:k + 2 * size]:
                said = " ".join(words[i][2] for i in left[k:k + 2 * size])
                found.append((words[left[k]][0], "said twice in a row", said))
                covered = k + 2 * size - 1
                break
    joined = [(line, [i for i in line if i not in gone]) for line in lines]
    joined = [(line, kept) for line, kept in joined if kept]
    for line, kept in joined:
        said = " ".join(words[i][2] for i in kept)
        plain = " " + " ".join(norm(words[i][2]) for i in kept) + " "
        if any(f" {r} " in plain for r in RESTARTS):
            found.append((words[kept[0]][0], "may be a restart or correction", said))
        if norm(words[kept[-1]][2]) in OPEN_ENDS:
            found.append((words[kept[0]][0], "trails off", said))
    for n, (_, first) in enumerate(joined):
        a = [norm(words[i][2]) for i in first]
        for _, second in joined[n + 1:n + 9]:
            b = [norm(words[i][2]) for i in second]
            if min(len(a), len(b)) >= 5 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.6:
                found.append((words[first[0]][0], f"much like the line at {words[second[0]][0]:.2f}",
                              " ".join(words[i][2] for i in first)))
                break
    return sorted(found)


def script(project, settings, words):
    gone = dropped(settings, words)
    keep = settings.get("keep") or [["all", 0.0, words[-1][1] + 1]]
    lines, read = [], []
    for name, a, b in keep:
        inside = [i for i, w in enumerate(words) if a <= (w[0] + w[1]) / 2 < b]
        print(f"== {name}  ({a}-{b})")
        for line in sentences(inside, words):
            lines.append(line)
            shown, skipped = [], []
            for i in line + [None]:
                if i is not None and i in gone:
                    skipped.append(i)
                    continue
                if skipped:
                    shown.append("[" + " ".join(words[k][2] for k in skipped) + "]")
                    skipped = []
                if i is not None:
                    shown.append(words[i][2])
            print(f"  {words[line[0]][0]:8.2f}  {' '.join(shown)}")
            clean = " ".join(words[i][2] for i in line if i not in gone)
            if clean:
                read.append(clean)
    out = project / "work" / "script.txt"
    out.write_text("\n".join(read) + "\n")
    fillers = sum(1 for line in lines for i in line if gone.get(i) == "filler")
    others = sum(1 for line in lines for i in line if i in gone) - fillers
    print(f"\n[in brackets] comes out: {fillers} fillers, {others} other words")
    found = suspects(lines, words, gone)
    print(f"{len(found)} to look at (some repeats are meant: keep those):" if found else "nothing else stands out")
    for at, what, said in found:
        print(f"  {at:8.2f}  {what}: {said}")
    print(f"what the viewer will hear: {out}")


# ---------------------------------------------------------------- listening to the cut

def check(project):
    """Transcribe the cut voice and compare it with the words that should be in it."""
    work = project / "work"
    small, heard_file = work / "check16.wav", work / "words_check.json"
    if not (work / "voice.wav").exists():
        raise SystemExit("cut first: there is no work/voice.wav")
    binary = transcriber(work)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(work / "voice.wav"), "-ac", "1", "-ar", str(RATE),
                    str(small)], check=True)
    subprocess.run([str(binary), str(small), str(heard_file)], check=True)
    expected = [w for w in json.loads((work / "words_edit.json").read_text()) if norm(w[2])]
    heard = [w for w in json.loads(heard_file.read_text()) if norm(w[2])]
    segments = json.loads((work / "edl.json").read_text())["segments"]
    cuts = [s["start"] for s in segments]
    matcher = difflib.SequenceMatcher(None, [norm(w[2]) for w in expected], [norm(w[2]) for w in heard], autojunk=False)
    doubts = []
    for op, i, j, k, m in matcher.get_opcodes():
        if op not in ("delete", "replace"):
            continue
        a, b = expected[i][0], expected[j - 1][1]
        if any(a - 0.35 <= c <= b + 0.35 for c in cuts):
            got = " ".join(w[2] for w in heard[k:m]) or "nothing"
            doubts.append(f"  {a:7.2f}  (recording {expected[i][3]:.2f})  expected '"
                          f"{' '.join(w[2] for w in expected[i:j])}', heard '{got}'")
    def recorded(t):
        s = [s for s in segments if s["start"] <= t + 1e-6][-1]
        return s["in"] + t - s["start"]

    left = [f"  {w[0]:7.2f}  (recording {recorded(w[0]):.2f}-{recorded(w[1]):.2f})  '{w[2]}'"
            for w in heard if is_filler(w[2])]
    print(f"\n{len(doubts)} places at a cut to listen to (the transcriber also varies by itself):")
    print("\n".join(doubts) or "  none")
    print(f"{len(left)} fillers still heard:")
    print("\n".join(left) or "  none")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path)
    parser.add_argument("--words", type=float, nargs=2, metavar=("FROM", "TO"))
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    project = options.project.expanduser().resolve()
    if options.check:
        return check(project)
    words_file = project / "work" / "words_main.json"
    if not words_file.exists():
        raise SystemExit("no transcript yet: run cut.py <project> --plan first")
    words = json.loads(words_file.read_text())
    if options.words:
        for start, end, text in words:
            if options.words[0] <= start <= options.words[1]:
                print(f"{start:8.3f} {end:8.3f}  {text}")
        return
    script(project, json.loads((project / "reel.json").read_text())["cut"], words)


if __name__ == "__main__":
    main()

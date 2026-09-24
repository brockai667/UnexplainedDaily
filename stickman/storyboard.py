# -*- coding: utf-8 -*-
r"""Storyboard generator pre prerobeny UnexplainedDaily: tema -> scenar (11-13 viet) + shot-list.

Vystup je STYL-NEZAVISLY: to iste JSON vie vyrenderovat styl A (3D keyframy) aj styl B (panacik/HyperFrames).
Pravidla su z overenych dvoch epizod (Gobekli Tepe) a z rersersu, co funguje na kanale:
1 veta = 1 zaber, suvisly pribeh (but/so/then), ~165-175 wpm, 85-100 slov = 28-33 s, titul v tvare "The ..." do 6 slov,
ziadne "you/your", posledny zaber sa vracia na prvy (loop) a konci otvorenou otazkou.

Pouzitie:
  python storyboard.py "Gobekli Tepe"                 # vygeneruje + ulozi specs/gobekli-tepe.json
  python storyboard.py "Gobekli Tepe" --show          # aj vypise scenar po vetach
Kluc: GROQ_API_KEY z ~/.config/watch/.env (lokalne) alebo MODELS_TOKEN z prostredia (Actions).
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SPECS = os.path.join(ROOT, "specs")
os.makedirs(SPECS, exist_ok=True)

# kluc: lokalne z ~/.config/watch/.env, v Actions uz je MODELS_TOKEN v prostredi
if not os.environ.get("MODELS_TOKEN"):
    envp = os.path.join(os.path.expanduser("~"), ".config", "watch", ".env")
    if os.path.exists(envp):
        for ln in open(envp, encoding="utf-8"):
            if ln.strip().startswith("GROQ_API_KEY"):
                os.environ["MODELS_TOKEN"] = ln.split("=", 1)[1].strip().strip('"').strip("'")
sys.path.insert(0, ROOT)
import llm as common  # noqa: E402  (llm_json s retry-after, Groq)

# ------------------------------------------------------------------ archetypy zaberov
# kluc -> (co sa deje v obraze, ake zlate cislo/text sa da zobrazit)
SHOTS = {
    "walk_in":     "hlavna postava prichadza na miesto (kopec, brana, dvere); zlaty ROK alebo miesto",
    "spot":        "postava si vsimne detail; punch-in na detail, zlate '!'",
    "dig":         "postava odkryva/otvara/vytahuje vec; udery, otrasy",
    "descend":     "vec pokracuje dalej dole/dovnutra, nez cakala (hlbka, dlzka)",
    "scale_measure": "cely objekt v zabere + kota, ktora narastie na rozmer (count-up 's jednotkou')",
    "human_stack": "POROVNANIE VELKOSTI s ludmi naskladanymi na sebe (napr. 'three people on each other's shoulders'), cisla 1-2-3",
    "wide_reveal": "siroky/vtacie zaber odhali, ze toho je VIAC (kruhy, pole, mesto)",
    "timeline_compare": "porovnanie s niecim znamym (pyramida, Rim) + count-up rokov",
    "no_list":     "tri slamy typu 'NO METAL / NO WHEEL / NO WRITING' presne na slovach",
    "action_crowd": "skupina ludi nieco robi (tesa, stava, zasypava, uteka)",
    "exhibit":     "artefakt vo vitrine/v muzeu/na stole, kamera obchadza detail (sucasnost, nie pravek)",
    "theory":      "spekulacia: Bob a dve myslienkove bubliny s dvoma verziami (druha veta doplni pravu bublinu)",
    "object_reveal": "cely hlavny objekt v zabere (lod, stroj, dvere), kamera ho odhali; veta opisuje SAM objekt",
    "detail_compare": "dve veci vedla seba v jednom zabere + zlaty pocet/pomer (223 zubov, 35 kolies z toho 30 viditelnych)",
    "punch":       "tvrdy zoom na kluc. slovo (napr. 'On purpose.'), uder v zvuku",
    "loop_close":  "navrat na uvodny zaber, zlate '?', otvorena otazka",
}
ORDER_HINT = ("walk_in -> spot -> dig -> descend -> scale_measure -> human_stack -> wide_reveal -> "
              "timeline_compare -> no_list -> action_crowd -> punch -> loop_close")

SYSTEM = "You write 30-second YouTube Shorts narration for a mystery/history channel. Output strict JSON only."

# Kokoro am_michael: pri rychlosti 1.12 hovori ~2.41 slova/s (odmerane na Mary Celeste: 87 slov = 36,1 s).
# Engine podla toho zafixuje `speed` v spec-e a nemusi hladat rychlost opakovanou syntezou.
WPS, SPEED_BASE, TARGET_S = 2.41, 1.12, 31.0

FACTS_PROMPT = """Topic: {topic}

SOURCE TEXT (Wikipedia article "{wtitle}") - every fact you list MUST come from this text, word for word in meaning.
If a name, year or number is not in this text, do not write it anywhere.
---
{extract}
---

List what is actually known about this, as a fact sheet for a narrator. Only facts you are confident are real.
Include: who found it / who is involved and in which year, where it is, the key measurements with units,
its age and how that compares to one famous thing, what the people or builders did NOT have or know,
what happened to it in the end, and what is genuinely still unexplained (mark interpretations as interpretations).

Return JSON: {{"facts": ["...", "..."], "uncertain": ["claims often repeated but not established"]}}
8 to 12 facts, each one short sentence with concrete numbers where they exist."""

PROMPT = """Topic: {topic}

FACT SHEET (ground truth - use ONLY these facts, do not add any others):
{facts}
Do NOT state any of these as fact (they are disputed): {uncertain}

Write the narration for ONE 30-second vertical short and its shot list.

HARD RULES
- 11 to 13 sentences, 85-100 words TOTAL. Sentence = 4 to 12 words.
- One sentence = one shot. The story runs continuously (and / but / so / then). No fragments, no trailer lines.
- Start with a SITUATION a person is in (year + someone doing something), never with a claim or a question.
- Present tense, concrete: a named person or "an archaeologist" does a concrete thing.
- Exactly one number-with-unit fact (size/height/depth) and exactly one age/time comparison to something famous.
- Somewhere: three things the builders/people did NOT have (three short items, 1-2 words each).
- Last sentence: an open question ("And nobody knows why." style). No call to action, no "subscribe".
- NEVER use the words "you" or "your". No "imagine". No adjectives stacked ("incredible, mysterious").
- Title: starts with "The", max 6 words, no numbers, no colon.
- NEVER describe the camera or the shot ("the camera descends", "wide shot"). Say what HAPPENS in the world.
- An interpretation must be marked as one ("its discoverer believed", "archaeologists think"), never stated as fact.
- Facts must come from the fact sheet above. If a detail is not there, leave it out instead of inventing it.

SHOT TYPES (use each at most twice, keep roughly this order: {order})
{shots}

Return JSON exactly like this:
{{"title": "The ...",
  "lines": [
    {{"say": "In 1994, an archaeologist climbs a hill in southern Turkey", "shot": "walk_in",
      "gold": {{"text": "1994"}}, "cue": "1994"}},
    {{"say": "It's a carved pillar, five and a half metres tall.", "shot": "scale_measure",
      "gold": {{"count": 5.5, "unit": "m"}}, "cue": "five"}},
    {{"say": "The people who built it had no metal, no wheel, no writing.", "shot": "no_list",
      "gold": {{"items": ["NO METAL", "NO WHEEL", "NO WRITING"]}}, "cue": "metal"}}
  ]}}
"gold" is optional (only where a number/word should slam on screen); "cue" is the word in that sentence
where the gold element appears - it MUST be a word from "say".

The shot name is only HOW it is filmed - the sentence must never mention the shot, the camera or a "wide view",
and must never reuse the shot name as a word. Here is a full, correct example for a different topic
(Gobekli Tepe) - copy its rhythm and concreteness, not its content:
{EXAMPLE}"""

# --- dvojkrokovy rezim (kvalitnejsi): najprv scenar bez zaberov, potom priradenie zaberov ---
SCRIPT_PROMPT = """Topic: {topic}

FACT SHEET (ground truth - use ONLY these facts, never add a name, year or number that is not here):
{facts}
Do NOT state any of these as fact (disputed): {uncertain}

Write ONLY the narration of a 30-second vertical short. No shots, no camera, no directions.

HARD RULES
- 11 to 13 sentences, 70-80 words TOTAL. Sentence = 4 to 9 words, never longer - a 13-word sentence
  forces the narrator to rush and the episode no longer fits 33 seconds.
- One continuous story (and / but / so / then). No fragments, no trailer lines, no lists of adjectives.
- Start with a SITUATION: a year plus a person doing a concrete thing. Never start with a claim or question.
- Present tense. Every sentence is something that HAPPENS or a plain fact.
- Exactly one measurement with a unit.
- An age comparison to something famous ("seven thousand years older than the pyramids") ONLY if the fact sheet
  really supports it. If the fact sheet has no such comparison, leave it out - never invent one, and never compare
  a thing to a famous object it has nothing to do with.
- The example below says "no metal, no wheel, no writing" because those builders were Stone Age. That line belongs
  ONLY to that topic. Never write it for anything else - a bronze device, a ship or a modern case obviously had metal
  and writing, and writing it there is a factual error. Only list things they lacked if the fact sheet says so.
- An interpretation must be marked ("its discoverer believed", "archaeologists think").
- Never the words "you", "your", "imagine", "subscribe". Never name the camera or a shot.
- Second to last sentence closes the story ("And nobody knows why." style).
- LAST sentence is an open question that makes people comment (6-10 words, no "you").
- Title: starts with "The", max 6 words, no numbers, no colon.

Return JSON: {{"title": "The ...", "say": ["sentence 1", "sentence 2", ...]}}

Example of the right rhythm (different topic - copy the rhythm, not the content):
{EXAMPLE}"""

SHOTS_PROMPT = """Assign a camera shot to each narration sentence of a 30-second cartoon short.

SHOT TYPES:
{shots}
Usual order: {order}. Use each at most twice. The FIRST sentence is walk_in or spot,
the sentence that closes the story is punch or action_crowd, the LAST sentence (the question) is loop_close.

SENTENCES:
{numbered}

For each sentence return the shot, an optional gold element that slams on screen, and the cue word
(a word that really occurs in that sentence, where the gold appears).
gold is one of: {{"text": "1994"}} | {{"count": 5.5, "unit": "m"}} | {{"items": ["NO METAL", "NO WHEEL", "NO WRITING"]}}
Only add gold where there is a real number, year or triple IN THAT SENTENCE. The gold values must be taken from the
sentence itself - never copy the values from this instruction. Most sentences have no gold at all.
The shot must match what the sentence is about: scale_measure only for a size with a unit, timeline_compare only for
an age/era comparison, no_list only for a sentence listing three missing things, human_stack only for a size compared
to people, action_crowd only when a group does something.

Return JSON: {{"lines": [{{"i": 1, "shot": "walk_in", "gold": {{"text": "1994"}}, "cue": "1994"}}, ...]}}"""

EXAMPLE = """
 1 walk_in          In 1994, an archaeologist climbs a hill in southern Turkey
 2 spot             and sees a stone poking out of the dirt.
 3 dig              He digs.
 4 descend          It keeps going down.
 5 scale_measure    It's a carved pillar, five and a half metres tall.
 6 human_stack      That's three people standing on each other's shoulders.
 7 wide_reveal      And it's not alone. There are whole rings of them.
 8 timeline_compare This place is seven thousand years older than the pyramids.
 9 no_list          The people who built it had no metal, no wheel, no writing.
10 action_crowd     Then they buried all of it.
11 punch            On purpose.
12 loop_close       And nobody knows why."""

EXAMPLE_SAY = """In 1994, an archaeologist climbs a hill in southern Turkey / and sees a stone poking out of the dirt. /
He digs. / It keeps going down. / It's a carved pillar, five and a half metres tall. / That's three people standing on
each other's shoulders. / And it's not alone. There are whole rings of them. / This place is seven thousand years older
than the pyramids. / The people who built it had no metal, no wheel, no writing. / Then they buried all of it. /
On purpose. / And nobody knows why. / What would make people bury their own temple?"""


def _words(lines):
    return sum(len(l["say"].split()) for l in lines)


def check(spec):
    """Vrati zoznam problemov (prazdny = OK)."""
    p, lines = [], spec.get("lines", [])
    t = spec.get("title", "")
    if not (11 <= len(lines) <= 13):
        p.append(f"poce viet {len(lines)} (chcem 11-13)")
    w = _words(lines)
    if not (66 <= w <= 82):
        p.append(f"slov {w} (chcem 70-80 = 29-33 s pri prirodzenom tempe)")
    if not t.startswith("The ") or len(t.split()) > 6:
        p.append(f"titul '{t}' (ma zacinat 'The' a mat max 6 slov)")
    for i, l in enumerate(lines):
        n = len(l["say"].split())
        if n > 12 or n < 3:
            p.append(f"veta {i+1} ma {n} slov: {l['say'][:50]}")
        if l.get("shot") not in SHOTS:
            p.append(f"veta {i+1}: neznamy shot '{l.get('shot')}'")
        if re.search(r"\b(you|your|imagine|subscribe)\b", l["say"], re.I):
            p.append(f"veta {i+1} obsahuje zakazane slovo: {l['say'][:50]}")
        cue = (l.get("cue") or "").lower().strip(".,!?")
        if cue and cue not in [x.lower().strip(".,!?") for x in l["say"].split()]:
            p.append(f"veta {i+1}: cue '{cue}' nie je v texte")
    if lines:
        if lines[0]["shot"] not in ("walk_in", "spot"):
            p.append("prvy zaber ma byt walk_in/spot (situacia, nie tvrdenie)")
        if lines[-1]["shot"] != "loop_close":
            p.append("posledny zaber ma byt loop_close (navrat + otazka)")
        if not lines[-1]["say"].rstrip().endswith("?"):
            p.append("posledna veta MUSI byt otvorena otazka do komentarov (koncit otaznikom), "
                     "'And nobody knows why.' patri az predposledne")
    # porovnanie veku je vitane, ale nevynucuj ho - vynutene porovnanie plodi nezmysly
    # („Its length surpasses the Titanic" pri 103 ft lodi)
    return p


NUMWORD = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100}
UNITS = r"(metres|meters|m|kilometres|kilometers|km|feet|foot|ft|tons|tonnes|kilograms|kg|centimetres|cm)"


def assign_shots(says, world="hill"):
    """Zaber priradi KOD podla toho, o com veta je (maly model to robil semanticky zle).
    LLM uz len pise text; mapovanie je deterministicke a testovatelne."""
    n = len(says)
    lines, used = [], {}
    # na mori/brehu nie je kam kopat ani co rozmnozit - tieto zabery tam vyzeraju ako bana a cintorin
    banned = {"descend", "wide_reveal", "dig"} if world in ("shore", "sea") else set()
    if world == "sea":
        banned |= {"human_stack", "action_crowd"}   # na palube sa panacikovia na seba nestavaju ani nezasypavaju jamu
    era_default = "historic" if re.search(r"\b1[7-9]\d{2}|20\d{2}\b", " ".join(says)) else "ancient"

    def take(shot, fallback="punch"):
        if shot in banned:
            shot = fallback if fallback not in banned else "punch"
        if used.get(shot, 0) >= 2:          # ziadny archetyp viac ako 2x (inak 6 rovnakych zaberov za sebou)
            # ber ten z pouzitelnych, ktory bol zatial najmenej krat - rozlozi to zabery rovnomerne
            # len vseobecne pouzitelne zabery; exhibit/dig/human_stack su viazane na konkretny obsah
            rota = [x for x in ("spot", "punch", "object_reveal", "descend", "wide_reveal") if x not in banned]
            alt = min(rota, key=lambda x: (used.get(x, 0), rota.index(x)))
            used[alt] = used.get(alt, 0) + 1
            return alt
        used[shot] = used.get(shot, 0) + 1
        return shot

    for i, s in enumerate(says):
        low = s.lower()
        gold, cue, shot, bubble = None, None, None, None
        modern = bool(re.search(r"\b(museum|exhibit|display|viewers|tourists|visitors|laborator|imaging|x-?ray|scan|"
                                r"ct |radiocarbon|researchers?|scientists?|today|modern|replica|reconstruction)\b", low))
        nos = re.findall(r"\bno ([a-z]+)", low)
        m_unit = re.search(r"\b([\d][\d.,]*|" + "|".join(NUMWORD) + r")(?:\s+and a half)?\s+" + UNITS + r"\b", low)
        # rok = cislo s erou (70 BC) alebo po "in/around/by/since/from"; inak je to pocet, nie rok
        m_year = re.search(r"\b(?:in|around|by|since|from|to)\s+(\d{1,3}(?:,\d{3})+|\d{3,4})\b|"
                           r"\b(\d{1,3}(?:,\d{3})+|\d{1,4})\s*(?:bce|bc|ce|ad)\b", low)
        if m_year:
            m_year = re.match(r"(.*)", next(g for g in m_year.groups() if g))
        m_wordage = re.search(r"\b(" + "|".join(NUMWORD) + r")\s+(thousand|hundred)\s+years\b", low)
        m_numyears = re.search(r"\b(\d{1,3}(?:,\d{3})+|\d{3,4})\s+years\b", low)      # "2,300 years older"
        m_part = re.search(r"\b(\d{2,4})\s+(?:\w+\s+)?(teeth|gears|cogs|dials|pieces|fragments|parts|wheels|"
                           r"symbols|characters|letters)\b", low)          # cast objektu -> detail, nie sirka zaberu
        m_many = re.search(r"\b(\d{2,4})\s+(?:\w+\s+)?(bones|skeletons|stones|bodies|people|coins|rooms|"
                           r"enclosures|pillars|tablets|graves|statues|ships|houses|mounds)\b", low)
        # „before" samo o sebe nie je porovnanie veku („the log stops ten days before the discovery")
        m_age = re.search(r"\b(older than|predates|earlier than|years older)\b", low) or (
            re.search(r"\bbefore\b", low) and re.search(r"\b(\d{3,4}|years|century|centuries|era)\b", low)
            and re.search(r"\bbefore\s+(?:the\s+)?[a-z]", low))
        if i == 0:
            shot = take("walk_in")
        elif i == n - 1:
            shot = "loop_close"
        elif modern and re.search(r"\b(museum|exhibit|display|case|vitrine|shelf|collection|rests? in|sits? in|"
                                  r"on show|viewers|visitors)\b", low):
            shot = take("exhibit")
        elif len(nos) >= 3:
            shot, gold = take("no_list"), {"items": [f"NO {w.upper()}" for w in nos[:3]]}
            cue = nos[0]
        elif m_unit:
            raw = m_unit.group(1)
            val = NUMWORD.get(raw, None)
            if val is None:
                try:
                    val = float(raw.replace(",", ""))
                except ValueError:
                    val = None
            if val is not None and "and a half" in low:
                val += 0.5
            unit = {"metres": "m", "meters": "m", "foot": "ft", "feet": "ft", "kilometres": "km",
                    "kilometers": "km", "tonnes": "t", "tons": "t", "kilograms": "kg",
                    "centimetres": "cm"}.get(m_unit.group(2), m_unit.group(2))
            shot = take("scale_measure")
            if val is not None:
                # engine musi vediet, ci kreslit kotu zvislo (vyska) alebo vodorovne (dlzka)
                axis = "h" if re.search(r"\b(length|long|wide|width|across|span|diameter)\b", low) else "v"
                gold, cue = {"count": val, "unit": unit, "axis": axis}, raw
        elif m_age and m_wordage:
            val = NUMWORD[m_wordage.group(1)] * (1000 if m_wordage.group(2) == "thousand" else 100)
            shot, gold, cue = take("timeline_compare"), {"count": val, "unit": "YEARS"}, m_wordage.group(1)
        elif m_age and m_numyears:
            shot, gold = take("timeline_compare"), {"count": int(m_numyears.group(1).replace(",", "")), "unit": "YEARS"}
            cue = m_numyears.group(1)
        elif m_age and m_year:
            shot, gold, cue = take("timeline_compare"), {"text": m_year.group(1)}, m_year.group(1)
        elif m_age and re.search(r"(?:older than|before|predates|earlier than)\s+(?:the\s+)?[a-z]", low):
            shot = take("timeline_compare")          # porovnanie veku aj bez cisla ("predates the printing press")
        elif re.search(r"\b(people|person|adults?|men|women|shoulders|taller|stacked|stories)\b", low) and \
                re.search(r"\b(that's|as tall|same as|equal)\b", low):
            shot = take("human_stack")
        elif re.search(r"\b(some \w+|others \w+|researchers think|archaeologists think|historians think|"
                       r"believed?|theory|theories|suspect|may have|might have|possibly|perhaps)\b", low):
            shot = "theory"                   # engine spari dve susedne theory vety do dvoch bublin
            stop = {"believe", "believed", "believes", "others", "suggest", "suggests", "think", "thinks", "could",
                    "would", "should", "their", "these", "those", "which", "about", "after", "before", "sudden",
                    "suddenly", "theory", "theories", "perhaps", "possibly", "historians", "researchers",
                    "archaeologists", "scientists", "people"}
            # bublina = prve vecne slovo ZA spekulativnym slovesom („some believe toxic fumes…" -> fumes)
            adj = {"toxic", "sudden", "strange", "possible", "likely", "violent", "secret", "unknown", "massive"}
            tail = re.split(r"\b(?:believed?|believes|suggests?|think|thinks|suspect|theory|theories|"
                            r"may have|might have|perhaps|possibly)\b", low, maxsplit=1)
            words_after = re.findall(r"\b([a-z]{4,})\b", tail[-1]) if len(tail) > 1 else []
            cand = [w for w in words_after if w not in stop and w not in adj]
            if cand:
                bubble, cue = cand[0], cand[0]
        elif re.search(r"^(the|its|it|her|his)\s+\w+.{0,30}\b(appears|remains?|stands?|sits?|looks?|lies?|floats?|"
                       r"is intact|is empty|is sealed|is gone)\b", low):
            shot = take("object_reveal", "spot")   # veta opisuje sam objekt - punch na tvar je tam prazdny
        elif re.search(r"\b(sees|spots|notices|finds|spotted|glinting|sticking|poking)\b", low):
            shot = take("spot")
        elif re.search(r"\b(digs|dug|uncovers|excavat|shovel|brush)\w*\b", low):
            shot = take("dig")
        elif re.search(r"\b(deeper|keeps going|descend|further down|below|beneath|under the)\b", low):
            shot = take("descend")
        elif re.search(r"\b(bury|buried|carry|carried|build|built|carve|carved|flee|fled|abandon|filled)\w*\b", low):
            shot = take("action_crowd")
        elif re.search(r"\b(whole|dozens|hundreds|rings|circles|everywhere|across|more of them|not alone|others)\b", low):
            shot = take("wide_reveal")
        elif m_many:
            shot, gold, cue = take("wide_reveal"), {"text": m_many.group(1)}, m_many.group(1)
        elif m_part:
            ax = "h" if re.search(r"\b(length|long|wide|width|across|span|diameter)\b", low) else "v"
            shot, gold, cue = take("detail_compare"), {"text": m_part.group(1), "axis": ax}, m_part.group(1)
        else:
            shot = take("punch", "spot")
        if i == 0 and m_year:
            gold, cue = {"text": m_year.group(1)}, m_year.group(1)
        lines_vs = None                      # engine potrebuje vediet, s CIM sa porovnava (inak kresli vzdy pyramidu)
        if shot == "timeline_compare":
            mv = re.search(r"(?:older than|before|predates|earlier than)\s+(?:the\s+)?([a-z][a-z \-]{2,28})", low)
            if mv:
                lines_vs = re.split(r"\s+(?:by|in|around|about)\s+", mv.group(1).strip().rstrip(".,"))[0]
                if lines_vs in ("discovery", "it", "this", "that", "them", "us", "today", "now", "then",
                                "the ship", "the site", "the find"):
                    lines_vs = None          # nie je to znamy orientacny bod, nedá sa nakreslit
        if shot == "timeline_compare" and not lines_vs:
            shot = "punch"                    # engine bez 'vs' nevie, s cim porovnavat - radsej tvrdy zoom
        # era: muzeum/veda = modern; rok 1700+ = historic (19. storocie nie su jaskynni ludia); inak ancient
        yr = re.search(r"\b(1[7-9]\d{2}|20\d{2})\b", low)
        era = "modern" if modern else ("historic" if yr else era_default)
        lines.append({"say": s, "shot": shot, "era": era,
                      **({"gold": gold} if gold else {}), **({"cue": cue} if cue else {}),
                      **({"vs": lines_vs} if lines_vs else {}), **({"bubble": bubble} if bubble else {})})
    if "wide_reveal" not in banned and not any(l["shot"] == "wide_reveal" for l in lines):   # pribeh chce vrchol
        for l in lines[3:-2]:
            if l["shot"] == "punch":
                l["shot"] = "wide_reveal"
                break
    return lines


WORLDS = [                     # (regex, svet pre uvodny/slucokovy zaber, varianta postavy)
    # lod na otvorenom mori = svet `sea` (hladina ako zem, sail_in); breh je len pre nalezy na pobrezi
    (r"\bship\b|brigantine|schooner|vessel|adrift|lifeboat|voyage|crew|sailor|cargo", "sea", "sailor"),
    (r"port\b|harbou?r|beach|shoreline|lighthouse", "shore", "sailor"),
    (r"shipwreck|sunken|\bdiver|diving|underwater|salvage|sponge", "shore", "diver"),
    (r"glacier|snow|ice|frozen|himalaya|alpine|mountain pass|blizzard", "snow", "ranger"),
    (r"sea|ocean|coast|island|atlantic|pacific|lake", "shore", "ranger"),
    (r"desert|sand|dune|sahara|oasis|nazca", "desert", "archaeologist"),
    (r"cave|cavern|underground|tunnel|mine|grotto|catacomb", "cave", "archaeologist"),
    (r"forest|jungle|rainforest|swamp|woods", "forest", "ranger"),
    (r"city|street|town|building|factory|museum|library|laboratory", "city", "scientist"),
]


def scene_world(topic, facts, says):
    """Uvodny (a teda aj slucokovy) svet + varianta postavy podla temy - inak kazda epizoda zacina na kopci."""
    blob = " ".join([topic] + list(facts) + list(says)).lower()
    for rx, world, hero in WORLDS:
        if re.search(rx, blob):
            return world, hero
    return "hill", "archaeologist"


def trim_to_length(spec, hi=80):
    """Prilis dlhy scenar neskracujeme dalsim volanim LLM - zahodime vypln (zabery bez zlateho prvku,
    nie prvy/posledny), od najdlhsej vety. Kazda veta je samostatna, pribeh to unesie."""
    lines = spec.get("lines", [])
    n = lambda: sum(len(l["say"].split()) for l in lines)
    dropped = []
    while n() > hi and len(lines) > 11:
        cand = [(len(l["say"].split()), i) for i, l in enumerate(lines)
                if 0 < i < len(lines) - 2 and not l.get("gold") and l.get("shot") in ("punch", "spot", "action_crowd")]
        if not cand:
            break
        _, i = max(cand)
        dropped.append(lines.pop(i)["say"])
    if dropped:
        print(f"  skratene o {len(dropped)} viet: " + " | ".join(d[:40] for d in dropped), flush=True)
    return spec


CMP_VERB = r"(older than|younger than|predates|earlier than|surpass\w*|taller than|longer than|bigger than|" \
           r"larger than|heavier than|faster than|before the)"


def check_compare(spec):
    """Porovnanie so znamym objektom musi mat oporu vo faktoch - inak vzniknu nezmysly
    ako „Its length surpasses the Titanic" pri 103-stopovej lodi."""
    facts = " ".join(spec.get("facts", [])).lower()
    if not facts:
        return []
    p = []
    for i, l in enumerate(spec.get("lines", [])):
        low = l.get("say", "").lower()
        m = re.search(CMP_VERB + r"\s+(?:the\s+)?([a-z][a-z \-]{2,24})", low)
        if not m:
            continue
        what = m.group(2).split()[0].strip(".,")
        if len(what) > 3 and what not in facts:
            p.append(f"veta {i+1} porovnava s '{what}', ale fact sheet o tom nic nehovori - "
                     f"porovnavaj len s tym, co je vo faktoch, alebo vetu vyhod")
    return p


def check_no_list(spec):
    """'no metal, no wheel, no writing' je pravda len pri kamennej dobe - inak je to vecny nezmysel."""
    facts = " ".join(spec.get("facts", [])).lower()
    bad = []
    for i, l in enumerate(spec.get("lines", [])):
        if l.get("shot") != "no_list":
            continue
        low = l.get("say", "").lower()
        items = re.findall(r"\bno ([a-z]+)", low)
        ok = any(re.search(r"\b(no|without|lacked|did not have|had none)\b.{0,40}" + re.escape(w), facts) for w in items)
        if not ok:
            bad.append(f"veta {i+1} tvrdi '{', '.join('no ' + w for w in items)}', ale fact sheet to nehovori "
                       f"- prepis vetu na nieco, co je v faktoch")
    return bad


def wiki_extract(topic, chars=6000):
    """Realny podklad namiesto pamate modelu: Wikipedia (bez kluca). Vrati (nazov clanku, text) alebo (None, '')."""
    import requests
    api = "https://en.wikipedia.org/w/api.php"
    h = {"User-Agent": "FactoryAnim/1.0 (storyboard research)"}
    try:
        s = requests.get(api, params={"action": "query", "list": "search", "srsearch": topic,
                                      "srlimit": 1, "format": "json"}, headers=h, timeout=20).json()
        hits = s.get("query", {}).get("search", [])
        if not hits:
            return None, ""
        title = hits[0]["title"]
        e = requests.get(api, params={"action": "query", "prop": "extracts", "explaintext": 1,
                                      "titles": title, "format": "json"}, headers=h, timeout=25).json()
        page = next(iter(e.get("query", {}).get("pages", {}).values()), {})
        return title, (page.get("extract") or "")[:chars]
    except Exception as ex:                      # radsej bez podkladu ako spadnut
        print(f"  [wiki] chyba: {ex}", flush=True)
        return None, ""


def check_facts(spec):
    """Mena a rocne cisla v scenari musia byt vo fact sheete (LLM si inak vymysli objavitela)."""
    facts = " ".join(spec.get("facts", [])).lower()
    if not facts:
        return []
    # vseobecne zname orientacne body nie su vymyslene mena - tie sa vo fact sheete byt nemusia
    known = {"great", "pyramid", "pyramids", "stonehenge", "egypt", "egyptian", "rome", "roman", "greek", "greece",
             "europe", "european", "earth", "moon", "sun", "america", "asia", "africa", "viking", "vikings",
             "bronze", "iron", "stone", "middle", "ages", "world", "war", "north", "south", "east", "west",
             "eiffel", "tower", "liberty", "statue", "titanic", "colosseum", "parthenon", "acropolis", "atlantic",
             "pacific", "mediterranean", "sahara", "himalaya", "himalayas", "everest", "nile", "amazon", "alps"}
    known |= {w.lower().strip(".,") for w in (spec.get("topic", "") + " " + spec.get("title", "")).split()}
    p = []
    for l in spec.get("lines", []):
        toks = l.get("say", "").split()
        start = True
        for w in toks:
            c = w.strip(".,!?;:'\"()")
            end = w.endswith((".", "!", "?"))
            if c:
                if re.fullmatch(r"\d{3,4}", c):
                    if c not in facts:
                        p.append(f"rok/cislo {c} nie je vo fact sheete")
                elif not start and len(c) > 2 and c[:1].isupper() and c.lower() not in facts                         and c.lower() not in known:
                    p.append(f"meno '{c}' nie je vo fact sheete")
            start = end
    return sorted(set(p))


def _split_facts(obj):
    """LLM vie vratit fakty ako jeden string s kudrnatymi uvodzovkami (JSON pole sa zlepi do 1 polozky).
    Vytiahne z lubovolnej struktury rovny zoznam viet."""
    out = []
    if isinstance(obj, str):
        s = obj.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        parts = re.split(r'"\s*,\s*"|\n\s*-\s*|\n{2,}', s)
        out += [p.strip().strip('"').strip() for p in parts if len(p.strip()) > 12]
    elif isinstance(obj, list):
        for x in obj:
            out += _split_facts(x)
    elif isinstance(obj, dict):
        for x in obj.values():
            out += _split_facts(x)
    return [o for o in out if o]


def repair(spec):
    """Opravi drobnosti, ktore netreba riesit dalsim volanim LLM (hlavne cue slova)."""
    for l in spec.get("lines", []):
        toks = [w.strip(".,!?;:'’\"") for w in l.get("say", "").split()]
        low = [w.lower() for w in toks]
        cue = (l.get("cue") or "").lower().strip(".,!?")
        if cue and cue in low:
            continue
        g = l.get("gold") or {}
        cand = []
        if "count" in g:                      # cislo -> slovo, kde sa cislo hovori
            cand = [w for w in toks if re.match(r"^[\d.,]+$", w)] or \
                   [w for w in toks if w.lower() in ("five", "six", "seven", "eight", "nine", "ten", "three", "four", "two")]
        elif "text" in g:
            cand = [w for w in toks if w.strip(".,").lower() == str(g["text"]).lower()]
        elif "items" in g and g["items"]:
            first = str(g["items"][0]).split()[-1].lower()   # "NO METAL" -> "metal"
            cand = [w for w in toks if w.lower() == first]
        if not cand:                          # fallback: prve dlhsie slovo v druhej polovici vety
            cand = [w for w in toks[len(toks) // 2:] if len(w) > 3] or toks[-1:]
        l["cue"] = cand[0].strip(".,!?")
    return spec


def generate(topic, tries=3):
    shots_txt = "\n".join(f"- {k}: {v}" for k, v in SHOTS.items())
    print("  wikipedia...", flush=True)
    wtitle, extract = wiki_extract(topic)
    print(f"  podklad: {wtitle or 'NENASIEL'} ({len(extract)} znakov)", flush=True)
    print("  fakty...", flush=True)
    raw = common.llm_json(FACTS_PROMPT.format(topic=topic, wtitle=wtitle or "-",
                                              extract=extract or "(clanok sa nenasiel - pouzi len to, cim si si isty)"),
                          SYSTEM, temperature=0.2, max_tokens=1200) or {}
    fact_list = _split_facts(raw.get("facts", raw))
    unc_list = _split_facts(raw.get("uncertain", []))
    fs = {"facts": fact_list, "uncertain": unc_list}
    facts = "\n".join(f"- {f}" for f in fact_list) or "- (fact sheet sa nepodaril, drz sa vseobecne znameho)"
    unc = "; ".join(unc_list) or "(nic)"
    print(f"  fact sheet: {len(fact_list)} faktov, {len(unc_list)} spornych", flush=True)
    sprompt = SCRIPT_PROMPT.format(topic=topic, facts=facts, uncertain=unc, EXAMPLE=EXAMPLE_SAY)
    last, best = None, None
    for attempt in range(1, tries + 1):
        # krok 2: scenar BEZ zaberov (model sa inak snazi opisovat kameru)
        try:                                  # Groq obcas vrati 400 json_validate_failed -> skus bez FIX bloku
            sc = common.llm_json(sprompt if attempt == 1 else sprompt + FIX.format(problems="; ".join(last)),
                                 SYSTEM, temperature=0.6, max_tokens=1400) or {}
        except Exception as ex:
            print(f"  pokus {attempt}: LLM zlyhalo ({str(ex)[:60]}), skusam holy prompt", flush=True)
            try:
                sc = common.llm_json(sprompt, SYSTEM, temperature=0.75, max_tokens=1400) or {}
            except Exception as ex2:
                print(f"  pokus {attempt}: aj holy prompt zlyhal ({str(ex2)[:60]})", flush=True)
                continue
        says = [s.strip() for s in _split_facts(sc.get("say", [])) if s.strip()]
        if not says:
            continue
        # krok 3: priradenie zaberov - deterministicky z textu viet (maly model to robil semanticky zle)
        world, hero = scene_world(topic, fact_list, says)
        spec = {"title": sc.get("title", ""), "topic": topic, "facts": fact_list,
                "world": world, "hero": hero, "lines": assign_shots(says, world)}
        # rychlost reci dopocitaj rovno, nech engine nemusi skusat rebricek (kazdy stupen = nova synteza)
        spec["speed"] = round(max(SPEED_BASE, SPEED_BASE * _words(spec["lines"]) / (WPS * TARGET_S)), 2)
        repair(spec)
        # nepodlozene porovnanie radsej zahod hned, nez kvoli nemu volat LLM znova (veta je samostatna)
        while len(spec["lines"]) > 11:
            bad = check_compare(spec)
            if not bad:
                break
            idx = int(re.search(r"veta (\d+)", bad[0]).group(1)) - 1
            print(f"  zahodena nepodlozena porovnavacia veta: {spec['lines'][idx]['say'][:50]}", flush=True)
            spec["lines"].pop(idx)
        trim_to_length(spec)
        last = check(spec) + check_facts(spec) + check_no_list(spec) + check_compare(spec)
        print(f"  pokus {attempt}: {len(spec.get('lines', []))} viet, {_words(spec.get('lines', []))} slov, "
              f"{'OK' if not last else 'problemy: ' + '; '.join(last)}", flush=True)
        if not last:
            return spec, []
        if best is None or len(last) < len(best[1]):      # ak ziadny pokus nie je cisty, vrat ten najmenej zly
            best = (spec, last)
    if best:
        return best
    raise SystemExit("LLM nevratil pouzitelny scenar (skus znova, Groq byval 400/429)")


FIX = """

The previous attempt had these problems - fix ONLY these and keep the rest:
{problems}"""


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)
    topic = " ".join(args)
    spec, problems = generate(topic)
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    out = os.path.join(SPECS, slug + ".json")
    json.dump(spec, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{spec.get('title')}  ->  {out}")
    if "--show" in sys.argv:
        for i, l in enumerate(spec.get("lines", []), 1):
            g = l.get("gold")
            print(f" {i:2}. [{l['shot']:16}] {l['say']}" + (f"   ZLATE: {g}" if g else ""))
    w = _words(spec.get("lines", []))
    print(f"slov: {w}  odhad dlzky pri rychlosti {spec.get('speed', SPEED_BASE)}: {w / (WPS * spec.get('speed', SPEED_BASE) / SPEED_BASE):.1f} s")
    if problems:
        print("PROBLEMY:", "; ".join(problems))
        sys.exit(2)

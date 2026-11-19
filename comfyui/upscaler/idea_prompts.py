"""Model-free idea exploration for LFM3-VL: each call turns a draft into a new prompt idea.

The base-prompt contract (``lfm_prompts``) deliberately invents nothing. This mode is the
opposite: it keeps the draft's core subject and explicit constraints, then explores one or
two *lenses* (setting, light, viewpoint, story moment, ...) in a *structure* (cinematic shot,
layered depth, photo brief, ...) that were not used recently. The model first brainstorms a
few one-line concepts; the one least similar to earlier ideas is developed into the prompt.
Concrete "sparks" sampled per call push a small model away from its most typical answer.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

CONTRACT_VERSION = "idea-explore-1"
EXPLORATIONS = ("explore", "wild")
DETAILS = ("concise", "balanced", "detailed")
TARGETS = ("general", "moss_image", "krea2")


@dataclass(frozen=True)
class Lens:
    key: str
    label: str
    instruction: str
    sparks: tuple[str, ...]
    bold: bool = False


@dataclass(frozen=True)
class Structure:
    key: str
    label: str
    instruction: str


LENSES = (
    Lens("setting", "Setting", "Place the scene somewhere specific and unexpected but fitting. If the draft names a place, keep it and show an unusual corner or version of it.",
         ("a flooded cathedral", "a rooftop greenhouse", "a night market under an overpass", "a salt flat", "an abandoned observatory",
          "a bamboo scaffold", "a frozen harbor", "a desert motel", "a cliffside monastery", "a subway platform after closing",
          "a sunflower field taller than people", "a library with collapsed shelves")),
    Lens("time_weather", "Time and weather", "Set a precise time of day and weather that changes how everything looks.",
         ("blue hour after rain", "a dust storm at noon", "first light through fog", "a thunderstorm on the horizon", "heavy snow at midnight",
          "heat haze at midday", "drizzle under streetlights", "the minute before sunset", "a clear night under a full moon", "monsoon rain")),
    Lens("light", "Light", "Build the image around one distinctive light source: say where it comes from and what it touches.",
         ("a single bare bulb", "light through stained glass", "bioluminescent water", "a bonfire", "car headlights", "a flickering television",
          "paper lanterns", "sunlight through blinds", "a lightning flash", "a welding torch", "a candle held close", "a sodium streetlamp")),
    Lens("viewpoint", "Viewpoint", "Choose a striking viewpoint and framing: where the camera stands, how far away, and what frames the subject.",
         ("a worm's-eye view", "a high top-down view", "framed through a doorway", "seen in a puddle reflection", "an extreme close-up",
          "a tiny figure in a vast wide shot", "over the shoulder", "through rain-streaked glass", "a tilted angle", "through foreground leaves")),
    Lens("moment", "Moment", "Show a different instant of the story, just before or just after the main action, with visible cause and effect.",
         ("the moment before contact", "the aftermath", "a split second of surprise", "the calm after chaos", "mid-fall", "the first step",
          "a held breath", "an interrupted task")),
    Lens("palette", "Color", "Give the image a deliberate color story: two or three named dominant colors and where each one appears.",
         ("teal and burnt orange", "monochrome red", "mint and peach pastels", "black and gold", "ultramarine and lemon yellow",
          "faded sepia with one red accent", "emerald and ivory", "violet and acid green")),
    Lens("material", "Materials", "Make materials and textures tangible: name the surfaces and how they are worn, wet, rough or polished.",
         ("cracked porcelain", "rusted iron", "wet velvet", "frosted glass", "woven straw", "polished brass", "weathered wood",
          "dripping wax", "knitted wool", "chipped enamel")),
    Lens("companion", "Companion", "Add one secondary character or creature that interacts with the main subject in a meaningful way.",
         ("a curious crow", "a child", "a stray cat", "an old robot", "a ghostly double", "a swarm of fireflies", "a rival",
          "a sleeping dog", "a tiny dragon")),
    Lens("story", "Story details", "Add environmental storytelling: two or three specific objects that hint at who the subject is and what just happened.",
         ("a half-written letter", "a cracked compass", "spilled tea", "a torn ticket", "an open toolbox", "scattered photographs",
          "a wilted bouquet", "a map with circled places", "an unlit lantern")),
    Lens("motion", "Motion", "Add frozen motion: wind, splashes, falling or flying particles, fabric or hair caught moving.",
         ("flying sparks", "a burst of feathers", "swirling leaves", "a splash frozen mid-air", "drifting ash", "billowing fabric",
          "scattering paper", "falling petals", "sea spray")),
    Lens("emotion", "Emotion", "Give the subject one specific, readable emotion shown through expression, posture and gesture.",
         ("quiet pride", "exhausted relief", "mischievous delight", "fierce focus", "melancholy", "awe", "nervous anticipation",
          "tender affection")),
    Lens("scale", "Scale", "Play with scale: make something dramatically huge or tiny compared with everything else.",
         ("a giant hand", "a miniature city", "a tiny figure on an enormous object", "a moon filling the sky", "towering plants",
          "a dollhouse-sized world", "a colossal statue"), bold=True),
    Lens("era", "Era", "Move the scene into a specific era or future and show it in clothing, objects and architecture.",
         ("the 1920s", "the Bronze Age", "a 1980s suburb", "Victorian London", "a far-future colony", "the Edo period",
          "the 1960s space age", "a medieval village", "a post-apocalyptic future", "Art Deco 1930s"), bold=True),
    Lens("genre", "Genre", "Reinterpret the scene through the visual language of a genre, shown through costume, setting and staging.",
         ("a fairy tale", "film noir", "a nature documentary", "space opera", "a western", "gothic horror", "a heist", "a folk tale",
          "slapstick comedy", "a mythic epic"), bold=True),
    Lens("twist", "Twist", "Introduce one surreal or impossible element that fits the idea, described as if it were real.",
         ("gravity turned sideways", "a door standing in the sky", "clouds indoors", "an ocean inside a teacup",
          "shadows that move on their own", "plants made of glass", "a staircase into the sea", "fish swimming through the air"), bold=True),
    Lens("medium", "Medium", "Show the scene as a specific medium and describe its visible technique.",
         ("a 35mm film photograph", "a gouache illustration", "a claymation set", "a woodblock print", "a cut-paper diorama",
          "a charcoal sketch", "a glossy 3D render", "an impasto oil painting", "a vintage travel poster", "a cyanotype"), bold=True),
)
STRUCTURES = (
    Structure("cinematic", "Cinematic shot", "Begin with the shot type and camera position, then the subject and its action, then the surroundings, then the light and its direction, and end with one atmospheric detail."),
    Structure("layered", "Layered depth", "Describe the foreground first, then the main subject in the middle ground, then the background, and finish with the light that ties the layers together."),
    Structure("story", "Story moment", "Write it as a frozen moment from a story: what is happening, how the subject reacts, the telling details around them, then the light and mood."),
    Structure("spotlight", "Subject spotlight", "Start close on the subject (face or surface, clothing or texture, expression), then pose and gesture, then a brief setting, then the light falling on the subject."),
    Structure("atmosphere", "Atmosphere first", "Open with the atmosphere, weather and light, then reveal the subject within it, then the specific details, and end with the dominant colors."),
    Structure("photo_brief", "Photo brief", "Write it like a photographer's shot description: camera position and lens (for example 24mm or 85mm), subject and action, location, light, color grade, and the character of the film or sensor."),
    Structure("cascade", "Wide to detail", "Start with the whole scene in one sentence, narrow down to the subject, and finish on one striking small detail seen up close."),
    Structure("contrast", "Contrast", "Build the description around one strong visual contrast (big and small, warm and cold, still and moving, old and new) and describe both sides clearly."),
    Structure("composition", "Composition", "Describe the picture through its composition: where the subject sits in the frame, the leading lines and empty space, how the eye travels, then the light and colors."),
)
LENS_BY_KEY = {lens.key: lens for lens in LENSES}
STRUCTURE_BY_KEY = {structure.key: structure for structure in STRUCTURES}

_WORDS = {"concise": (45, 70), "balanced": (80, 120), "detailed": (130, 180)}
_SENTENCES = {"concise": "3 or 4", "balanced": "4 to 6", "detailed": "6 to 9"}
_TOKENS = {"concise": 150, "balanced": 240, "detailed": 360}
_TARGET = {
    "general": "a modern text-to-image model that reads natural-language descriptions",
    "moss_image": "MOSS Image, which reads long natural-language captions; tie every attribute to its subject and state spatial relations plainly",
    "krea2": "Krea 2, which reads rich natural-language descriptions; describe light, surfaces and photographic or painterly qualities concretely",
}
_KEEP = {
    "explore": "the draft's main subjects with their number and key traits, their action, and the setting if the draft names one, "
    "plus names, colors, quoted text and exclusions. Change or add only what the draft leaves open.",
    "wild": "the draft's main subjects with their number, their action, and anything in quotation marks or marked with no or "
    "without. Setting, era, mood, scale and viewpoint may be reinvented boldly.",
}
_CONCEPTS = {"explore": 3, "wild": 4}
# Minimum share of the draft's content words the final prompt must still contain.
_COVERAGE = {"explore": 0.6, "wild": 0.4}
_STOP = set(
    "a an the and or but of in on at to for from with without by into onto over under above below near is are was were be been "
    "being it its this that these those there their his her him she he they them we you your our as while than then so very "
    "some any each every all no not never one two three image picture photo scene prompt draft concept beside behind "
    "between through across along around beneath inside outside toward towards against while where which who whose has "
    "have had upon".split()
)
# Common synonyms, so "elderly" still covers a draft's "old".
_ALIASES = {"elderly": "old", "aged": "old", "senior": "old", "women": "woman", "men": "man", "lady": "woman",
            "children": "child", "kid": "child", "kids": "child", "people": "person", "folk": "person", "pup": "puppy",
            "kitten": "cat", "feline": "cat", "canine": "dog", "automobile": "car", "ocean": "sea"}
# Words a small model reaches for in almost every description; decoding is biased away from them.
OVERUSED = ("weathered", "bustling", "ethereal", "vibrant", "serene", "tapestry", "testament", "mesmerizing",
            "breathtaking", "symphony", "palpable", "whimsical", "otherworldly", "juxtaposition")
_QUOTES = re.compile(r'"([^"\n]+)"|“([^”]+)”')
_CONTROL = re.compile(r"<\|[^|\n]+\|>|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LABEL = re.compile(
    r"^\s*(?:\*\*|#+\s*)?(?:here(?:'s| is)[^:\n]{0,60}:|(?:final\s+|image\s+|full\s+)*(?:prompt|caption|description|concept)\s*\d*\s*(?:\*\*)?\s*:)\s*",
    re.I,
)
_FILLER = re.compile(
    r",?\s*\b(?:masterpiece|best quality|high quality|highly detailed|ultra[- ]detailed|8k|4k|hdr|uhd|trending on artstation|"
    r"award[- ]winning|hyper[- ]?realistic|ultra[- ]realistic)\b",
    re.I,
)


def validate(prompt, exploration="explore", detail="balanced", target_model="general", lens="auto", structure="auto",
             temperature=0.85, avoid="", recent="", max_new_tokens=0, earlier="") -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Enter a draft idea to explore")
    prompt = prompt.strip()
    if len(prompt) > 6000:
        raise ValueError("Draft ideas support up to 6,000 characters")
    if exploration not in EXPLORATIONS:
        raise ValueError("exploration must be explore or wild")
    if detail not in DETAILS:
        raise ValueError("detail must be concise, balanced or detailed")
    if target_model not in TARGETS:
        raise ValueError("target_model must be general, moss_image or krea2")
    if lens != "auto" and lens not in LENS_BY_KEY:
        raise ValueError("Unknown lens")
    if structure != "auto" and structure not in STRUCTURE_BY_KEY:
        raise ValueError("Unknown structure")
    if not isinstance(temperature, (int, float)) or not 0 <= temperature <= 1.5:
        raise ValueError("temperature must be between 0 and 1.5")
    if not isinstance(avoid, str) or len(avoid) > 8000 or not isinstance(recent, str) or len(recent) > 600:
        raise ValueError("avoid or recent is too long")
    if not isinstance(earlier, str) or len(earlier) > 12000:
        raise ValueError("earlier is too long")
    if type(max_new_tokens) is not int or not (max_new_tokens == 0 or 64 <= max_new_tokens <= 1024):
        raise ValueError("max_new_tokens must be 0 (automatic) or 64 to 1024")
    return prompt


def recent_keys(recent: str) -> set[str]:
    return {item.strip() for item in re.split(r"[,\s]+", recent or "") if item.strip()}


def avoid_list(avoid: str) -> list[str]:
    return [line.strip(" -•\t") for line in (avoid or "").splitlines() if len(line.strip(" -•\t")) > 3][-12:]


def without_quotes(text: str) -> str:
    """Earlier ideas are listed without their quoted words, which a small model would otherwise copy."""
    return re.sub(r"\s+", " ", re.sub(r',?\s*(?:\w+\s+){0,3}"[^"\n]*"?|,?\s*(?:\w+\s+){0,3}“[^”]*”?', "", text)).strip(" ,")


def plan(seed: int, exploration: str, detail: str, lens: str = "auto", structure: str = "auto", recent: str = "") -> dict:
    """Seeded lens/structure/spark choice that skips keys used recently while alternatives remain."""
    rng = random.Random(int(seed) & 0xFFFFFFFFFFFFFFFF)
    used = recent_keys(recent)

    def pick(pool, keyed):
        fresh = [item for item in pool if item.key not in used] or list(pool)
        return keyed(rng.choice(fresh))

    if lens != "auto":
        lenses = [LENS_BY_KEY[lens]]
    elif exploration == "wild":
        lenses = [pick([item for item in LENSES if item.bold], lambda item: item)]
    else:
        lenses = [pick([item for item in LENSES if item.key != "medium"], lambda item: item)]
    if exploration == "wild":
        lenses.append(pick([item for item in LENSES if item not in lenses and not item.bold], lambda item: item))
    chosen = STRUCTURE_BY_KEY[structure] if structure != "auto" else pick(STRUCTURES, lambda item: item)
    sparks = [spark for item in lenses for spark in rng.sample(item.sparks, min(3, len(item.sparks)))]
    return {"lenses": lenses, "structure": chosen, "sparks": sparks, "concepts": _CONCEPTS[exploration],
            "rng_state": rng.getrandbits(32)}


def words_for(detail: str, draft: str) -> tuple[int, int]:
    low, high = _WORDS[detail]
    length = len(draft.split())
    # Long drafts are restructured, not cut down to a short target.
    return (max(low, min(200, length)), max(high, min(240, length + 40)))


def token_budget(detail: str, draft: str, override: int = 0) -> int:
    if override:
        return override
    return max(_TOKENS[detail], min(1024, int(words_for(detail, draft)[1] * 1.7)))


def brainstorm_messages(draft: str, exploration: str, chosen: dict, avoid: list[str]) -> list[dict]:
    count = chosen["concepts"]
    lines = [
        "Draft: " + draft,
        "",
        "Keep " + _KEEP[exploration],
        "Explore: " + " ".join(lens.instruction for lens in chosen["lenses"]),
        "Optional sparks: " + "; ".join(chosen["sparks"]) + ".",
    ]
    if avoid:
        lines += ["Earlier ideas (do something clearly different):"] + ["- " + without_quotes(item) for item in avoid[-8:]]
    lines += [
        "",
        f"Write {count} different image concepts based on the draft. Each concept is one sentence of 15 to 30 words that "
        f"names the subject, what happens, where, and the new element. Every concept keeps the same main subject; never "
        f"replace it with a different creature, person or object. Concepts are purely visual: no dialogue, speech or "
        f"written words unless the draft has them. Number them 1 to {count}.",
    ]
    system = ("You are a visual concept artist. You invent fresh, specific image ideas and describe them plainly. "
              "Answer with exactly the requested numbered lines and nothing else.")
    return [{"role": "system", "content": system}, {"role": "user", "content": [{"type": "text", "text": "\n".join(lines)}]}]


def develop_messages(draft: str, exploration: str, detail: str, target_model: str, chosen: dict, concept: str) -> list[dict]:
    low, high = words_for(detail, draft)
    lines = ["Draft: " + draft]
    if concept:
        lines.append("Concept: " + concept)
    else:
        lines.append("Explore: " + " ".join(lens.instruction for lens in chosen["lenses"])
                     + " Optional sparks: " + "; ".join(chosen["sparks"]) + ".")
    lines += [
        "",
        "Write the final image prompt for this " + ("concept." if concept else "draft."),
        "Structure: " + chosen["structure"].instruction,
        f"Length: {_SENTENCES[detail]} sentences, {low} to {high} words in total.",
        "Keep " + _KEEP[exploration],
        'Quoted text stays exactly as written, inside quotation marks. Keep every "no" or "without" exclusion from the draft.',
        "Use concrete nouns, materials, colors, light and spatial positions. Do not use quality tags such as masterpiece, 8k, "
        "best quality or highly detailed. Do not mention the draft or the concept.",
    ]
    system = ("You write prompts for " + _TARGET[target_model] + ". You describe one finished image in vivid, concrete, visual "
              "language. Output only the prompt as one paragraph.")
    return [{"role": "system", "content": system}, {"role": "user", "content": [{"type": "text", "text": "\n".join(lines)}]}]


def parse_concepts(raw: str) -> list[str]:
    concepts = []
    for line in str(raw or "").splitlines():
        match = re.match(r"^\s*(?:\d+|[-*•])\s*[.):\-]?\s+(.+)$", line)
        if not match:
            continue
        text = _LABEL.sub("", match[1]).strip().strip("*").strip().strip('"“”').strip()
        if len(text.split()) >= 5:
            concepts.append(text)
    return concepts


def stem(word: str) -> str:
    word = word.casefold()
    word = _ALIASES.get(word, word)
    for suffix in ("ing", "es", "ed", "s"):
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def content_words(text: str) -> set[str]:
    return {stem(word) for word in re.findall(r"[A-Za-z][A-Za-z'-]+", str(text or "")) if len(word) > 2 and word.casefold() not in _STOP}


def similarity(left: str, right: str) -> float:
    a, b = content_words(left), content_words(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def reuse(text: str, earlier: str, draft: str) -> float:
    """Share of an earlier idea's own additions (words not in the draft) that ``text`` repeats."""
    added = content_words(earlier) - content_words(draft)
    return len(added & content_words(text)) / len(added) if len(added) >= 3 else 0.0


def novelty(text: str, avoid: list[str], draft: str) -> float:
    return round(1.0 - max((reuse(text, item, draft) for item in avoid), default=0.0), 3)


def coverage(text: str, draft: str) -> float:
    source = content_words(draft)
    return len(source & content_words(text)) / len(source) if source else 1.0


def rank_concepts(concepts: list[str], avoid: list[str], draft: str, exploration: str, rng_state: int) -> list[tuple[str, float]]:
    """Concepts that keep the subject first, then those repeating the least of earlier ideas; ties in seeded order."""
    order = list(range(len(concepts)))
    random.Random(rng_state).shuffle(order)
    floor = _COVERAGE[exploration] * 0.75
    # Novelty and coverage are compared in steps of 0.1; among equals the most transformed concept (least like
    # the draft) wins, because a small model tends to list its safest, most literal idea first.
    scored = sorted(
        (coverage(concepts[index], draft) < floor, -round(novelty(concepts[index], avoid, draft), 1),
         -round(coverage(concepts[index], draft), 1), round(similarity(concepts[index], draft), 2), position, index)
        for position, index in enumerate(order)
    )
    return [(concepts[index], novelty(concepts[index], avoid, draft)) for *_, index in scored]


def bias_words(avoid: list[str], draft: str, limit: int = 30) -> list[str]:
    """Additions that recur in two or more earlier ideas (one per entry) and are not in the draft or overused."""
    from collections import Counter

    keep = content_words(draft)
    counts = Counter(word for item in avoid for word in {
        raw.casefold() for raw in re.findall(r"[A-Za-z][A-Za-z'-]+", item)
        if len(raw) > 3 and raw.casefold() not in _STOP and stem(raw) not in keep
    })
    overused = set(OVERUSED)
    return [word for word, count in counts.most_common() if count >= 2 and word not in overused][:limit]


def clean_idea(raw: str, truncated: bool) -> tuple[str, list[str]]:
    text = re.sub(r"(?is)<think>.*?(?:</think>|$)", "", str(raw or ""))
    if _CONTROL.search(text):
        raise RuntimeError("The prompt model returned control markers instead of a prompt; try again")
    text = _LABEL.sub("", text.strip())
    text = re.sub(r"\s*\n+\s*", " ", text).strip()
    text = re.sub(r"\*\*|__|`", "", text).strip()
    if len(text) > 1 and text[0] in "\"“" and text[-1] in "\"”" and text.count('"') + text.count("“") <= 2:
        text = text[1:-1].strip()
    elif text[:1] in "\"“" and (text.count('"') + text.count("“") + text.count("”")) % 2:
        text = text[1:].strip()  # an opening quote whose closing one was cut off
    text = _FILLER.sub("", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r",\s*,", ",", text).strip(" ,")
    warnings = []
    if truncated:
        end = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
        if end >= len(text) * 0.6:
            text = text[: end + 1]
        else:
            warnings.append("Token limit reached; the ending may be cut short")
    return text, warnings


def restore_quotes(text: str, draft: str) -> tuple[str, list[str]]:
    """Required display text is re-attached verbatim when the model dropped or changed it."""
    labels = [next(part for part in match.groups() if part) for match in _QUOTES.finditer(draft)]
    missing = [label for label in labels if '"' + label + '"' not in text and "“" + label + "”" not in text]
    for label in missing:
        text = text.rstrip() + ("" if text.rstrip().endswith((".", "!", "?")) else ".") + f' The words "{label}" are clearly visible.'
    return text, missing


def invented_text(text: str, draft: str) -> list[str]:
    """Quoted words in the idea that the draft did not ask for (image models will try to render them)."""
    wanted = {next(part for part in match.groups() if part).casefold() for match in _QUOTES.finditer(draft)}
    return [label for label in (next(part for part in match.groups() if part) for match in _QUOTES.finditer(text))
            if label.casefold() not in wanted]


def assess(text: str, draft: str, exploration: str, detail: str, avoid: list[str]) -> dict:
    words = len(text.split())
    kept = coverage(text, draft)
    fresh = novelty(text, avoid, draft)
    issues = []
    if words < words_for(detail, draft)[0] * 0.5:
        issues.append("too_short")
    if len(content_words(draft)) >= 2 and kept < _COVERAGE[exploration]:
        issues.append("lost_subject")
    if len(draft.split()) >= 8 and similarity(text, draft) >= 0.8:
        issues.append("echo")
    if avoid and fresh <= 0.4:
        issues.append("repeat")
    return {"words": words, "coverage": round(kept, 3), "novelty": fresh, "issues": issues,
            "invented_text": invented_text(text, draft)}

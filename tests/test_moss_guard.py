"""The temporary v2 output guard, on outputs of realistic length (about 250 words)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = types.ModuleType("psn_upscaler")
PACKAGE.__path__ = [str(ROOT / "comfyui" / "upscaler")]
sys.modules.setdefault("psn_upscaler", PACKAGE)
for name in ("moss_guard", "moss_upsampler"):
    spec = importlib.util.spec_from_file_location(f"psn_upscaler.{name}", ROOT / "comfyui" / "upscaler" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
guard = sys.modules["psn_upscaler.moss_guard"]
moss = sys.modules["psn_upscaler.moss_upsampler"]

BODY = (
    "Full-color digital painting, eye-level wide shot of a lone knight standing on a windswept cliff above a stormy sea. "
    "The knight wears dented steel plate armor with brass rivets, a torn crimson cape and a dented round helm with a narrow visor. "
    "He grips a long sword planted point-down in the wet grass, both gauntleted hands resting on the pommel. "
    "Behind him, dark slate clouds roll across the sky, and a single shaft of pale light breaks through to the left, catching the edge of his shoulder plate. "
    "The sea below churns in heavy grey-green waves that crash against jagged black rocks, throwing white spray into the air. "
    "Tall grass and small yellow wildflowers bend sideways in the wind around his boots, and loose strands of his cape whip toward the right edge of the frame. "
    "In the middle distance a ruined stone tower leans on a far headland, its broken top silhouetted against the clouds. "
    "Rain streaks diagonally across the scene in thin silver lines, and puddles on the cliff path reflect the faint light. "
    "The palette is dominated by cold blues and greys with warm accents from the cape and the wildflowers. "
    "Brushwork is loose and painterly in the sky, tighter and more detailed on the armor, with visible strokes in the waves. "
)
assert 200 <= len(BODY.split()) <= 320, len(BODY.split())


def test_watermark_sentence_and_credit_line_are_removed():
    text = BODY + 'A small white watermark reads "ArtStation" in the lower right corner. Painted by Ross Tran, credit line in the margin.'
    out, report = guard.clean("a knight on a cliff, trending on artstation", text)
    assert "ArtStation" not in out and "watermark" not in out and "credit line" not in out
    assert out.startswith("Full-color digital painting") and "ruined stone tower" in out
    assert any("removed text" in line for line in report)


def test_unrequested_quoted_lettering_keeps_the_object():
    text = BODY + 'Above the tower a firework reads "your name" in bright gold sparks.'
    out, _ = guard.clean("a knight on a cliff with fireworks", text)
    assert "your name" not in out and "a firework" in out


def test_requested_text_is_left_alone():
    text = BODY + 'A neon sign reads "OPEN LATE" in red tubes above the door.'
    out, report = guard.clean('vintage diner neon sign reading "OPEN LATE" in heavy fog', text)
    assert out == text.strip() and report == []


def test_signature_brushwork_is_not_text():
    text = BODY + "The artist's signature brushwork gives the waves a restless rhythm."
    out, _ = guard.clean("a knight on a cliff", text)
    assert "signature brushwork" in out


def test_negation_tails_are_removed_unless_the_draft_asks_for_absence():
    text = BODY.replace("on a far headland,", "on a far headland, with no modern signage or electronics present,")
    out, report = guard.clean("1890s knight on a cliff", text)
    assert "modern signage" not in out and "negation" in report[0]
    kept, _ = guard.clean("a knight on a cliff without a helmet", text)
    assert "modern signage" in kept


def test_black_and_white_drafts_lose_color_words_and_gain_the_prefix():
    out, report = guard.clean("black-and-white photo of a knight on a cliff at blue hour", BODY + "It is the blue hour.")
    assert "crimson" not in out and "yellow" not in out and "blue hour" in out
    assert out.startswith("Black-and-white photograph.") and "prefixed black-and-white" in report


def test_cleaning_that_removes_too_much_returns_the_original():
    text = 'A watermark reads "X". A caption reads "Y". Lettering covers it. A knight.'
    out, report = guard.clean("a knight", text)
    assert out == text and report == [guard.SKIPPED]


def test_provenance_tokens_are_replaced_with_their_visual_meaning():
    assert guard.prep("a castle, trending on ArtStation, 8k, unreal engine 5") == (
        "a castle, polished concept art, ultra-detailed, crisp high-detail 3D render"
    )
    assert guard.prep("a castle by Greg Rutkowski") == "a castle by Greg Rutkowski"


class SeqClip:
    """Fake CLIP returning a different take per generate call."""

    def __init__(self, texts):
        self.texts, self.seeds, self.sent = list(texts), [], None
        vocab = {"<|im_end|>": 248046, "<|endoftext|>": 248044}
        inner = SimpleNamespace(tokenizer=SimpleNamespace(get_vocab=lambda: vocab))
        self.tokenizer = SimpleNamespace(clip="qwen35_2b", qwen35_2b=inner)

    def tokenize(self, text, **kwargs):
        self.sent = text
        return {"qwen35_2b": [[(1, 1.0)] * 9]}

    def generate(self, tokens, **kwargs):
        self.seeds.append(kwargs["seed"])
        return [len(self.seeds), 248046]

    def decode(self, ids):
        return self.texts[ids[0] - 1]


REFUSED = 'A watermark reads "X". A caption reads "Y". Lettering covers it. A knight.'


def test_one_take_is_written_when_the_guard_can_clean_it():
    dirty = BODY + 'A watermark reads "ArtStation".'
    clip = SeqClip([dirty, BODY])
    text, info = moss.upsample(clip, "a knight on a cliff, trending on artstation", seed=10, max_takes=2)
    assert clip.seeds == [10] and "watermark" not in text and text.startswith("Full-color digital painting")
    assert clip.sent == "a knight on a cliff, polished concept art" and info["guard"]["prepped"] is True
    assert info["guard"]["takes"] == [{"seed": 10, "defects": 2, "words": len(dirty.split()), "refused": False}]


def test_a_refused_take_is_retried_with_the_next_seed():
    clip = SeqClip([REFUSED, BODY])
    text, info = moss.upsample(clip, "a knight", seed=10, max_takes=2)
    assert clip.seeds == [10, 11] and text == BODY.strip() and info["upsample"]["seed"] == 11
    assert [take["refused"] for take in info["guard"]["takes"]] == [True, False] and not info["warnings"]


def test_when_every_take_is_refused_the_least_defective_comes_back_with_a_warning():
    worse = REFUSED + ' Signed by the artist. A wordmark reads "Z".'
    clip = SeqClip([worse, REFUSED])
    text, info = moss.upsample(clip, "a knight", seed=3, max_takes=2)
    assert clip.seeds == [3, 4] and text == REFUSED and info["guard"]["report"] == [guard.SKIPPED]
    assert any("try another take" in warning for warning in info["warnings"])


def test_max_takes_one_never_retries():
    clip = SeqClip([REFUSED, BODY])
    text, _ = moss.upsample(clip, "a knight", max_takes=1)
    assert clip.seeds == [0] and text == REFUSED


def test_greedy_runs_once_and_the_guard_can_be_turned_off():
    dirty = BODY + 'A watermark reads "ArtStation".'
    clip = SeqClip([dirty, dirty])
    text, info = moss.upsample(clip, "a knight, 8k", temperature=0, max_takes=3)
    assert len(clip.seeds) == 1 and "watermark" not in text and info["guard"]["raw"] == dirty.strip()
    clip = SeqClip([dirty])
    text, info = moss.upsample(clip, "a knight, 8k", guard=False)
    assert "watermark" in text and clip.sent == "a knight, 8k" and info["guard"]["enabled"] is False


# Sentences from live v2 takes (2026-11-22) that the first guard version cleaned badly.
def test_every_quoted_item_after_the_verb_goes():
    text = BODY + 'Brick shopfronts line the lower background, with boarded windows, hanging lanterns, and small signs reading "COFFEE" and "CIGARS".'
    out, _ = guard.clean("a busy 1890s london street with horse carriages", text)
    assert out.endswith("hanging lanterns, and small signs.") and "CIGARS" not in out


def test_apostrophes_inside_double_quotes_do_not_break_the_match():
    text = BODY + 'On the left, a row of brick shops has awnings, hanging signs reading "LADIES\' DRESS", "CLOTHING", and "FURNITURE", with glass windows displaying coats and hats.'
    out, _ = guard.clean("a busy 1890s london street with horse carriages", text)
    assert '"' not in out and "DRESS" not in out
    assert out.endswith("hanging signs, with glass windows displaying coats and hats.")


def test_described_letters_count_as_visible_text():
    text = BODY + 'Overhead signs read "SUBWAY" in bold uppercase letters, with smaller illegible fare information below.'
    out, _ = guard.clean("black and white photo of a crowded subway car at rush hour", text)
    assert "uppercase letters" not in out and "SUBWAY" not in out
    assert guard.defects("a subway car", "Gold letters spell the name.") == 1

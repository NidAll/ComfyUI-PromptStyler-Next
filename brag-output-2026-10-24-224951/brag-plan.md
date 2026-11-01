# Brag Plan: PromptStyler Next

## What is this app?

A modular creative styling platform for ComfyUI, HEISS Studio, and standalone
Python: it keeps your subject text intact, layers curated visual styles onto it,
and formats the result in the prompting convention your specific model expects —
while showing you every clause it applied, suppressed, or skipped.

## The angle

Prompt styling is normally a slot machine: you paste a tag, something happens,
and you have no idea what changed. PromptStyler Next is the opposite — a
deterministic engine with a receipt. The film is built around that receipt.

The creative premise: **treat the transformation trace like forensic evidence.**
Cinematic scale, big type, real UI, and then the payoff — the screen where the
product quietly lists what it did and why. Most tools hide the diff. This one
puts it on the front page under the words "See what changed."

Second premise, held throughout: **the subject never moves.** The styled prompt
repeats the user's own sentence verbatim and appends. That's the promise the
tagline makes — "Keep your idea. Shape its visual language." — and the film
proves it visually rather than saying it twice.

## Hook (first 2-3 seconds)

Ink-black frame. A monospace prompt types fast onto it:
`A quiet bookshop on a rainy evening, a reader beside the window`

Then the append lands: rust-colored clauses materialize after the comma —
`black and white`, `silver monochrome`, `soft highlight diffusion`. The user's
own words never dim or move.

Display line slams in on the beat: **"Your words stay."**

That is the whole product thesis in three words, demonstrated before it's
claimed.

## Key moments (the middle)

- **The number.** 1,164 real entries land as a huge plate numeral while actual
  catalog cards drift past behind it — the real cards, with their real
  descriptions and terrazzo swatches.
- **The recipe.** The real "Your recipe" panel: two named layers, intensity
  sliders at 75%, precedence arrows. Type: "Up to sixteen layers."
- **The same recipe, two languages.** Left plate (ink): the real SDXL tag output.
  Right plate (paper): the real Fibo 2 structured caption JSON, keys color-coded.
  One recipe in, two native syntaxes out. Type: "Same recipe. The model's own
  language."
- **The receipt.** Real trace rows typed in mono, stamped with their real verdicts
  — `applied`, `suppressed`, `skipped` — each with the engine's real reason
  ("Axis protected by the recipe…", "Conflicting claim replaced by
  cinema.softfocus under last_wins."). Under it, the real fingerprint.

## Outro / punchline

Back to ink. The wordmark lands with a bell. Tagline: "Keep your idea. Shape its
visual language." Below it, the three surfaces: "ComfyUI · HEISS Studio · Python".

Last visible detail, small and mono: `1,164 entries · 52 packs · offline`.

## User flow worth showing

entry → key action → result, taken from the real workbench:

1. **Entry** — subject typed into "Start with your subject"; model profile chosen.
2. **Key action** — two styles added from "The style library" into "Your recipe";
   a protected axis is checked; "Compose prompt" is pressed.
3. **Result** — "See what changed": composed prompt plus transformation trace.

All three beats are shown from actual screenshots of the running workbench, not
recreations.

## Tone

- Preset: `cinematic`
- Creative direction: "forensic product film — a receipt for a prompt; quiet
  authority, big scale, no hype"
- Interpretation: long lenses and slow pushes rather than fast cuts; hard cuts
  land on beats; type is large and sparse; each scene states one thing and holds
  it. No exclamation, no adjectives doing the work numbers should do. Sound is a
  restrained bed with three decisive hits.

## Format: landscape — 1920x1080
## Duration: 20.0s (30 fps)

## Visual identity (from the project)

- Background: `#f5f1eb` (paper), `#e8e4dc` (paper-2), `#fefdfb` (plate)
- Ink: `#0f0d0b`, secondary `#292624`, muted `#544f4a`
- Accent: `#a33810` (rust), soft `#f6dbcf`
- Rule/hairline: `#bbb7af`
- Swatches: `#202d37`, `#b28e5c`, `#dad0bd`, `#955640`, `#99ae99`, `#1e4c3a`
- Display font: the workbench renders Syne falling back to Arial Black; on screen
  that is a heavy grotesque — use **Archivo Black** to match the real rendering.
- Body font: Onest falling back to system-ui — use **Inter** 400/700.
- Mono: **JetBrains Mono** (the project's own declared code face, bundled).
- Strongest visual elements: the terrazzo swatch triplets, the 2px ink masthead
  rule, the black "Compose prompt" bar, the truncated mono fingerprint, and the
  rust intensity slider.

## Share copy (draft)

Every style layer leaves a receipt: what was applied, what was suppressed, and
why. 1,164 entries, 11 model profiles, zero runtime dependencies — PromptStyler
Next.

## Audio direction

- Role: cinematic support — one steady bed, three decisive hits, nothing else.
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (steady and
  clean; the `polished`/`cinematic` track). 109.96 BPM.
- Music treatment: start at 0.0s at 0.30, no fade-in ramp beyond 0.12s; hold flat;
  fade out over the final 0.9s under the logo card.
- Music cue guidance: bundled preset read —
  `assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`.
  Strong-cue locks (within ±0.15s):
  1. **3.27s** — the hook's display line / cut to the library.
  2. **10.93s** — the model-language reveal (the film's centrepiece).
  3. **17.47s** — the logo card lands.
  Beat grid for sequential events — 1.09, 1.64, 2.19 (clause appends);
  14.20, 14.73, 15.29, 15.84 (trace rows).
- Audio-reactive treatment: subtle; the rust accent glow behind the library
  numeral and a soft paper vignette breathe with RMS/bass. No waveform or
  equalizer graphics, no text scaling.
- SFX posture: sparse; motion-matched; three big hits and a handful of dry
  UI accents.
- Audio-coupled moments: typing of the prompt (key ticks), the three clause
  appends (soft ticks), the numeral settling (one bell), the trace rows landing
  (four dry clicks, first and last only audible enough to group them), the final
  logo (deep bell).
- Restraint rule: no whooshes on every cut, no riser, nothing that competes with
  the mono text being read. Silence between hits is part of the tension.

## Storyboard

### Scene 1 — The receipt begins — 3.27s
Ink ground, full frame. A single hairline rust rule at 12% width draws leftward.
Eyebrow, top-left, mono, letterspaced: `PROMPTSTYLER NEXT`.
The real default subject types onto the frame in JetBrains Mono:
`A quiet bookshop on a rainy evening, a reader beside the window`
Label above it, muted: `YOUR PROMPT`.
At 1.09s the append begins: `, black and white` lands in rust; 1.64s
`, silver monochrome`; 2.19s `, soft highlight diffusion`. The base text never
shifts or dims.
Display line arrives at 2.55s, Archivo Black, paper white, tracking -2%:
**"Your words stay."**
Sequential/interaction: yes — prompt types character by character (~0.9s), then
three clauses append on consecutive beats (1.09 / 1.64 / 2.19), each with a
small rust caret flash.
Audio intent: intimate, precise, a little tense — the sound of instrumentation.
Audio-coupled idea: randomized keypress ticks for typing; a dry tick per clause.
Music: bed enters immediately, low.
Transition mood: hard cut → Scene 2.

### Scene 2 — 1,164 — 3.29s
Paper ground blooms in (warm paper, not white). Two real catalog cards
("Silver-screen noir", "Diffusion-filter romance") drift slowly behind at low
contrast, slightly scaled and blurred — depth, not decoration.
Centre: a giant `1,164` in Archivo Black at ~420px, counting from 0 over 0.8s and
settling on the beat.
Under it: `entries across 52 packs.`
Smallest line: `1,017 styles · 69 grades · 78 modifiers · offline · zero runtime dependencies`
Sequential/interaction: yes — the numeral counts up, then the caption lines fade
in beneath it in one block (held, not staggered, so it can be read).
Audio intent: the film opens up; scale arrives.
Audio-coupled idea: counter ticks thin out and stop as it lands; one soft-medium
impact at settle.
Music: bed continues.
Transition mood: hard cut → Scene 3.

### Scene 3 — Up to sixteen layers — 3.27s
Paper-2 ground. The real "Your recipe" panel slides in from the right at 105%
scale settling to 100%, clipped by a hard ink rule.
Its two layers are already present: "1. Silver-screen noir", "2. Diffusion-filter
romance", each at 75%.
Display line, left, over paper: **"Up to sixteen layers."**
Sub, muted, one line: `Order sets precedence. Intensity sets specificity.`
As the panel settles, the two intensity sliders animate 0→75% in rust, and layer 2
nudges up 6px to suggest reordering.
Sequential/interaction: yes — panel push-in, then the two sliders fill in sequence.
Audio intent: mechanical, satisfying, hands-on.
Audio-coupled idea: two dry slider fills, 0.18s apart on the beat grid.
Music: bed continues.
Transition mood: hard cut → Scene 4.

### Scene 4 — The model's own language — 3.81s
Split frame, hard vertical seam at centre, no easing.
Left half: ink plate. Header mono `SDXL · TAGS`. Below it, the real tag output,
typewriter, wrapping:
`black and white, silver monochrome, soft highlight diffusion, highlight spread, readable detail`
Right half: paper plate. Header mono `FIBO 2 · STRUCTURED`. The real structured
caption types in, JSON keys in rust, values in ink:
`{"aesthetics":{"color_scheme":"Use a black-and-white silver palette"},"artistic_style":"Keep soft highlight spread over an otherwise readable image","lighting":{"conditions":"Wrap the existing highlights in a gentle luminous veil"},"short_description":"A quiet bookshop on a rainy evening, a reader beside the window"}`
Display line spans the seam above, Archivo Black, on a paper bar that cuts across
both plates: **"Same recipe. The model's own language."**
Small caption bottom-right, muted: `11 model profiles`
Sequential/interaction: yes — both panels type in parallel; the SDXL side lands
first (shorter), the Fibo side lands second; the display bar sweeps across the
seam last.
Audio intent: the reveal. The film's biggest idea.
Audio-coupled idea: beat-locked reveal at 10.93s; a bell under the bar sweep.
Music: bed continues; this is the strong cue.
Transition mood: hard cut → Scene 5.

### Scene 5 — See what changed — 3.83s
Ink ground. Heading, paper white: **"See what changed."**
Four real trace rows land one at a time, mono, each a verdict stamp plus its real
reason:
1. `skipped` — `medium · Axis protected by the recipe or an existing structured-caption field.`
2. `suppressed` — `lighting · Conflicting claim replaced by cinema.softfocus under last_wins.`
3. `applied` — `palette · Shared clause rendered by the model adapter.`
4. `applied` — `texture · Shared clause rendered by the model adapter.`
Verdicts are color-coded: skipped = muted, suppressed = rust, applied = sage
`#99ae99`. Each row gets a thin rule above it, like a ledger.
Bottom: the real truncated fingerprint, mono, muted:
`Catalog 10375da75df6`
Sequential/interaction: yes — four rows land on the beat grid
(14.20 / 14.73 / 15.29 / 15.84), held together after the last so they can be read.
Audio intent: quiet authority. The receipt is the flex.
Audio-coupled idea: one dry click per row, first and last slightly louder.
Music: bed continues.
Transition mood: hard cut → Scene 6.

### Scene 6 — Logo card — 2.53s
Ink ground. A single rust hairline draws across the full width.
The wordmark **PromptStyler Next** lands in Archivo Black, paper white, at
17:47 on the bell.
Tagline under it, Inter: `Keep your idea. Shape its visual language.`
Surfaces, muted, letterspaced: `COMFYUI · HEISS STUDIO · PYTHON`
Smallest line, mono: `1,164 entries · 52 packs · offline`
Music fades out under the card; the bell rings over it.
Transition mood: end on the card, no fade to black beyond the last 0.2s.

**Music mood for this video:** cinematic, warm, restrained — steady forward
motion, three decisive accents.
**Audio summary:** a low steady bed from frame one, keypress texture in the dark,
one bell as the library opens, one decisive hit as the same recipe splits into two
model languages, dry ledger clicks through the trace, and a final bell under the
wordmark while the music fades away.

## Composition notes

- Every screenshot used is from the local workbench running on 127.0.0.1:8791,
  captured at 2× device scale: masthead, real catalog cards, real recipe panel,
  real inspection panel, real model-profile control.
- All product copy, numbers, style names, composed prompts, trace reasons and the
  fingerprint are real engine output. Nothing is mocked.
- No personal data, hostnames, hardware details, or filesystem paths appear
  anywhere in the film.

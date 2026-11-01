# Hyperframes Composition Brief: PromptStyler Next

## Objective

Create a 20-second cinematic launch film for PromptStyler Next, built around the
product's transformation trace — the receipt that shows what each style layer did
to a prompt.

## Output

- Composition directory: `brag-output-2026-10-24-224951/composition/`
- Rendered video: `brag-output-2026-10-24-224951/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 20.0 seconds at 30 fps

## Source Material

- Project root: `/home/nidall/AI/ComfyUI/custom_nodes/ComfyUI-PromptStyler-Next`
- Primary files read: `promptstyler_next/web/index.html`,
  `promptstyler_next/web/styles.css`, `promptstyler_next/web/app.mjs`,
  `README.md`, `promptstyler_next/engine.py`, `promptstyler_next/service.py`,
  `promptstyler_next/packs/*.json`
- Product name: PromptStyler Next
- Tagline / strongest claim: "Keep your idea. Shape its visual language." and the
  UI section heading "See what changed."
- Key UI or visual moment to recreate: the workbench itself — "The style library"
  beside "Your recipe", and the "See what changed" inspection panel with the
  transformation trace.

### Real assets captured from the running product

All captured with Playwright at 2× device scale from the local service on
127.0.0.1:8791, at a 1920x1080 viewport:

| File | What it is |
| --- | --- |
| `assets/img/app-top-1920.png` | Full viewport: masthead, "Start with your subject", real prompt, SDXL profile, protected medium axis, "The style library" (1164 entries), "Your recipe" with 2 layers at 75% |
| `assets/img/app-workspace-1920.png` | Workspace band: real catalog cards and the recipe column |
| `assets/img/app-inspection-1920.png` | "See what changed": real composed prompt and the real footer fingerprint `Catalog 10375da75df6` |
| `assets/img/cards-row.png` | Two real catalog cards, tightly cropped |
| `assets/img/recipe-tight.png` | Real "Your recipe" panel, tightly cropped |
| `assets/img/fibo-inspection-1920.png` | (reference only) same panel with Fibo selected |

### Copy that must appear verbatim

- `A quiet bookshop on a rainy evening, a reader beside the window` (the
  workbench's own default subject)
- `black and white, silver monochrome, soft highlight diffusion, highlight spread, readable detail`
  (real SDXL tag output)
- The real Fibo 2 structured caption:
  `{"aesthetics":{"color_scheme":"Use a black-and-white silver palette"},"artistic_style":"Keep soft highlight spread over an otherwise readable image","lighting":{"conditions":"Wrap the existing highlights in a gentle luminous veil"},"short_description":"A quiet bookshop on a rainy evening, a reader beside the window"}`
- Real trace verdicts and reasons:
  - `skipped` — `Axis protected by the recipe or an existing structured-caption field.`
  - `suppressed` — `Conflicting claim replaced by cinema.softfocus under last_wins.`
  - `applied` — `Shared clause rendered by the model adapter.`
- Numbers: `1,164`, `52 packs`, `1,017 styles`, `69 grades`, `78 modifiers`,
  `11 model profiles`, `Up to sixteen layers.`
- `Keep your idea. Shape its visual language.`
- `See what changed.`
- `ComfyUI · HEISS Studio · Python`

## Creative Direction

- Tone preset: `cinematic`
- Creative direction: "forensic product film — a receipt for a prompt"
- Interpretation: slow pushes and big type, hard cuts landing on beats, one
  statement per scene, no hype adjectives. Scale and sound carry the drama; the
  UI stays crisp and unretouched.
- Angle: prompt styling is normally a slot machine. This one hands you the
  receipt — every clause marked applied, suppressed, or skipped, with its reason.
- Hook: a prompt typing in the dark, then rust-colored clauses appending while
  the user's own words never move. Line: "Your words stay."
- Outro / punchline: wordmark on ink, tagline, the three surfaces.
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals
  - Unrelated visual redesign
  - Glow, gradients or chrome that isn't in the project's own palette

## Visual Identity

- Background: `#f5f1eb` (paper), `#e8e4dc` (paper-2), `#fefdfb` (plate)
- Text: `#0f0d0b` (ink), `#292624` (ink-2), `#544f4a` (muted)
- Accent: `#a33810` (rust); soft `#f6dbcf`
- Rule: `#bbb7af`; applied-verdict green `#99ae99` (real swatch E)
- Display font: Archivo Black (bundled) — matches how the workbench's Syne
  actually renders on an offline machine (Arial Black fallback)
- Body font: Inter 400/700 (bundled)
- Mono font: JetBrains Mono (bundled; the project's own declared code face)
- Visual references from the project: the 2px ink masthead rule, terrazzo swatch
  triplets, the black "Compose prompt" bar, the rust intensity slider, the
  truncated mono fingerprint, the hairline ledger rules of the trace list.

LOOK line: warm terrazzo paper `#f5f1eb` ground against ink `#0f0d0b` plates,
one rust `#a33810` accent at full saturation for every focal mark, 2px hairlines
`#bbb7af`, Archivo Black display at 92–420px with -0.03em tracking, Inter 400 at
28–34px, JetBrains Mono 22–28px for all engine data, 40px frame gutter, zero
gradients, zero glow except the one audio-reactive accent halo. Banned: Inter as
display, Space Grotesk, purple/blue tech gradients, glassmorphism, drop shadows
on type.

## Storyboard

Use `brag-plan.md` as the creative contract.

Scene summary:
1. **The receipt begins** — 3.27s — prompt types, three rust clauses append, "Your words stay."
2. **1,164** — 3.29s — giant numeral over real catalog cards, "entries across 52 packs."
3. **Up to sixteen layers** — 3.27s — real workbench viewport with a slow push, recipe column; display line.
4. **The model's own language** — 3.81s — split ink/paper plates, real SDXL tags vs real Fibo structured caption, "Same recipe. The model's own language."
5. **See what changed** — 3.83s — ink ground, four real trace rows land on beat, real fingerprint.
6. **Logo card** — 2.53s — wordmark, tagline, three surfaces.

## Audio

- Audio role: cinematic support — steady bed, three decisive hits.
- Audio arc: bed enters with the typing, a soft-medium impact as the library
  opens, a bell on the model reveal, dry ledger clicks through the trace, a final
  bell under the wordmark while music fades away.
- Music: `assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3`
- Music treatment: `data-start="0"`, `data-volume="0.30"`, fade-in 0.12s,
  fade-out over the last 0.9s.
- Music cue guidance: bundled preset at
  `assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`
  (109.96 BPM). Strong-cue locks: **3.27s**, **10.93s**, **17.47s**.
  Beat grid: 1.09 / 1.64 / 2.19 for clause appends; 14.20 / 14.73 / 15.29 / 15.84
  for trace rows.
- Audio-reactive treatment: subtle — the rust accent halo behind the library
  numeral and a paper-grain warmth on the ground breathe with RMS/bass. No
  waveform or equalizer graphics, no text scaling. Data extracted to
  `assets/music/audio-data.json` (30 fps, 8 bands).
- Audio-coupled moments:
  - Scene 1 — typing key ticks, one dry tick per clause append.
  - Scene 2 — counter ticks thinning out, one soft-medium impact on settle.
  - Scene 4 — beat-locked bell on the split reveal.
  - Scene 5 — one dry click per trace row.
  - Scene 6 — deep bell under the wordmark.
- SFX selection guidance: `impact/impactBell_heavy_000` and `_003` for the two
  bells; `impact/impactSoft_medium_001` and `_003` for the library; interface
  clicks for clause appends and trace rows; `keyboard/keypress-*` for typing.
  Keep key ticks quiet (0.28–0.38) since they repeat.
- Exact SFX choice, timestamps and density: Hyperframes decides from the
  implemented animation.
- Audio files: copied into `assets/music/` and `assets/sfx/`.

## Hyperframes Instructions

Load the composition-building Hyperframes skills — `hyperframes` (contract +
`references/format.md`, `references/motion.md`, `references/look.md`),
`hyperframes-registry`, `media-use`, `hyperframes-cli`. `/brag` is its own
workflow: skip the `hyperframes` storyline step — no `references/types/*`, no
`references/story.md`, no `SPEC.md`. Also skip `usage`, `history`, `feedback` and
REVIEW.md; `check` is brag's gate.

Requirements:
- Show real project visuals: scenes 2 and 3 full-bleed real workbench screenshots,
  and all engine data on screen copied from real output.
- Keep all text readable in the final render.
- Stay within 15-25 seconds; the root is 20.0s.
- Include the planned music/SFX layer.
- Do not add captions or a voiceover — the user asked for none.
- Keep creation and rendering local.

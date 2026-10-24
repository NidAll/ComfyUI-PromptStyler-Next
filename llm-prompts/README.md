# Base prompt toolkit

Copy one of the `.txt` prompts into an LLM and replace its final input block with
your request. Paste the resulting **base prompt** into PromptStyler Next. These
files are reusable authoring instructions; the engine does not call an LLM.

| Start from | Copy this file | Result |
| --- | --- | --- |
| An idea | [01-create-base.txt](01-create-base.txt) | One portable semantic description |
| A prompt with a look baked in | [02-neutralize-prompt.txt](02-neutralize-prompt.txt) | Content with optional art direction removed |
| A reference image | [03-describe-reference.txt](03-describe-reference.txt) | Visible content for a vision-capable LLM |
| An underspecified scene | [04-expand-scene.txt](04-expand-scene.txt) | More concrete content, with additions explicitly opt-in |
| A reference-based edit | [05-edit-instruction.txt](05-edit-instruction.txt) | The requested change and preservation constraints |
| A base that needs checking | [06-audit-base.txt](06-audit-base.txt) | Base, deferred style requests and fidelity notes |
| A base and known catalog IDs | [07-build-recipe.txt](07-build-recipe.txt) | A validated-contract-shaped recipe for later validation |

The audit output is an authoring report, not a node input. Copy only its
`base_prompt` field. A recipe produced by an LLM still needs engine validation;
its shape alone does not make it valid.

## The handoff

```text
Idea or reference -> LLM semantic base -> PromptStyler Next style layers
                 -> styled positive output -> the model's native encoder
```

The Style node takes the base as its prompt. Compose Recipe accepts the same
base in `prompt`, or through its connected advanced STRING input. That connected
input replaces only the recipe's prompt. Keep image references, seed, image size,
LoRAs and sampling settings in the workflow. No metaprompt text belongs in the
node's prompt field.

```text
Two bicycle mechanics stand beside one cargo bicycle. The mechanic on the left
holds the front wheel while the other adjusts the rear rack. A sign on the wall
reads "REPAIR 7". Both mechanics and the entire bicycle are visible.
```

This base says what must exist and how it relates. It leaves rendering medium,
artistic light, global palette, surface process and mood available to the presets.
It does not tell the model to make a photograph, an anime image or a painting.

## Content that should stay in the base

Retain entity counts, action, identity, necessary materials and colors, relative
positions, actual weather, required framing and exact text. A red life jacket,
rain that drives the action, or a sign's words are content constraints. A global
teal grade, cinematic light or watercolor medium are optional art direction.
Do not remove meaningful facts just to make a prompt sound neutral. Avoid adding
nonessential facts that would unnecessarily constrain every preset.

Keep the same base when comparing styles or profiles. Most scenes need a few
clear sentences; complex spatial relationships need more. There is no universal
token target. See [the sample corpus](examples/base-scenes.json) for different
levels of complexity and [replay recipes](examples/).

## What the node can protect

The engine preserves user prose verbatim; it does not understand arbitrary
contradictions in it. The seven style axes are `medium`, `lighting`, `palette`,
`composition`, `texture`, `mood` and `detail`. Bundled clauses now declare the
axes they own, so layer order can resolve competing instructions deterministically.
For example, a later grade replaces a preset's palette without removing its medium.

Use `locked_axes` only when the user has a corresponding non-negotiable constraint.
Lock `palette` when a specified identity color must survive a monochrome preset;
lock `composition` when a diagram's layout must remain fixed. A lock suppresses
style clauses on that whole axis. It does not parse a color name, preserve pixels,
or guarantee that the model follows a count. For exact text, avoid destructive
texture effects or protect `texture`/`detail` when required. The Information
Hierarchy pack provides gentler alternatives; its instructions remain model-dependent.

Start with one visual treatment at intensity 0.5–0.8, inspect the output, then add
a grade or a finishing modifier. Thresholds switch authored clauses on and off;
intensity is not a continuous strength multiplier. Some looks intentionally
change perspective or abstraction. Lock the relevant axis or choose another look
when those changes conflict with the scene. Higher intensity is not inherently
better, and stacking more full looks does not inherently improve quality.

## Profiles and native formatting

| Exact profile | Base and output handoff |
| --- | --- |
| `sdxl` | Prose or supplied tags in; styled text to compatible SDXL encoding |
| `flux` | Prose in; styled prose to the actual FLUX encoder |
| `qwen-image`, `qwen-image-2.1` | Prose in; native Qwen encoder and reference workflow |
| `moss-image`, `moss-image-dmd` | Prose in; MOSS encoder; native Layout formatting separately if requested |
| `anima`, `anima-turbo` | Same semantic prose base; added clauses use spaced lowercase tags |
| `fibo` | Prose becomes `short_description` in the returned caption JSON; pass that JSON intact |
| `fibo-edit` | Edit instruction or supported caption JSON; keep native reference connections |
| `generic` | Conservative prose formatting when there is no dedicated profile |

Ming, Krea, Z-Image and Iris do not have dedicated profiles in this version. A
`generic` pass does not establish native schema or conditioning support. If a
workflow needs a model-specific layout or wrapper, build it from the **styled**
output afterward. Do not feed an arbitrary bbox/layout JSON into the plain-prose
path, and do not wrap Fibo's output a second time.

## Evidence and limits

This separation is the project's design choice, informed by the models' actual
interfaces. BFL's [official image prompting guidance](https://github.com/black-forest-labs/skills/blob/master/skills/flux-image-best-practices/SKILL.md)
supports descriptive prose and explicitly quoted text. The [MOSS author guide](https://github.com/OpenMOSS/MOSS-Image/blob/main/USERGUIDE.md)
supports prose, tags and a separate Layout interface; explicit line breaks can
help text layout. [Anima's model card](https://huggingface.co/circlestone-labs/Anima)
supports mixed captions/tags and describes limitations in realism and lengthy
text. [Qwen's model card](https://huggingface.co/Qwen/Qwen-Image) documents image
generation, editing and multilingual text rendering. These capabilities motivate
the handoff choices; they do not prove optimal settings for every checkpoint.

A portable base reduces prompt conflicts. It cannot make every preset suitable
for every scene, or make every architecture equally good at the same output.
Photographic packs remain excluded from Anima. Text-heavy bases will stress its
documented limitations. Some shape transformations deliberately trade fidelity
for abstraction. No image-quality grid or LLM-output benchmark is supplied by this
toolkit; [the pack review](../docs/style-review.md) and automated checks establish
data/composition behavior, not perceptual quality.

The original prompt text and sample scenes in this directory are CC0-1.0 under
[STYLE-LICENSE](../STYLE-LICENSE). Research links retain their own terms.

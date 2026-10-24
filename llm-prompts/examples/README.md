# Replay examples

`base-scenes.json` is a frozen semantic corpus with human-authored facts. It is
not itself an engine recipe. Optional locks illustrate preservation tradeoffs;
the toolkit never applies them automatically.

Each `recipe-*.json` file is a standalone recipe. For example:

```sh
promptstyler-next compose llm-prompts/examples/recipe-flux.json
```

`recipe-fibo.json` produces caption JSON as the positive output; pass it intact
to the native Fibo encoder. `recipe-edit.json` produces an edit instruction and
still requires the reference-aware native editing workflow. `recipe-qwen.json`
keeps exact multilingual text in its base, which does not guarantee correct
rendering of those characters.

For a visual acceptance grid, reuse each base and the same seed within each
model/workflow. Compare styling bypassed, one style at 0.35/0.75/1, and that style
with one grade or modifier. Include a portrait, multiple people, a still life,
an impossible scene, exact text and an edit. Judge entity identity/count,
relationships, text, style distinctiveness and visible artifacts separately.
Record the actual checkpoint, encoder, recipe fingerprint, dimensions, seed,
sampling, CFG and LoRAs. Cross-model seeds are bookkeeping, not matched noise.

Honor the engine's model eligibility. A profile test checks serialized content,
not image quality. These examples have not been run as an image-generation grid
or through multiple LLMs; no synthetic quality score is implied.

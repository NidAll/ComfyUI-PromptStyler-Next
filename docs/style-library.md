# Style library

The built-in library contains original, independently authored visual treatments, color grades and creative modifiers. Code is Apache-2.0; all bundled style text is dedicated under CC0-1.0 in [STYLE-LICENSE](../STYLE-LICENSE). No legacy PromptStyler templates, artist identities or generated-image assets are copied into these packs.

The current collection has 1,003 entries in 49 packs: 867 visual treatments, 69 color grades and 67 effects (modifiers), plus 161 retired IDs that map to replacements where one exists. The audited reference library has 585 modern pack entries; the successor increases the count while giving each entry structured clauses, explicit composition claims and separate prose/tag renderings. The count is an inventory fact, not a visual-quality metric.

## What is covered

| Collection | Examples of distinct approaches |
| --- | --- |
| Cinematography | Silver-screen noir, motivated practical light, two-strip color, widescreen intimacy |
| Photography | Wet plate, platinum print, pinhole, cross-polarized materials, telephoto compression |
| Anime | Painted cels, OVA transfer, animation layout, fine-line key visuals, colored contours |
| Manga | Screentone, fude pen, white ink, scratchboard-like carving, tone-cut geometry |
| Illustration | Silverpoint, gouache, colored pencil, wax resist, quilled paper |
| Fine art | Tonalism, Fauvism, precisionism, Orphism, alla prima painting |
| Printmaking | Mezzotint, aquatint, drypoint, collagraph, pochoir, mokuhanga |
| Graphic design | Swiss order, Bauhaus construction, De Stijl, Art Deco, Gestalt closure |
| 3D and miniatures | Wax, bronze, filament layers, point clouds, stop motion, plaster casts |
| Architecture | Axonometric drawing, earthen volumes, Metabolist modularity, daylight models |
| Concept development | Whitebox blockouts, value keys, silhouette studies, material studies |
| Experimental | Chemigrams, slit scans, photograms, solarization, interlaced signal art |
| Documentary | Zone-system prints, everyday color, work prints, push and pull processing |
| Material studies | Embroidery, mosaics, lacquer, marquetry, ceramics, metal relief |
| Historical media | Encaustic, fresco, gold-ground panels, manuscript illumination, ceramic figures |
| Regional crafts | Technique-focused miniature painting, resist dyeing, tile and lacquer processes |
| Technical and mapping | Engineering drawing, cartographic representations and measured diagram languages |
| Editorial and wayfinding | Publication systems, informational graphics and navigational visual hierarchies |
| Culinary and botanical | Food-image craft, specimen representations and botanical observation |
| Performance and archival | Performance documentation, archival media and reproduction processes |
| Transport and tactile | Transport design communication and tangible surface treatments |
| Garden and land art | Designed-landscape and site-art representations |
| Jewelry and accessories | Small-object craftsmanship and presentation |
| Lettering and typography | Letterform-driven visual systems; supplied text remains the user's responsibility |
| Landscape and weather | Atmospheric and landscape representation choices |
| Fashion and textile | Garment presentation, drape and editorial material studies |
| Grades and modifiers | Sage-and-stone color, silver monochrome, raking light, selective focal detail |

### Community-origin collections

These 15 authored packs add 225 visual treatments. Their 45 color grades now live in
the shared Color set and their 30 effects in the shared Effects set (two retired).
Each pack is versioned and licensed CC0-1.0.

| Pack | Coverage |
| --- | --- |
| Analog horror | Broadcast interruptions, degraded institutional media and surveillance |
| Anime subgenres | Storytelling and production-language variants across anime |
| Brutalist graphic design | Raw typography, industrial signage, xerox and anti-design |
| Cozy nostalgia | Intimate domestic scenes and warmly remembered places |
| Dreamcore | Uncanny soft-focus memories and impossible familiar spaces |
| Editorial subcultures | Zines, streetwear, club flyers and alternative beauty editorials |
| Gaming eras | Distinct visual languages from 16-bit art through early 3D |
| Internet aesthetics | Vaporwave, mallsoft, Y2K interfaces and DIY web culture |
| Liminal spaces | Transitional, empty public and institutional environments |
| Occult and esoteric | Alchemical, hermetic, divinatory and ritual visual systems |
| Retro media | Analog home video, local television and physical media interfaces |
| Psychological surrealism | Displaced scale, delayed reflections and spatial unease |
| Symbolism and metaphysical art | Allegory, silent plazas, symbolic gardens and staged still life |
| Visionary art | Biomorphic forms, synesthetic color and luminous geometry |
| Weirdcore | Glitched interfaces, misplaced objects and uneasy visual incongruities |

### Focused packs

| Pack | Entries | Kind and scope |
| --- | --- | --- |
| Computational Surfaces | 8 | Engraved flow fields, reaction-diffusion lacquer, contour relief, Truchet inlay, dithered felt, voronoi glass, moire satin and plotter density |
| Weather and atmosphere | 10 | Rain, coastal mist, heat haze, frost, snow light, blue hour, after rain, sea fog, canopy light and post-storm light |
| Textile and fashion craft | 10 | Jacquard, brocade, organza, velvet, denim, tweed, cable knit, pleats, lookbook and visible mending |
| Garden and land art | 10 | Axial, parterre, rock, moss, terraced, meadow and walled gardens, plus three land-art forms |
| Jewelry craft | 10 | Granulation, guilloche, champleve, plique-a-jour, mokume-gane, hammered, wirework, cabochon, faceting and cameo |
| Lettering | 10 | Calligraphy, brush signs, stencil, wood type, chalk, neon, gold leaf, embossed, stitched and drawn serif; text-capable models only |

The former Optical Material Accents and Animation Finishing modifiers are effects in
the shared Effects set. The Information Hierarchy modifiers, which asked the model to
arrange labels and connectors, were retired: an image encoder cannot follow them.

## 2026-11 cleanup

All clauses were rewritten from instructions ("Render the subject as...") into short
visual descriptions ("hand-inked anime cel art"), because text encoders read words,
not commands. Negations, conditionals and references to "the scene" or "existing"
content were removed. The mood axis was replaced by visible light, palette or
composition. Tags for Anima now favour tags the model knows (54% of bundled tags and
77% of looks' core tags match a 30,877-tag local tagger vocabulary, used as a
stand-in for Anima's own vocabulary). Studio packs were cut from 40 to 10 entries
each, grades and effects were consolidated, and authors were unified. 161 IDs are
retired; 70 map to a replacement and the rest are skipped with a notice. `scripts/audit_library.py --check` enforces
these rules. The improvement claims are about text; image adherence was checked only
on the limited matched-seed comparison recorded in [validation](validation.md).

The [pack review](style-review.md) records the earlier 0.3.0 corrections.

Historical and regional names are creative technique references. They do not certify provenance, cultural authenticity, scholarly reconstruction or image-model knowledge. Some transformations intentionally change geometry, palette or medium; the user chooses those treatments explicitly.

## How a style is built

Every style has a stable ID, clear title, description, category, search tags, kind, model constraints, explicit axis claims and staged clauses. Each clause contains natural-language text, compact tags and an activation threshold. Full looks generally expose medium first, then supporting lighting, color, composition or texture. A small grade or modifier changes one declared axis. The authoring policy avoids invented subjects, plot events, lettering and generic quality boosters. The [0.3.0 review](style-review.md) corrects targeted content leakage in both prose and tag renderings; it does not certify semantic behavior of generated pixels.

For example, `cinema.noir` separates its classic film medium, monochrome palette, directional shadow shaping and silver-grain texture into independent clauses. Its Anima variant begins with `film noir anime screenshot`. `photo.*` and `documentary.*` entries exclude Anima because that model is documented for illustration rather than realism. Most craft styles are model-neutral; that means their output formatting is supported, not that every model will render the craft equally well.

## Intensity and layers

Intensity activates authored clauses progressively through three standard tiers (0, 0.4 and 0.75), named Subtle, Balanced and Strong in Studio. It is an interpretable semantic control, not a continuous image-strength guarantee, attention weight or LoRA multiplier. Zero bypasses the layer. Each model profile's style budget then trims the lowest-priority supporting clauses when many layers are stacked.

Full looks use distinct medium and texture claims so incompatible rendering processes do not silently coexist. Every bundled authored axis is declared so claims identify conflicts consistently. A color grade can replace a prior palette while retaining its medium and texture. `first_wins`, `last_wins` and `error` are deterministic policies; `locked_axes` protects user-chosen dimensions. Undeclared contradictions inside user prose cannot be reliably detected without semantic inference. Inspection lists retained, skipped and overridden clauses so the result can be audited.

Try `cinema.noir` with a lighting modifier, `illustration.gouache` with `grade.sage`, or `render.clay` with `light.raking`. Read the trace when combining full looks with different medium claims. Recommendations rank metadata matches and capability eligibility; they do not silently rewrite a prompt or promise aesthetic compatibility.

## Previews

The bundled browser uses explicitly labeled abstract swatches to make the catalog navigable. They are not generated examples and do not demonstrate model output. Packs can declare safe relative preview references with alt text and provenance kind; custom preview paths are not automatically exposed by the server. A future evidence gallery should store model/checkpoint/workflow, seed, recipe fingerprint and license with each genuine example.

## Authoring and review

Add a separate versioned JSON pack using the documented schema. Use original wording, a distinctive visual identity and concise clauses. Give palette, lighting and composition claims consistent names. Do not create a cross-product of generic suffixes to increase the count. Review a new look for internal contradictions, unintended scene insertion and semantic duplication with neighboring entries. Community packs remain separate data files and cannot execute Python, fetch assets or evaluate templates.

The release tests check unique IDs, names, descriptions and base clauses; absence of stock quality boosters; legal thresholds and claim axes; capability filtering; every eligible style/profile composition; and stable intent preservation. These checks catch structural defects. Image-generation review across representative scenes remains necessary before calling individual looks visually optimized.

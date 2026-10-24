# Style library

The built-in library contains original, independently authored visual treatments, color grades and creative modifiers. Code is Apache-2.0; all bundled style text is dedicated under CC0-1.0 in [STYLE-LICENSE](../STYLE-LICENSE). No legacy PromptStyler templates, artist identities or generated-image assets are copied into these packs.

The launch collection has 832 entries in 33 packs: 784 visual treatments, 24 color grades and 24 modifiers. The audited reference library has 585 modern pack entries; the successor increases the count while giving each entry structured clauses, explicit composition claims and separate prose/tag renderings. The count is an inventory fact, not a visual-quality metric.

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

Historical and regional names are creative technique references. They do not certify provenance, cultural authenticity, scholarly reconstruction or image-model knowledge. Some transformations intentionally change geometry, palette or medium; the user chooses those treatments explicitly.

## How a style is built

Every style has a stable ID, clear title, description, category, search tags, kind, model constraints, explicit axis claims and staged clauses. Each clause contains natural-language text, compact tags and an activation threshold. Full looks generally expose medium first, then supporting lighting, color, composition or texture. A small grade or modifier changes one declared axis. No style automatically adds subjects, plot events, artist names, resolution claims or generic quality boosters.

For example, `cinema.noir` separates its classic film medium, monochrome palette, directional shadow shaping and silver-grain texture into independent clauses. Its Anima variant explicitly changes the medium to an illustrated keyframe. `photo.*` and `documentary.*` entries exclude Anima because that model is documented for illustration rather than realism. Most craft styles are model-neutral; that means their output formatting is supported, not that every model will render the craft equally well.

## Intensity and layers

Intensity activates authored clauses progressively. It is an interpretable semantic control, not a continuous image-strength guarantee, attention weight or LoRA multiplier. Zero bypasses the layer. Different looks can use different thresholds when their craft requires it.

Full looks use distinct medium and texture claims so incompatible rendering processes do not silently coexist. Claims identify conflicts on declared axes. A color grade can replace a prior palette while retaining its medium and texture. `first_wins`, `last_wins` and `error` are deterministic policies; `locked_axes` protects user-chosen dimensions. Undeclared contradictions inside user prose cannot be reliably detected without semantic inference. Inspection lists retained, skipped and overridden clauses so the result can be audited.

Try `cinema.noir` with a lighting modifier, `illustration.gouache` with `grade.sage`, or `render.clay` with `light.raking`. Read the trace when combining full looks with different medium claims. Recommendations rank metadata matches and capability eligibility; they do not silently rewrite a prompt or promise aesthetic compatibility.

## Previews

The bundled browser uses explicitly labeled abstract swatches to make the catalog navigable. They are not generated examples and do not demonstrate model output. Packs can declare safe relative preview references with alt text and provenance kind; custom preview paths are not automatically exposed by the server. A future evidence gallery should store model/checkpoint/workflow, seed, recipe fingerprint and license with each genuine example.

## Authoring and review

Add a separate versioned JSON pack using the documented schema. Use original wording, a distinctive visual identity and concise clauses. Give palette, lighting and composition claims consistent names. Do not create a cross-product of generic suffixes to increase the count. Review a new look for internal contradictions, unintended scene insertion and semantic duplication with neighboring entries. Community packs remain separate data files and cannot execute Python, fetch assets or evaluate templates.

The release tests check unique IDs, names, descriptions and base clauses; absence of stock quality boosters; legal thresholds and claim axes; capability filtering; every eligible style/profile composition; and stable intent preservation. These checks catch structural defects. Image-generation review across representative scenes remains necessary before calling individual looks visually optimized.

# Firefly E-Ink UI Prompts

Prompt library for generating degraded gothic e-ink UI assets in Adobe Firefly.

## Firefly settings

- **Max prompt length:** 1000 characters (each prompt below is within limit)
- **No negative prompt field** — exclusions are baked into each prompt
- **Content type:** Illustration / Graphic
- **Style reference:** Use best result (nested arch / dialogue frame) at ~50–70%
- **Composition tip:** If center fills with arches, append: `hollow picture frame not standalone arch, interior blank white for text`

## Shared core anchor (~312 chars)

Used at the start of every prompt below:

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD.
```

## Optional suffixes

Append when results need tuning (stay under 1000 chars total):

| Goal | Suffix |
|------|--------|
| More degradation | `, intense horizontal glitch on border, corners crumbling to stipple dust, interior stays blank white` |
| Less center clutter | `, hollow picture frame not standalone arch, gothic shape only on bottom border lip` |
| Integrated stipple | `, stipple dots form the strokes themselves, white gaps inside every line` |
| More readable frame | `, interior 80% pure white for paragraph text, zero inner lines arches or axes` |

---

## Text frames

### Dialogue box (615)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Wide horizontal dialogue frame, hollow picture frame not standalone arch. Thin rounded stipple border ~10% margin. Top/sides ghosted double border. Bottom margin only: faded nested arch crest + vertical drip remnants. Faint construction circle on outer edge. Interior 80% pure white for paragraph text.
```

### Dialogue box — heavy degradation (578)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Wide dialogue frame, border heavily eroded fragmenting into stipple + horizontal glitch bands on edges only. Bottom margin degraded gothic arch band. Corners dissolving to dot fade. Interior huge clean empty white, zero inner lines/arches/axes. Game dialogue panel.
```

### Title banner (501)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Thin wide title strip. Top stippled double border, small faded arch ghost on top margin only. Scan tear on top border. Crosshairs at ends. Wide empty white center strip for one-line title.
```

### Choice list frame (502)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Tall narrow menu list frame. Left stippled dashed border eroded with glitch. Right border minimal dots. Short degraded top/bottom caps. Interior tall empty white column for stacked choices.
```

### Inset / quote frame (464)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Small inset quote frame. Thin double stipple border eroded at corners. Faint construction circle behind outer edge only. Center completely empty white.
```

### Full-screen reading panel (503)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Large reading panel thin border. Bottom margin wide degraded gothic arch band only. Sides glitching horizontally. Faint grid in outer margin only. Massive empty white interior for body text.
```

---

## Circular buttons

### Default (501)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Circular UI button. Fragmented stipple ring eroded, glitch on ring only. Two faint ghost rings. Small faded arch on lower arc outside center. Crosshair center. Empty white middle for icon.
```

### Pressed (498)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Circular button pressed. Ring collapsed inward, denser stipple on border. Scan tear on outer ring. Glitched crosshair. Bottom arc eroding to vertical dot remnants on edge. Empty center.
```

### Disabled (418)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Faint broken ring almost gone, sparse stipple on edge. Faded crosshair. Mostly empty white. Empty center.
```

### Small icon button (425)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Small circular icon button. Tight eroded stipple ring, glitch on one side. Crosshair center. Empty white middle.
```

### Large primary button (482)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Large circular primary button. Nested faded stipple rings on perimeter. Faint arch ghost lower ring only. Radius guides outside ring. Large empty white center for label.
```

---

## HUD & chrome

### Main menu panel (504)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Menu panel rounded rectangle border eroded/glitch on edges. Top margin small faded arch band. Faint construction circle behind outer edge. Corner crosshairs. Large empty interior for buttons.
```

### Status bar (459)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Thin horizontal status bar. Top/bottom stippled lines eroded with glitch. Small crosshair segment dividers on border. Empty white segments inside.
```

### Divider (443)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Horizontal UI divider. Broken stipple line with scan glitch. Small faded ring + crosshair at center. Dashed radius fading outward.
```

### Scrollbar track (415)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Thin vertical scrollbar track. Stippled dashed sides eroded. Dot caps top/bottom. Empty white channel.
```

### Scrollbar thumb (424)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Small rectangular scrollbar thumb. Corrupted stipple outline eroded edges. Crosshair center. Ghost offset pass.
```

### Page indicator dots (425)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Row of five eroded stipple rings. One selected denser. Faint dashed alignment line. Sparse noise near dots only.
```

---

## Icons

### Back / close (440)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Small circular back icon. Eroded stipple ring. Abstract X from broken dashed diagonals in dots. Crosshair center. Empty middle.
```

### Settings (435)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Settings gear icon. Nested stipple circles + radial dashes eroding on perimeter. Crosshair hub. Scan tear outer edge only.
```

### Inventory (451)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Square inventory icon frame. Stippled dashed border eroded corners. Abstract pouch from broken dot lines. Crosshair corners. Empty center.
```

### Compass (436)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Compass rose icon. Stippled radius lines on perimeter. Faint arch north marker, no letters. Crosshair center. Empty middle.
```

---

## Extras

### Modal / popup frame (477)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Centered modal popup. Thick eroded stipple border, heavy glitch on edges. Bottom margin degraded arch band. Corner crosshairs. Large empty white center for message.
```

### Corner flourishes (441)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Four corner bracket pieces. Short stippled L-shapes eroded. Faint arc ghost each corner. Crosshair at joint. For tiling corners.
```

### Background texture (432)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. Very faint edge-only background. Sparse stippled grid barely at screen edges. Mostly pure white center for readability.
```

### Sprite sheet (427)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, center decoration, clean CAD. UI sprite sheet grid: dialogue frames, buttons, HUD, icons. Empty white interiors, degraded borders only. No text.
```

---

## Terminal star button (organic 8-point sunburst)

Reference: puffy blobby 8-point star / sunburst terminal button — soft rounded tips, fluid curves, faint circular base. Not sharp geometric star, not 3D clay render.

**Firefly tip:** Upload Blender screenshot as composition reference (~40%). Use best e-ink dialogue frame as style reference (~60%).

### Star button icon (559)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. No text, watermark, cathedral, clean CAD. Terminal game button icon, top-down view. Organic 8-point star sunburst silhouette, puffy soft rounded tips, blobby fluid curves not sharp geometric star. Thick stippled outline eroded with glitch on edge. Faint circular ghost ring behind shape. Crosshair at center. Empty white middle for symbol. Avoid perfect symmetry, 3D render, color.
```

### Star button — pressed (497)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. No text, watermark, cathedral, clean CAD. Terminal button pressed state. Organic 8-point star collapsed inward, tips softer blobbier, denser stipple on border. Scan tear across one edge. Ghost offset pass. Crosshair glitched. Empty white center. Avoid sharp star, 3D, color.
```

### Star button — disabled (451)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. No text, watermark, cathedral, clean CAD. Faint terminal button icon. Barely visible organic 8-point star sunburst outline dissolving to stipple dust, puffy rounded tips almost gone. Faint circle ghost. Faded crosshair. Mostly empty white. Avoid sharp geometric star, 3D, color.
```

### Star button — large with label area (521)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. No text, watermark, cathedral, clean CAD. Large terminal UI button. Organic 8-point star sunburst outer shape, puffy blobby rounded tips, thick soft stippled perimeter. Faint concentric ghost rings inside points. Crosshair center. Large empty white middle for label. Top-down game button. Avoid sharp geometric star, 3D clay, color.
```

### Star-shaped frame (hollow border) (570)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, cathedral, clean CAD. Hollow picture frame shaped as organic 8-point star sunburst border, puffy rounded blobby tips, soft fluid curves not sharp star. Border ~10% thickness stipple eroded. Faint circular construction ring behind. Interior large empty white circle for text. Game terminal UI frame.
```

### Rectangular frame with star corner ornaments (556)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Faded gothic hints on margins only. Large empty white text-safe center, zero marks inside. No text, watermark, cathedral, clean CAD. Wide dialogue frame with rounded rectangle border. Four organic puffy 8-point star sunburst ornaments on corners only, blobby soft tips not sharp. Stars as faded stipple ghosts on margin. Interior huge empty white for text. Terminal game UI.
```

---

## Style notes (from iteration)

- **Target look:** Degraded architectural plate — stipple is the stroke medium, not an overlay on clean lines
- **Gothic:** Faded nested arch ghosts on margins/bottom only; never a centered standalone arch
- **UI usability:** Decoration on border only; interior must stay empty white for text
- **Terminal buttons:** Organic 8-point sunburst — puffy blobby tips, not sharp CAD star or 3D clay
- **Avoid:** CAD precision, cathedral scenes, ink blobs/splatters, uniform grain across whole image
- **Display:** 7.5" e-ink — generate at 800×480 or 480×800, threshold to 1-bit, nearest-neighbor downscale

## Folk-totem filigree (bread-idol reference)

Reference: ornate ritual totems — braided wheat stalks, openwork lace filigree, scalloped headdress crests, mask-like corner ghosts, bulbous scroll flourishes. Symmetrical folk-art interwoven line-work on borders only. **Not** photoreal bread, gold, color, or centered figurines.

**Firefly tip:** Upload bread-totem grid as composition reference (~50%). Use best degraded e-ink dialogue frame as style reference (~50%).

### Shared core anchor — folk-totem (~358 chars)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Folk-totem filigree on margins only: braided wheat bands, openwork lace holes, scalloped headdress crests. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered idol, figurine scene, color, food, 3D render, clean CAD.
```

### Dialogue frame — filigree border (597)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Folk-totem filigree on margins only: braided wheat bands, openwork lace holes, scalloped headdress crests. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered idol, figurine scene, color, food, 3D render, clean CAD. Wide dialogue frame hollow picture border. Sides: vertical braided wheat stipple bands with lace negative-space holes. Top: faded scalloped headdress crest ghost. Bottom: bulbous scroll flourish band eroded to stipple dust. Interior 80% pure white for text.
```

### Choice list frame (541)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Folk-totem filigree on margins only: braided wheat bands, openwork lace holes, scalloped headdress crests. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered idol, figurine scene, color, food, 3D render, clean CAD. Tall narrow menu frame. Left border thick openwork lace stipple band eroded with glitch. Right border minimal braided dashes. Top/bottom short scroll-cap ornaments fading to dots. Tall empty white column inside.
```

### Circular button — totem ring (548)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Folk-totem filigree on margins only: braided wheat bands, openwork lace holes, scalloped headdress crests. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered idol, figurine scene, color, food, 3D render, clean CAD. Circular UI button. Outer ring openwork lace stipple with wheat-braid segments, eroded glitch on ring. Faint scalloped crest ghost on lower arc. Crosshair center. Empty white middle for icon.
```

### Corner bracket — mask totem (556)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Folk-totem filigree on margins only: braided wheat bands, openwork lace holes, scalloped headdress crests. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered idol, figurine scene, color, food, 3D render, clean CAD. Single corner bracket piece. Small faded ritual mask-totem silhouette in stipple, scalloped halo above, braided stalk below, openwork lace beside. Eroded to ghost pass. Crosshair at joint. For tiling frame corners.
```

### Title banner — headdress crest (523)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Folk-totem filigree on margins only: braided wheat bands, openwork lace holes, scalloped headdress crests. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered idol, figurine scene, color, food, 3D render, clean CAD. Thin wide title strip. Top margin large scalloped headdress crest in stipple, scan tear across crest. Sides faint braided wheat dashes. Wide empty white center for one-line title.
```

### Modal frame — heavy filigree (562)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Folk-totem filigree on margins only: braided wheat bands, openwork lace holes, scalloped headdress crests. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered idol, figurine scene, color, food, 3D render, clean CAD. Centered modal popup. Thick openwork lace border ~12% margin, corners crumbling to stipple dust. Four faint mask-totem corner ghosts only. Bottom scroll flourish band degraded. Large empty white center for message.
```

### Sprite sheet — filigree UI kit (534)

```
B/W degraded e-ink UI asset. Stipple-dot strokes only, no solid lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Folk-totem filigree on margins only: braided wheat bands, openwork lace holes, scalloped headdress crests. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered idol, figurine scene, color, food, 3D render, clean CAD. UI sprite sheet grid: dialogue frames, lace-ring buttons, totem corner brackets, banners. Empty white interiors, degraded filigree borders only.
```

### Optional suffixes — folk-totem

| Goal | Suffix |
|------|--------|
| More lace openwork | `, border holes are negative white space inside stipple braids, filigree not solid fill` |
| More totem feel | `, faint ritual mask silhouette ghosts at four corners only, never centered` |
| Less clutter | `, filigree only on bottom lip and corners, sides minimal braided dashes` |
| More degradation | `, intense horizontal glitch on border lace, crest dissolving to stipple dust` |

---

## Naive sigil outsider-art (hand-ink references)

Reference: shaky hand-drawn marker/ink on paper — wobbly bold strokes, grainy bleed edges, naive outsider art. Motifs: irregular starburst asterisks, wavy spindly tendrils, blocky arrows, parallel stripe hatching, scalloped beaded borders, small sigil blobs with almond-eye ghosts. Occult diagram / folk horror sketchbook. **Not** centered creatures, full illustrations, color, red ink, or clean vector UI.

**Firefly tip:** Upload best hand-ink reference (~50%). Use degraded e-ink dialogue frame as style reference (~50%) for scan-tear + empty-center discipline.

### Shared core anchor — naive sigil (~382 chars)

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on margins only: wavy tendril spindles, hand starbursts, blocky arrows, stripe hatch bands. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD.
```

### Dialogue frame — scalloped beaded border (598)

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on margins only: wavy tendril spindles, hand starbursts, blocky arrows, stripe hatch bands. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. Wide dialogue frame. Scalloped beaded stipple border wobbly hand-drawn ~10% margin. Corner sigil starburst ghosts only. Sides vertical stripe hatch eroded with glitch. Bottom wavy tendril cap + faint blocky arrows. Interior 80% pure white for text.
```

### Choice list frame (552)

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on margins only: wavy tendril spindles, hand starbursts, blocky arrows, stripe hatch bands. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. Tall narrow menu frame. Left border thick wobbly stipple line with stripe hatch fill eroded. Right border sparse tendril dashes. Top/bottom short scalloped caps dissolving to dots. Tall empty white column for stacked choices.
```

### Circular button — starburst ring (561)

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on margins only: wavy tendril spindles, hand starbursts, blocky arrows, stripe hatch bands. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. Circular UI button. Hand-drawn irregular starburst ring stipple, 6-8 wobbly points eroded with glitch. Faint tendril ghost on lower arc. Crosshair center. Empty white middle for icon.
```

### Corner bracket — sigil ghost (571)

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on margins only: wavy tendril spindles, hand starbursts, blocky arrows, stripe hatch bands. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. Single corner bracket. Small faded organic sigil blob ghost with almond-eye dots, spindly tendril offshoot, irregular star above. Hand-inked wobbly L-shape eroded. Crosshair at joint. For tiling corners.
```

### Title banner — stripe hatch (538)

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on margins only: wavy tendril spindles, hand starbursts, blocky arrows, stripe hatch bands. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. Thin wide title strip. Top/bottom parallel stripe hatch bands shaky hand-drawn. Small starburst asterisks at ends fading to stipple. Scan tear on top border. Wide empty white center for one-line title.
```

### Divider — wavy tendril (524)

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on margins only: wavy tendril spindles, hand starbursts, blocky arrows, stripe hatch bands. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. Horizontal UI divider. One long wavy tendril line hand-inked stipple with bleed, broken mid-span glitch. Small irregular starburst at center. Tapering spindly ends fading to dots.
```

### Text frame border — inner sigil ring (589) ★ best result

Refined from modal prompt: **border only**, thin ring, huge interior. Upload your best Firefly result as style reference (~70%).

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on border only: wavy tendril spindles, hand starbursts, blocky arrows. Huge empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. Hollow text frame border only, thin wobbly stipple ring ~6% margin. Four corner sigil starburst ghosts on border joints. Top/bottom center blocky arrow sigils, side midpoints outward arrows on border. Sides single wobbly stipple lines eroded glitch. Interior 88% pure white rectangle. Pure white outside border, no outer margin art, no tendrils beyond frame.
```

### Text frame border — minimal ring (521)

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on border only: wavy tendril spindles, hand starbursts, blocky arrows. Huge empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. Hollow picture frame thin stipple border ~5% margin. Corner starburst sigils only. Top/bottom faint blocky arrow ghosts on border lip. Interior 90% pure white. Zero decoration outside frame edge, pure white canvas.
```

### Dialogue frame — sigil border + gothic degradation (984) ★ combined

Merges **minimal sigil ring** + **heavy degradation dialogue frame** + **thin organic neuron lines**: ~5% border, corner starbursts, blocky arrow ghosts, bottom organic arch band, spindly tendril arcs on sides, eroded glitch edges, 90% empty interior.

```
B/W degraded e-ink UI asset. Shaky hand-inked stipple-dot strokes, thin organic spindly lines, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on border only: neuron tendril spindles, hand starbursts, blocky arrows. Faded organic gothic arch ghosts on margins only, loose hand-drawn not CAD. Huge empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, cathedral, inner arches/axes, full scene, color, clean CAD. Wide game dialogue frame, hollow picture border, thin wobbly stipple ring ~5% margin eroded fragmenting into stipple + horizontal glitch bands edges only. Corner starburst sigils dissolving to dot fade. Top/bottom faint blocky arrow ghosts on lip. Bottom thin organic gothic arch band, spindly neuron lines. Sides faint thin tendril arcs margin only. Interior 90% pure white, zero inner decoration. Pure white outside frame edge.
```

### Modal frame — neuron margin (568) — use text frame border instead

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on margins only: wavy tendril spindles, hand starbursts, blocky arrows, stripe hatch bands. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. Centered modal popup. Thick wobbly stipple border ~12% margin. Four corner sigil starburst ghosts only. Outer margin faint spindly tendril arcs like neuron diagram, eroded scan tears. Large empty white center for message.
```

### Scalloped card frame (554)

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on margins only: wavy tendril spindles, hand starbursts, blocky arrows, stripe hatch bands. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. Rounded card frame with scalloped beaded outer edge hand-drawn stipple. Border grainy ink bleed eroded at corners. Faint starburst at each scallop tip. Hollow frame interior huge empty white for content.
```

### Icon — irregular sigil star (537)

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on margins only: wavy tendril spindles, hand starbursts, blocky arrows, stripe hatch bands. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. Small UI icon. Irregular hand-drawn 7-point sigil star stipple, uneven point lengths, three negative-space dot voids in center. Wobbly bleed edges. Sparse tendril off one point. Empty white around icon.
```

### Sprite sheet — sigil UI kit (548)

```
B/W degraded e-ink UI asset. Shaky hand-inked strokes in grainy stipple, jagged bleed edges, no solid vector lines, no overlay grain. Eroded borders, ghosted passes, scan tears on edges. Naive sigil outsider-art on margins only: wavy tendril spindles, hand starbursts, blocky arrows, stripe hatch bands. Large empty white text-safe center, zero marks inside. Corner crosshairs. No text, watermark, centered creature, full scene, color, clean CAD. UI sprite sheet grid: scalloped frames, starburst buttons, tendril dividers, stripe banners, sigil corner brackets. Empty white interiors, degraded hand-ink borders only.
```

### Optional suffixes — naive sigil

| Goal | Suffix |
|------|--------|
| More hand-drawn wobble | `, lines visibly shaky uneven not CAD, marker bleed fuzz on stroke edges only` |
| More occult diagram | `, faint spindly neuron tendrils in outer margin only, never crossing interior` |
| More naive folk | `, blocky arrow sprouts on top margin, dot-eye sigil ghosts at corners only` |
| Less clutter | `, decoration on bottom lip and corners only, sides single wobbly stipple line` |
| Larger interior | `, interior 90% pure white, border thin ring ~5% margin only, zero art outside frame edge` |
| More degradation | `, intense horizontal glitch on border, starbursts dissolving to stipple dust` |

---

## Changelog

- 2026-06-24: Combined dialogue frame — thin organic neuron lines + loose gothic arches
- 2026-06-24: Combined naive sigil + gothic degradation dialogue frame prompt
- 2026-06-24: Text frame border variant — thin inner ring, larger white interior (refined from modal)
- 2026-06-24: Naive sigil outsider-art prompts (hand-ink references, B/W degraded e-ink)
- 2026-06-24: Folk-totem filigree prompts (bread-idol reference, B/W degraded e-ink)
- 2026-06-24: Terminal star/sunburst button + frame prompts
- 2026-06-24: Initial prompt set — compressed for Firefly 1000 char limit

"""Extract '7','0','5' outlines from Jost (Futura-style free alternative,
OFL licensed) at Black weight, as SVG path data -- so the final icon never
depends on a font being installed (same reasoning as the old LED-segment
rects, just sourced from real type this time)."""
import json
import os

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen

OUT = os.path.dirname(os.path.abspath(__file__))

font = TTFont(os.path.join(OUT, "Jost.ttf"))
# Black = 900 (max boldness, per "in đậm hơn để nổi bật")
instantiateVariableFont(font, {"wght": 900}, inplace=True)

glyph_set = font.getGlyphSet()
cmap = font.getBestCmap()
upm = font["head"].unitsPerEm  # units per em, to normalize later

result = {"unitsPerEm": upm, "glyphs": {}}
overall_ymin, overall_ymax = None, None
for ch in "705":
    glyph_name = cmap[ord(ch)]
    glyph = glyph_set[glyph_name]
    pen = SVGPathPen(glyph_set)
    glyph.draw(pen)
    bp = BoundsPen(glyph_set)
    glyph.draw(bp)
    xmin, ymin, xmax, ymax = bp.bounds
    result["glyphs"][ch] = {
        "d": pen.getCommands(),
        "advanceWidth": glyph.width,
        "bounds": {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax},
    }
    overall_ymin = ymin if overall_ymin is None else min(overall_ymin, ymin)
    overall_ymax = ymax if overall_ymax is None else max(overall_ymax, ymax)
result["overallYMin"] = overall_ymin
result["overallYMax"] = overall_ymax

with open(os.path.join(OUT, "jost_glyphs.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2)

print("unitsPerEm:", upm)
print("overall y range:", overall_ymin, overall_ymax)
for ch, g in result["glyphs"].items():
    print(ch, "advance:", g["advanceWidth"], "bounds:", g["bounds"])

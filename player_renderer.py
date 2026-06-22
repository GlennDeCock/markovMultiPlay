"""
player_renderer.py — Renders a full player window as a 1-bit PIL Image.
Resolution is configurable — supports both 480x800 (V2) and 384x640 (V1).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from engine import STATUS_ENCOUNTER, STATUS_GAME_OVER
from image_gen import generate_scene_pil_image

# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

_FONT_DIR = Path(__file__).parent / "fonts"
_FONTS: dict[int, ImageFont.FreeTypeFont] = {}


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    f = _FONTS.get(size)
    if f is None:
        path = _FONT_DIR / "DejaVuSansMono.ttf"
        f = ImageFont.truetype(str(path), size=size)
        _FONTS[size] = f
    return f


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _draw_dashed_hrule(draw: ImageDraw, y: int, x1: int, x2: int,
                       color: int = 0, dash_len: int = 4, gap_len: int = 5):
    x = x1
    on = True
    while x < x2:
        end = min(x + (dash_len if on else gap_len), x2)
        if on:
            draw.line([(x, y), (end, y)], fill=color, width=1)
        x = end
        on = not on


def _dotted_rect(draw: ImageDraw, x1, y1, x2, y2, color: int = 0):
    _draw_dashed_hrule(draw, y1, x1, x2, color)
    _draw_dashed_hrule(draw, y2, x1, x2, color)
    for y in range(y1, y2, 7):
        draw.line([(x1, y), (x1, min(y + 4, y2))], fill=color, width=1)
        draw.line([(x2, y), (x2, min(y + 4, y2))], fill=color, width=1)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    char_w = font.getlength("n")
    chars_per_line = max(1, int(max_width / char_w))
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        line = ""
        for word in words:
            candidate = line + (" " if line else "") + word
            if len(candidate) > chars_per_line and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Layout computation  (scales with screen resolution)
# ---------------------------------------------------------------------------

class _Layout:
    """Computed layout for a given screen size."""

    def __init__(self, screen_w: int, screen_h: int):
        self.screen_w = screen_w
        self.screen_h = screen_h

        bezel = 6 if screen_w <= 400 else 8
        self.bezel = bezel
        self.pw = screen_w - bezel * 2
        self.ph = screen_h - bezel * 2

        # Image size — scale zoom to fit width
        # 100x100 grid; pick zoom so image fits with padding
        max_img_w = self.pw - 24
        zoom = max(1, min(3, int(max_img_w / 100)))
        self.img_w = 100 * zoom
        self.img_h = 100 * zoom
        self.img_pad = 8 if screen_h <= 500 else 12
        self.img_x = (self.pw - self.img_w) // 2
        self.img_top = self.img_pad
        self.zoom = zoom

        self.sep1_y = self.img_h + self.img_pad * 2
        self.text_y = self.sep1_y + 2
        self.text_x = 18 if screen_w <= 400 else 24
        self.text_w = self.pw - self.text_x * 2

        self.trace_h = max(24, min(36, screen_h // 22))
        self.choice_h = max(30, min(40, screen_h // 20))
        self.choice_gap = max(3, min(5, screen_h // 160))
        self.choice_pad = 12 if screen_w <= 400 else 16
        self.choice_zone = 2 * self.choice_h + self.choice_gap
        self.sep2_y = self.ph - self.choice_zone - self.trace_h - 12
        self.trace_y = self.sep2_y + 4
        self.choice_y_start = self.trace_y + self.trace_h + 4


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_player_screen(
    player_id: str | None,
    scene_text: str,
    choices: list,
    trace: str | None,
    status: str,
    node_id: str | None = None,
    node_title: str | None = None,
    encounter_text: str | None = None,
    use_restart: bool = False,
    screen_w: int = 480,
    screen_h: int = 800,
) -> Image.Image:
    """Render a full player window as 1-bit PIL Image.
    Pixel values: 1 = paper (white), 0 = ink (black).
    screen_w/screen_h select the layout (V2=480x800, V1=384x640, etc).
    """
    L = _Layout(screen_w, screen_h)
    img = Image.new("1", (L.screen_w, L.screen_h), 1)
    draw = ImageDraw.Draw(img)

    # ── Paper background ────────────────────────────────────────────
    draw.rectangle([L.bezel, L.bezel, L.bezel + L.pw - 1, L.bezel + L.ph - 1],
                   fill=1, outline=0)
    _dotted_rect(draw, L.bezel + 4, L.bezel + 4,
                 L.bezel + L.pw - 4, L.bezel + L.ph - 4, color=0)

    # ── Scene image ─────────────────────────────────────────────────
    scene_img = generate_scene_pil_image(scene_text, zoom=L.zoom)
    img.paste(scene_img, (L.bezel + L.img_x, L.bezel + L.img_top))

    if status == STATUS_ENCOUNTER:
        clash_font = _get_font(10)
        clash_label = "BREACH"
        cw = int(clash_font.getlength(clash_label))
        cx = L.bezel + L.img_x + (L.img_w - cw) // 2
        cy = L.bezel + L.img_top + L.img_h - 14
        draw.rectangle([cx - 4, cy - 2, cx + cw + 4, cy + 12], fill=0)
        draw.text((cx, cy), clash_label, fill=1, font=clash_font)

    # ── Separator 1 ─────────────────────────────────────────────────
    sy1 = L.bezel + L.sep1_y
    _draw_dashed_hrule(draw, sy1, L.bezel + 12, L.bezel + L.pw - 12)

    # ── Scene text ──────────────────────────────────────────────────
    text_font = _get_font(11 if screen_h > 500 else 9)
    title_font = _get_font(13 if screen_h > 500 else 11)
    txt_x = L.bezel + L.text_x
    txt_y = L.bezel + L.text_y
    text_area_h = (L.bezel + L.sep2_y) - txt_y - 4

    if node_title:
        draw.text((txt_x, txt_y), node_title, fill=0, font=title_font)
        txt_y += title_font.size + 6

    wrapped = _wrap_text(scene_text, text_font, L.text_w)
    draw.multiline_text((txt_x, txt_y), wrapped, fill=0,
                        font=text_font, spacing=3)

    # ── Node ID (top-right of text zone) ────────────────────────────
    if node_id and not node_title:
        nid_font = _get_font(7)
        nid_text = node_id
        nid_w = int(nid_font.getlength(nid_text))
        draw.text((L.bezel + L.pw - 18 - nid_w, L.bezel + L.sep1_y + 2),
                  nid_text, fill=0, font=nid_font)

    # ── Separator 2 ─────────────────────────────────────────────────
    sy2 = L.bezel + L.sep2_y
    _draw_dashed_hrule(draw, sy2, L.bezel + 12, L.bezel + L.pw - 12)

    # ── Trace line ──────────────────────────────────────────────────
    if trace:
        trace_font = _get_font(8)
        draw.text((txt_x, L.bezel + L.trace_y), trace, fill=0, font=trace_font)

    # ── Choices or restart button ───────────────────────────────────
    if use_restart or status == STATUS_GAME_OVER:
        btn_font = _get_font(10)
        btn_x = L.bezel + L.choice_pad
        btn_w = L.pw - L.choice_pad * 2
        btn_y = L.bezel + L.choice_y_start
        btn_h = L.choice_zone
        _dotted_rect(draw, btn_x - 2, btn_y - 2,
                     btn_x + btn_w + 2, btn_y + btn_h + 2, color=0)
        rlabel = "[ restart ]"
        rw = int(btn_font.getlength(rlabel))
        draw.text((btn_x + (btn_w - rw) // 2,
                   btn_y + (btn_h - 10) // 2),
                  rlabel, fill=0, font=btn_font)
    else:
        choice_font = _get_font(9)
        display = []
        for ch in choices[:2]:
            pfx = "\u21BA  " if getattr(ch, "is_cross", False) else "\u2192  "
            display.append(pfx + ch.label)

        for i, label in enumerate(display):
            cy = L.bezel + L.choice_y_start + i * (L.choice_h + L.choice_gap)
            cx = L.bezel + L.choice_pad
            cw = L.pw - L.choice_pad * 2
            _dotted_rect(draw, cx, cy, cx + cw, cy + L.choice_h, color=0)
            draw.text((cx + 12, cy + L.choice_h // 2 - 7),
                      label, fill=0, font=choice_font)

    return img


def render_to_png_bytes(player_id, scene_text, choices, trace,
                        status, node_id=None, node_title=None,
                        encounter_text=None,
                        screen_w=480, screen_h=800) -> bytes:
    """Render and return PNG bytes."""
    img = render_player_screen(
        player_id=player_id,
        scene_text=scene_text,
        choices=choices,
        trace=trace,
        status=status,
        node_id=node_id,
        node_title=node_title,
        encounter_text=encounter_text,
        screen_w=screen_w,
        screen_h=screen_h,
    )
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

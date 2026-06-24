"""
player_renderer.py — Renders a full player window as a 1-bit PIL Image.
Background.png carries frame, buttons, and border art; this layer adds
cityscape + dynamic text only.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from engine import STATUS_ENCOUNTER, STATUS_GAME_OVER
from epaper_layout import (
    PW, PH, SCENE_TOP, SCENE_W, SCENE_H, SCENE_X,
    NODE_FRAME_W, NODE_FRAME_H, NODE_FRAME_X, NODE_FRAME_Y, NODE_FRAME_BORDER,
    TEXT_WRAP_W, TEXT_BODY_SIZE, NODE_ID_TEXT_SIZE,
    BTN_SIZE, BTN_Y, CHOICE_LX, CHOICE_RX,
    CHOICE_TEXT_Y, CHOICE_W, TRACE_Y,
)
from image_gen import generate_node_pil_image

_UI_DIR = Path(__file__).parent / "UI_Elements"
_FONT_DIR = Path(__file__).parent / "fonts"
_UI_CACHE: dict[tuple, Image.Image] = {}
_FONTS: dict[tuple, ImageFont.FreeTypeFont] = {}


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    f = _FONTS.get(key)
    if f is None:
        path = _FONT_DIR / "DejaVuSansMono.ttf"
        f = ImageFont.truetype(str(path), size=size)
        _FONTS[key] = f
    return f


def _load_background(width: int, height: int) -> Image.Image:
    key = ("Background.png", width, height)
    if key in _UI_CACHE:
        return _UI_CACHE[key]
    img = Image.open(_UI_DIR / "Background.png").convert("RGBA")
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    _UI_CACHE[key] = img
    return img


def _rgba_to_1bit(rgba: Image.Image) -> Image.Image:
    flat = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    flat = Image.alpha_composite(flat, rgba)
    return flat.convert("L").point(lambda p: 0 if p < 200 else 255, mode="1")


def _paste_1bit(base: Image.Image, overlay: Image.Image, x: int, y: int) -> None:
    base.paste(overlay, (x, y))


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if font.getlength(candidate) <= max_width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    cx: float,
    cy: float,
    font: ImageFont.FreeTypeFont,
    fill: int = 0,
    spacing: int = 4,
) -> None:
    if not lines:
        return
    heights = [font.size + spacing for _ in lines]
    total_h = sum(heights) - spacing
    y = cy - total_h / 2
    for line in lines:
        w = font.getlength(line)
        draw.text((cx - w / 2, y), line, fill=fill, font=font)
        y += font.size + spacing


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
    screen_w: int = PW,
    screen_h: int = PH,
) -> Image.Image:
    """Render a full player window as 1-bit PIL Image (1=paper, 0=ink)."""
    sw, sh = screen_w, screen_h
    sx = int(SCENE_X * sw / PW)
    sy = int(SCENE_TOP * sh / PH)
    sw_scene = int(SCENE_W * sw / PW)
    sh_scene = int(SCENE_H * sh / PH)
    nfw = int(NODE_FRAME_W * sw / PW)
    nfh = int(NODE_FRAME_H * sh / PH)
    nfx = int(NODE_FRAME_X * sw / PW)
    nfy = int(NODE_FRAME_Y * sh / PH)
    text_w = int(TEXT_WRAP_W * sw / PW)
    text_cy = nfy + nfh // 2
    btn_y = int(BTN_Y * sh / PH)
    choice_lx = int(CHOICE_LX * sw / PW)
    choice_rx = int(CHOICE_RX * sw / PW)
    choice_text_y = int(CHOICE_TEXT_Y * sh / PH)
    trace_y = int(TRACE_Y * sh / PH)

    img = _rgba_to_1bit(_load_background(sw, sh))

    seal_seed = node_id or scene_text or ""
    scene = generate_node_pil_image(seal_seed, sw_scene, sh_scene)
    _paste_1bit(img, scene, sx, sy)

    draw = ImageDraw.Draw(img)
    body_font = _get_font(max(7, int(TEXT_BODY_SIZE * sh / PH)))
    node_font = _get_font(max(5, int(NODE_ID_TEXT_SIZE * sh / PH)))
    choice_font = _get_font(max(7, int(9 * sh / PH)))

    if node_id:
        nid_x = nfx + nfw - int(nfw * NODE_FRAME_BORDER)
        nid_y = nfy + int(nfh * NODE_FRAME_BORDER)
        draw.text((nid_x, nid_y), node_id, fill=0, font=node_font, anchor="ra")

    display_text = scene_text or ""
    if status == STATUS_ENCOUNTER:
        display_text = scene_text or "Someone else was here."

    lines = _wrap_text(display_text, body_font, text_w)
    _draw_centered_lines(draw, lines, nfx + nfw // 2, text_cy, body_font)

    if trace:
        trace_font = _get_font(max(6, int(7 * sh / PH)))
        tw = trace_font.getlength(trace)
        draw.text(((sw - tw) / 2, trace_y), trace, fill=0, font=trace_font)

    if use_restart or status == STATUS_GAME_OVER:
        rfont = _get_font(max(8, int(10 * sh / PH)))
        label = "[ restart ]"
        rw = rfont.getlength(label)
        draw.text(((sw - rw) / 2, btn_y - int(BTN_SIZE * sh / PH) // 2 - 18),
                  label, fill=0, font=rfont)
    else:
        labels = []
        for ch in choices[:2]:
            pfx = "\u21BA " if getattr(ch, "is_cross", False) else ""
            labels.append(pfx + ch.label)
        for cx, label in [(choice_lx, labels[0] if labels else ""),
                          (choice_rx, labels[1] if len(labels) > 1 else "")]:
            if not label:
                continue
            lw = choice_font.getlength(label)
            draw.text((cx - lw / 2, choice_text_y), label, fill=0, font=choice_font)

    return img


def render_to_png_bytes(player_id, scene_text, choices, trace,
                        status, node_id=None, node_title=None,
                        encounter_text=None, use_restart=False,
                        screen_w=PW, screen_h=PH) -> bytes:
    img = render_player_screen(
        player_id=player_id,
        scene_text=scene_text,
        choices=choices,
        trace=trace,
        status=status,
        node_id=node_id,
        node_title=node_title,
        encounter_text=encounter_text,
        use_restart=use_restart,
        screen_w=screen_w,
        screen_h=screen_h,
    )
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

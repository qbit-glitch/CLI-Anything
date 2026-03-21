"""GIMP CLI - Cairo 2D vector renderer.

Provides a CairoRenderer class for drawing shapes, text, particles, paths,
and gradients to an in-memory surface with optional Cairo acceleration.

Falls back to Pillow when PyCairo is not installed.
"""

from __future__ import annotations

import math
import os
import struct
import zlib
from typing import Optional

try:
    import cairo
    HAS_CAIRO = True
except ImportError:
    HAS_CAIRO = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class CairoRenderer:
    """2D vector renderer backed by Cairo or Pillow.

    Args:
        width: Surface width in pixels.
        height: Surface height in pixels.
    """

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self._surface = None
        self._ctx = None
        self._pil_image = None
        self._pil_draw = None

        if HAS_CAIRO:
            self._surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
            self._ctx = cairo.Context(self._surface)
        elif HAS_PIL:
            self._pil_image = Image.new("RGBA", (width, height), (0, 0, 0, 255))
            self._pil_draw = ImageDraw.Draw(self._pil_image)
        else:
            # Fallback: store raw RGBA bytes
            self._raw = bytearray(width * height * 4)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_source_rgba(self, color: tuple):
        """Set Cairo source color from (r, g, b[, a]) tuple with values 0-1."""
        if not HAS_CAIRO or self._ctx is None:
            return
        if len(color) == 3:
            self._ctx.set_source_rgba(color[0], color[1], color[2], 1.0)
        else:
            self._ctx.set_source_rgba(color[0], color[1], color[2], color[3])

    def _pil_color(self, color: tuple) -> tuple:
        """Convert 0-1 float color to 0-255 int RGBA tuple for Pillow."""
        if len(color) == 3:
            r, g, b = color
            a = 1.0
        else:
            r, g, b, a = color
        return (
            int(round(r * 255)),
            int(round(g * 255)),
            int(round(b * 255)),
            int(round(a * 255)),
        )

    def _apply_transform(self, transform: dict):
        """Apply transform dict to Cairo context (translate, rotate, scale)."""
        if not HAS_CAIRO or self._ctx is None:
            return
        tx = transform.get("translate_x", 0.0)
        ty = transform.get("translate_y", 0.0)
        rot = transform.get("rotate", 0.0)  # degrees
        sx = transform.get("scale_x", 1.0)
        sy = transform.get("scale_y", 1.0)
        if tx or ty:
            self._ctx.translate(tx, ty)
        if rot:
            self._ctx.rotate(math.radians(rot))
        if sx != 1.0 or sy != 1.0:
            self._ctx.scale(sx, sy)

    def _apply_style(self, style: dict, fill: bool = True):
        """Apply fill/stroke from style dict and execute fill+stroke."""
        if not HAS_CAIRO or self._ctx is None:
            return
        fill_color = style.get("fill", (1.0, 1.0, 1.0, 1.0))
        stroke_color = style.get("stroke", None)
        stroke_width = style.get("stroke_width", 1.0)

        if fill_color and fill:
            self._set_source_rgba(fill_color)
            if stroke_color:
                self._ctx.fill_preserve()
            else:
                self._ctx.fill()

        if stroke_color:
            self._set_source_rgba(stroke_color)
            self._ctx.set_line_width(stroke_width)
            self._ctx.stroke()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear(self, color: tuple = (0.0, 0.0, 0.0, 1.0)):
        """Clear the surface with a solid color.

        Args:
            color: (r, g, b, a) floats in range [0, 1].
        """
        if HAS_CAIRO and self._ctx is not None:
            self._ctx.save()
            self._ctx.set_operator(cairo.OPERATOR_SOURCE)
            self._set_source_rgba(color)
            self._ctx.paint()
            self._ctx.restore()
        elif HAS_PIL and self._pil_image is not None:
            c = self._pil_color(color)
            self._pil_image = Image.new("RGBA", (self.width, self.height), c)
            self._pil_draw = ImageDraw.Draw(self._pil_image)
        else:
            r, g, b = int(color[0] * 255), int(color[1] * 255), int(color[2] * 255)
            a = int(color[3] * 255) if len(color) > 3 else 255
            for i in range(self.width * self.height):
                base = i * 4
                self._raw[base] = r
                self._raw[base + 1] = g
                self._raw[base + 2] = b
                self._raw[base + 3] = a

    def render_shape(self, shape_type: str, params: dict, transform: dict, style: dict):
        """Draw a shape on the surface.

        Args:
            shape_type: "rect", "ellipse", "polygon", or "path".
            params: Shape-specific parameters.
                rect: x, y, width, height, [corner_radius]
                ellipse: cx, cy, rx, ry
                polygon: points (list of (x,y) tuples)
                path: d (SVG path string, basic M/L/Z support)
            transform: translate_x, translate_y, rotate, scale_x, scale_y.
            style: fill (rgba tuple), stroke (rgba tuple), stroke_width.
        """
        if HAS_CAIRO and self._ctx is not None:
            self._ctx.save()
            self._apply_transform(transform)

            if shape_type == "rect":
                x = params.get("x", 0)
                y = params.get("y", 0)
                w = params.get("width", 10)
                h = params.get("height", 10)
                r = params.get("corner_radius", 0)
                if r > 0:
                    # Rounded rectangle via arcs
                    r = min(r, w / 2, h / 2)
                    self._ctx.new_path()
                    self._ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
                    self._ctx.arc(x + w - r, y + r, r, 3 * math.pi / 2, 0)
                    self._ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
                    self._ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
                    self._ctx.close_path()
                else:
                    self._ctx.rectangle(x, y, w, h)

            elif shape_type == "ellipse":
                cx = params.get("cx", 0)
                cy = params.get("cy", 0)
                rx = params.get("rx", 10)
                ry = params.get("ry", 10)
                self._ctx.save()
                self._ctx.translate(cx, cy)
                self._ctx.scale(rx, ry)
                self._ctx.arc(0, 0, 1, 0, 2 * math.pi)
                self._ctx.restore()

            elif shape_type == "polygon":
                points = params.get("points", [])
                if points:
                    self._ctx.move_to(*points[0])
                    for pt in points[1:]:
                        self._ctx.line_to(*pt)
                    self._ctx.close_path()

            elif shape_type == "path":
                d = params.get("d", "")
                self._parse_svg_path(d)

            self._apply_style(style)
            self._ctx.restore()

        elif HAS_PIL and self._pil_draw is not None:
            fill_color = self._pil_color(style.get("fill", (1.0, 1.0, 1.0, 1.0)))
            stroke_color = None
            raw_stroke = style.get("stroke")
            if raw_stroke:
                stroke_color = self._pil_color(raw_stroke)

            if shape_type == "rect":
                x = params.get("x", 0)
                y = params.get("y", 0)
                w = params.get("width", 10)
                h = params.get("height", 10)
                outline = stroke_color if stroke_color else None
                self._pil_draw.rectangle([x, y, x + w, y + h], fill=fill_color, outline=outline)

            elif shape_type == "ellipse":
                cx = params.get("cx", 0)
                cy = params.get("cy", 0)
                rx = params.get("rx", 10)
                ry = params.get("ry", 10)
                bbox = [cx - rx, cy - ry, cx + rx, cy + ry]
                outline = stroke_color if stroke_color else None
                self._pil_draw.ellipse(bbox, fill=fill_color, outline=outline)

            elif shape_type == "polygon":
                points = params.get("points", [])
                if points:
                    outline = stroke_color if stroke_color else None
                    self._pil_draw.polygon(points, fill=fill_color, outline=outline)

    def _parse_svg_path(self, d: str):
        """Parse minimal SVG path string (M, L, C, Z commands) onto Cairo context."""
        if not HAS_CAIRO or self._ctx is None:
            return
        import re
        tokens = re.findall(r'[MmLlCcZz]|[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?', d)
        i = 0
        cmd = None
        cx, cy = 0.0, 0.0
        self._ctx.new_path()
        while i < len(tokens):
            tok = tokens[i]
            if tok in 'MmLlCcZz':
                cmd = tok
                i += 1
            else:
                if cmd == 'M':
                    cx, cy = float(tokens[i]), float(tokens[i + 1])
                    self._ctx.move_to(cx, cy)
                    i += 2
                    cmd = 'L'
                elif cmd == 'm':
                    dx, dy = float(tokens[i]), float(tokens[i + 1])
                    cx += dx; cy += dy
                    self._ctx.move_to(cx, cy)
                    i += 2
                    cmd = 'l'
                elif cmd == 'L':
                    cx, cy = float(tokens[i]), float(tokens[i + 1])
                    self._ctx.line_to(cx, cy)
                    i += 2
                elif cmd == 'l':
                    dx, dy = float(tokens[i]), float(tokens[i + 1])
                    cx += dx; cy += dy
                    self._ctx.line_to(cx, cy)
                    i += 2
                elif cmd == 'C':
                    x1, y1 = float(tokens[i]), float(tokens[i + 1])
                    x2, y2 = float(tokens[i + 2]), float(tokens[i + 3])
                    cx, cy = float(tokens[i + 4]), float(tokens[i + 5])
                    self._ctx.curve_to(x1, y1, x2, y2, cx, cy)
                    i += 6
                elif cmd == 'c':
                    x1, y1 = cx + float(tokens[i]), cy + float(tokens[i + 1])
                    x2, y2 = cx + float(tokens[i + 2]), cy + float(tokens[i + 3])
                    dx, dy = float(tokens[i + 4]), float(tokens[i + 5])
                    cx += dx; cy += dy
                    self._ctx.curve_to(x1, y1, x2, y2, cx, cy)
                    i += 6
                elif cmd in ('Z', 'z'):
                    self._ctx.close_path()
                else:
                    i += 1

    def render_text(self, text: str, font: str, size: float, position: tuple, color: tuple):
        """Render text at a position.

        Args:
            text: The string to render.
            font: Font family name (e.g. "sans-serif").
            size: Font size in points.
            position: (x, y) tuple for the text origin.
            color: (r, g, b[, a]) floats in [0, 1].
        """
        x, y = position
        if HAS_CAIRO and self._ctx is not None:
            self._ctx.save()
            self._set_source_rgba(color)
            self._ctx.select_font_face(
                font,
                cairo.FONT_SLANT_NORMAL,
                cairo.FONT_WEIGHT_NORMAL,
            )
            self._ctx.set_font_size(size)
            self._ctx.move_to(x, y)
            self._ctx.show_text(text)
            self._ctx.restore()

        elif HAS_PIL and self._pil_draw is not None:
            pil_color = self._pil_color(color)
            try:
                pil_font = ImageFont.truetype(font, int(size))
            except Exception:
                try:
                    pil_font = ImageFont.load_default()
                except Exception:
                    pil_font = None
            self._pil_draw.text((x, y), text, fill=pil_color, font=pil_font)

    def render_particles(self, particle_state):
        """Draw particles from an Nx8 array [x, y, size, alpha, r, g, b, age].

        Args:
            particle_state: Nx8 numpy array or list of 8-element sequences.
        """
        if particle_state is None:
            return

        # Convert to list of rows if numpy
        if HAS_NUMPY and isinstance(particle_state, np.ndarray):
            rows = particle_state
        else:
            rows = particle_state

        for row in rows:
            px, py, size, alpha, r, g, b = (
                float(row[0]), float(row[1]), float(row[2]),
                float(row[3]), float(row[4]), float(row[5]), float(row[6]),
            )
            radius = max(0.5, size / 2.0)
            color = (r, g, b, alpha)

            if HAS_CAIRO and self._ctx is not None:
                self._ctx.save()
                self._set_source_rgba(color)
                self._ctx.arc(px, py, radius, 0, 2 * math.pi)
                self._ctx.fill()
                self._ctx.restore()

            elif HAS_PIL and self._pil_draw is not None:
                pil_color = self._pil_color(color)
                bbox = [px - radius, py - radius, px + radius, py + radius]
                self._pil_draw.ellipse(bbox, fill=pil_color)

    def render_path(self, points: list, trim_start: float, trim_end: float, style: dict):
        """Draw a bezier path with trim (partial draw).

        Args:
            points: List of (x, y) control points defining the path.
            trim_start: 0.0-1.0, where to start drawing.
            trim_end: 0.0-1.0, where to stop drawing.
            style: fill, stroke, stroke_width.
        """
        if not points:
            return

        trim_start = max(0.0, min(1.0, trim_start))
        trim_end = max(0.0, min(1.0, trim_end))
        if trim_start >= trim_end:
            return

        # Compute trimmed subset of points
        n = len(points)
        start_idx = int(trim_start * (n - 1))
        end_idx = max(start_idx + 1, int(math.ceil(trim_end * (n - 1))))
        end_idx = min(end_idx, n - 1)
        trimmed = points[start_idx: end_idx + 1]

        if len(trimmed) < 2:
            return

        if HAS_CAIRO and self._ctx is not None:
            self._ctx.save()
            self._ctx.new_path()
            self._ctx.move_to(*trimmed[0])
            for pt in trimmed[1:]:
                self._ctx.line_to(*pt)

            stroke_color = style.get("stroke", (1.0, 1.0, 1.0, 1.0))
            stroke_width = style.get("stroke_width", 1.0)
            self._set_source_rgba(stroke_color)
            self._ctx.set_line_width(stroke_width)

            line_cap = style.get("line_cap", "round")
            if line_cap == "round":
                self._ctx.set_line_cap(cairo.LINE_CAP_ROUND)
            elif line_cap == "square":
                self._ctx.set_line_cap(cairo.LINE_CAP_SQUARE)
            else:
                self._ctx.set_line_cap(cairo.LINE_CAP_BUTT)

            self._ctx.stroke()
            self._ctx.restore()

        elif HAS_PIL and self._pil_draw is not None:
            stroke_color = self._pil_color(style.get("stroke", (1.0, 1.0, 1.0, 1.0)))
            stroke_width = int(style.get("stroke_width", 1.0))
            flat = []
            for pt in trimmed:
                flat.extend(pt)
            if len(flat) >= 4:
                self._pil_draw.line(flat, fill=stroke_color, width=stroke_width)

    def render_gradient(self, gradient_type: str, colors: list, start: tuple, end: tuple):
        """Render a linear or radial gradient fill over the entire surface.

        Args:
            gradient_type: "linear" or "radial".
            colors: List of (position, r, g, b, a) tuples. position in [0, 1].
            start: (x, y) start point for linear, or (cx, cy) center for radial.
            end: (x, y) end point for linear, or (fx, fy) focal point for radial.
        """
        if HAS_CAIRO and self._ctx is not None:
            self._ctx.save()
            if gradient_type == "linear":
                pat = cairo.LinearGradient(start[0], start[1], end[0], end[1])
            elif gradient_type == "radial":
                # Radius = distance between start (center) and end (edge point)
                radius = math.sqrt(
                    (end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2
                )
                pat = cairo.RadialGradient(
                    start[0], start[1], 0,
                    start[0], start[1], max(radius, 1.0),
                )
            else:
                self._ctx.restore()
                return

            for stop in colors:
                pos = stop[0]
                r, g, b = stop[1], stop[2], stop[3]
                a = stop[4] if len(stop) > 4 else 1.0
                pat.add_color_stop_rgba(pos, r, g, b, a)

            self._ctx.set_source(pat)
            self._ctx.rectangle(0, 0, self.width, self.height)
            self._ctx.fill()
            self._ctx.restore()

        elif HAS_PIL and self._pil_image is not None:
            # Simple linear gradient fallback for Pillow
            if len(colors) < 2:
                return
            c0 = self._pil_color(colors[0][1:])
            c1 = self._pil_color(colors[-1][1:])

            img = self._pil_image
            draw = ImageDraw.Draw(img)

            if gradient_type == "linear":
                sx, sy = start
                ex, ey = end
                dx, dy = ex - sx, ey - sy
                length = math.sqrt(dx * dx + dy * dy)
                if length == 0:
                    return

                for px in range(self.width):
                    for py in range(self.height):
                        # Project (px,py) onto gradient vector
                        t = ((px - sx) * dx + (py - sy) * dy) / (length * length)
                        t = max(0.0, min(1.0, t))
                        r = int(c0[0] + (c1[0] - c0[0]) * t)
                        g = int(c0[1] + (c1[1] - c0[1]) * t)
                        b = int(c0[2] + (c1[2] - c0[2]) * t)
                        a = int(c0[3] + (c1[3] - c0[3]) * t)
                        img.putpixel((px, py), (r, g, b, a))
                self._pil_draw = ImageDraw.Draw(img)

    def to_png(self, path: str):
        """Save the surface to a PNG file.

        Args:
            path: Destination file path.
        """
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

        if HAS_CAIRO and self._surface is not None:
            self._surface.write_to_png(path)

        elif HAS_PIL and self._pil_image is not None:
            self._pil_image.save(path, "PNG")

        else:
            # Minimal PNG writer using only stdlib
            _write_raw_png(path, self.width, self.height, self._raw)

    def to_numpy(self):
        """Convert the surface to a NumPy RGBA uint8 array of shape (H, W, 4).

        Returns:
            numpy.ndarray with dtype uint8 if numpy available, else None.
        """
        if not HAS_NUMPY:
            return None

        if HAS_CAIRO and self._surface is not None:
            self._surface.flush()
            buf = self._surface.get_data()
            arr = np.frombuffer(buf, dtype=np.uint8).reshape(
                (self.height, self.width, 4)
            ).copy()
            # Cairo uses BGRA (on little-endian), convert to RGBA
            arr = arr[:, :, [2, 1, 0, 3]]
            return arr

        elif HAS_PIL and self._pil_image is not None:
            return np.array(self._pil_image.convert("RGBA"))

        else:
            arr = np.frombuffer(bytes(self._raw), dtype=np.uint8).reshape(
                (self.height, self.width, 4)
            ).copy()
            return arr


# ---------------------------------------------------------------------------
# Minimal stdlib PNG writer (no external deps)
# ---------------------------------------------------------------------------

def _write_raw_png(path: str, width: int, height: int, raw: bytearray):
    """Write a minimal RGBA PNG using only stdlib (struct + zlib)."""
    def chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = chunk(b"IHDR", ihdr_data)

    # IDAT — raw RGBA scanlines with filter byte 0
    scanlines = bytearray()
    for row in range(height):
        scanlines.append(0)  # filter type: None
        offset = row * width * 4
        scanlines.extend(raw[offset: offset + width * 4])

    compressed = zlib.compress(bytes(scanlines), 9)
    idat = chunk(b"IDAT", compressed)

    # IEND
    iend = chunk(b"IEND", b"")

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")  # PNG signature
        f.write(ihdr)
        f.write(idat)
        f.write(iend)

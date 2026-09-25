"""Paint library for program paintings.

A painting is a Python program that paints on a `Canvas` with real paint
operations. See `canvas.Canvas` for the operations and `noise` for fields.
"""

from .canvas import Canvas, rgb
from .noise import cellular, fbm, mix, smoothstep, value_noise

__all__ = ["Canvas", "cellular", "fbm", "mix", "rgb", "smoothstep", "value_noise"]

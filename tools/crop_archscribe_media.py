#!/usr/bin/env python3
"""Crop Archscribe PNG/GIF outputs to a Slide delivery viewport."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


def parse_box(raw: str) -> tuple[int, int, int, int]:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("box must be x,y,width,height")
    x, y, width, height = (int(part) for part in parts)
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("crop coordinates must be non-negative and dimensions must be positive")
    return x, y, width, height


def checked_bounds(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x, y, width, height = box
    if x + width > image.width or y + height > image.height:
        raise ValueError(f"crop {box} exceeds image bounds {image.width}x{image.height}")
    return x, y, x + width, y + height


def temporary_path(path: Path, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.stem}.crop.", suffix=suffix, dir=path.parent)
    os.close(descriptor)
    return Path(name)


def apply_mask(image: Image.Image, mask: tuple[int, int, int, int] | None) -> Image.Image:
    if mask is None:
        return image
    left, top, right, bottom = checked_bounds(image, mask)
    draw = ImageDraw.Draw(image)
    draw.rectangle((left, top, right - 1, bottom - 1), fill=image.getpixel((0, 0)))
    return image


def visible_margin(image: Image.Image) -> int:
    background = Image.new(image.mode, image.size, image.getpixel((0, 0)))
    bounds = ImageChops.difference(image, background).getbbox()
    if bounds is None:
        return min(image.size) // 2
    left, top, right, bottom = bounds
    return min(left, top, image.width - right, image.height - bottom)


def require_margin(margin: int, required: float, label: str) -> None:
    if margin < required:
        raise ValueError(f"{label} visible content margin {margin}px is below required {required:g}px")


def crop_png(
    path: Path,
    box: tuple[int, int, int, int],
    mask: tuple[int, int, int, int] | None,
    safe_margin: float,
) -> int:
    output = temporary_path(path, ".png")
    try:
        with Image.open(path) as source:
            cropped = source.crop(checked_bounds(source, box))
            cropped = apply_mask(cropped, mask)
            margin = visible_margin(cropped.convert("RGB"))
            require_margin(margin, safe_margin, "PNG")
            cropped.save(output, format="PNG", optimize=True)
        os.replace(output, path)
        return margin
    finally:
        output.unlink(missing_ok=True)


def crop_gif(
    path: Path,
    box: tuple[int, int, int, int],
    mask: tuple[int, int, int, int] | None,
    safe_margin: float,
) -> int:
    output = temporary_path(path, ".gif")
    frames: list[Image.Image] = []
    durations: list[int] = []
    try:
        with Image.open(path) as source:
            loop = int(source.info.get("loop", 0))
            for index in range(source.n_frames):
                source.seek(index)
                cropped = source.convert("RGB").crop(checked_bounds(source, box))
                frames.append(apply_mask(cropped, mask))
                durations.append(int(source.info.get("duration", 50)))
        margin = min(visible_margin(frame) for frame in frames)
        require_margin(margin, safe_margin, "GIF")
        frames[0].save(
            output,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=loop,
            disposal=2,
            optimize=True,
        )
        os.replace(output, path)
        return margin
    finally:
        output.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crop Archscribe delivery media without changing its editable source")
    parser.add_argument("--gif", required=True, type=Path)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--box", required=True)
    parser.add_argument("--mask", help="Optional x,y,width,height box in cropped-image coordinates")
    parser.add_argument("--safe-margin", type=float, default=0, help="Required blank margin around visible pixels")
    args = parser.parse_args()
    box = parse_box(args.box)
    mask = parse_box(args.mask) if args.mask else None
    gif_margin = crop_gif(args.gif.resolve(), box, mask, args.safe_margin)
    png_margin = crop_png(args.png.resolve(), box, mask, args.safe_margin)
    print(json.dumps({
        "gif": str(args.gif),
        "png": str(args.png),
        "crop": box,
        "mask": mask,
        "minimumRasterMargin": min(gif_margin, png_margin),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

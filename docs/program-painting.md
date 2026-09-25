# Program Painting (paint mode)

Paint mode renders on the server. The agent writes a Python painting program
(`studio/painting.py` in its workspace) against `code_monet.paintlib`, runs it
with the `paint` tool, looks at the result, edits the program, and runs it
again. Every successful run is a **version**. Clients never rasterize paint
strokes; they reveal server-rendered keyframe images along the recorded brush
footprints, so viewers watch each version paint in stroke by stroke.

Plotter mode is unchanged (vector paths, `draw_paths` / `generate_svg`).

## Version assets

Each version is written to `{user_dir}/paintings/{token}/` where `token` is a
random 32-char hex capability id. Files:

| File | Content |
|---|---|
| `kf_00.jpg` … `kf_NN.jpg` | Keyframe images: the finished look at the end of each painting stage |
| `final.png` | Final image (identical content to the last keyframe) |
| `preview.jpg` | Final image downscaled to ≤1200px wide |
| `reveal.json` | Stage labels and brush footprints (below) |

Served without auth (capability URL, like share tokens):

```
GET /painting-assets/{user_id}/{token}/{file}
```

`file` must match `kf_\d{2}\.jpg|final\.png|preview\.jpg|reveal\.json`.
Responses are immutable (`Cache-Control: public, max-age=31536000, immutable`).

### reveal.json

```json
{
  "width": 1600,
  "height": 1200,
  "keyframes": [
    {
      "label": "ground",
      "image": "kf_00.jpg",
      "ops": [
        ["a", 0, 0, 1600, 1200],
        ["s", 14.0, 120.5, 300.0, 180.0, 310.2, 240.0, 305.9]
      ]
    }
  ]
}
```

Coordinates are image pixels (`width` x `height`, typically 2x the logical
canvas size). Ops, in paint order:

- `["s", width, x0, y0, x1, y1, ...]` — brush stroke: a polyline (2–8 points)
  of the given width. Reveal the keyframe image through a round-capped,
  round-joined stroke of this path.
- `["a", x0, y0, x1, y1]` — area op (fill, wash, glaze, smear, crisp shape):
  reveal the keyframe image inside this rectangle with a quick soft wipe
  (top to bottom).

## WebSocket

Server → client when a version is ready:

```json
{
  "type": "painting_version",
  "piece_number": 12,
  "version": 3,
  "asset_base": "/painting-assets/<user_id>/<token>/",
  "image_width": 1600,
  "image_height": 1200,
  "stages": ["ground", "sky", "sea", "boat"]
}
```

`asset_base` is relative to the API base URL. The agent does not wait for the
animation; clients never send `animation_done` for versions.

`init` (on connect) carries the current version, if any, as
`"painting": {"piece_number", "version", "asset_base", "image_width", "image_height"}`
(or `null`). Clients show its `final.png` immediately without animating.

`new_canvas` and `clear` reset the painting to none (blank canvas).

## Client playback

- The canvas shows a **base image**: the previous version's final (or the blank
  canvas for version 1), drawn to fill the logical canvas.
- On `painting_version` (for the current piece, not while viewing a gallery
  piece): fetch `reveal.json`, preload keyframes, then for each keyframe in
  order reveal it over the current picture following its ops in order:
  strokes through their footprint path, area ops by a short wipe of their
  rect. Pace: about 12 ms per stroke op and 250 ms per area op, but compress so
  a keyframe takes at most 6 s and a whole version at most 45 s. Many ops are
  revealed per frame.
- After the last keyframe, swap to `final.png`. It becomes the base image for
  the next version.
- If another version arrives while animating, finish the current one
  immediately (jump to its final) and start the new one.
- The current stage label (`keyframes[i].label`) may be shown as status.
- Human strokes (rose) remain vector strokes drawn on top.

## Gallery

A piece saved from program painting has `"format": "raster"` and
`"image_token": "<token>"` in its gallery JSON (strokes may be empty).
Thumbnail/OG/share endpoints serve the stored final image. Clients showing a
raster gallery piece load `/painting-assets/{user_id}/{token}/final.png`;
`GET /gallery/{n}/strokes` and the public strokes endpoint include `format`,
`image_url` (absolute-path URL of `final.png`) for raster pieces.

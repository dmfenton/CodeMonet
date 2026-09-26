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
| `painting.py` | The painting program that rendered this version (served as `text/plain; charset=utf-8`). The server reads `studio/painting.py` (refusing a symlink), runs a throwaway copy, and after the run writes those exact bytes here as a fresh regular file, so a program that rewrites itself cannot change what is published. |

Served without auth (capability URL, like share tokens):

```
GET /painting-assets/{user_id}/{token}/{file}
```

`file` must match `kf_\d{2}\.jpg|final\.png|preview\.jpg|reveal\.json|painting\.py`.
Responses are immutable (`Cache-Control: public, max-age=31536000, immutable`)
and carry `X-Content-Type-Options: nosniff`. Programs are public for pieces
in public galleries, like their images. Only server-written files are served
(see [Untrusted programs](#untrusted-programs)).

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

## Untrusted programs

`studio/painting.py` is written by the agent, and the agent reads user
directions and nudges, so a program must be treated as arbitrary,
possibly prompt-injected code. Whatever it can read can end up in its
outputs, and those outputs (images, reveal log, program) are public for
pieces in public galleries.

What the server enforces:

- **Run.** `python -I -m code_monet.paintlib.runner` in a fresh temporary
  directory (cwd, `HOME` and `TMPDIR`) with an environment of exactly `PATH`,
  `HOME`, `TMPDIR` and `LANG` — nothing inherited from the server
  (`program_painting.paint_env`). `-I` ignores `PYTHON*` variables and keeps
  cwd and user site-packages off `sys.path`. The runner lives in `paintlib`
  so the process imports only the paint library, numpy, scipy and PIL, never
  server config (which loads secrets from SSM at import) or the agent SDK.
  The run is killed after `PAINT_TIMEOUT_S`.
- **Publish.** The program bytes are read before the run without following a
  symlink, and the server itself writes them as the version's `painting.py`
  (a child process that outlives the run could still overwrite it; see below).
- **Read back.** Every reader that serves or publishes a version file — the
  asset route, gallery raster lookups, public thumbnails/OG images, and the
  workspace render — goes through `workspace.assets.version_asset`: a
  well-formed token and file name, and a regular, single-link file whose real
  path is exactly `{user_dir}/paintings/{token}/{file}` (the user directory may
  sit behind the server-configured data-volume link). Planted symlinks below
  the user directory, hard links to other files, and path escapes are refused.
  This stops *live* links that would keep exposing a file's later contents;
  it cannot stop a program from copying bytes it can read into its output.

What is **not** isolated — the program runs as the server's OS user in the
server container, so a scrubbed environment removes the easy leak (printing
`os.environ`) but is not a boundary:

- Filesystem: it can read and write whatever the server can — the auth
  database, every user's workspace (including other versions' assets), the
  Anthropic identity token under `/run/secrets/anthropic/`, and on Linux the
  server's own environment via `/proc/<pid>/environ`. It can copy any of that
  into its own output.
- Network: unrestricted, including the instance metadata service; the
  `drawing-agent` container keeps IMDS access (dmfenton/compute
  `deploy/harden-imds.sh`), so the instance role's SSM parameters are
  reachable.
- Processes and resources: a daemonized child outlives the timeout; there are
  no memory or CPU limits.
- The paint agent also has the `Bash` tool in the same container, with the
  same reach, so isolating `paint` alone does not bound a prompt-injected
  agent.

A real boundary needs OS-level isolation of both the paint run and the
agent's shell: a separate user with no access to server data or secrets, no
network, and process/memory limits (for example a sandbox container, or
Landlock plus seccomp in the child).

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
  "stages": ["ground", "sky", "sea", "boat"],
  "ops": 4180
}
```

`asset_base` is relative to the API base URL. `ops` is the number of reveal ops
in the version; every version re-renders the whole program, so it is the mark
count of the picture as of that version. The agent does not wait for the
animation; clients never send `animation_done` for versions.

`init` (on connect) carries the current version, if any (or `null`):

```json
"painting": {
  "piece_number": 12,
  "version": 3,
  "asset_base": "/painting-assets/<user_id>/<token>/",
  "image_width": 1600,
  "image_height": 1200,
  "versions": [
    {
      "version": 1,
      "asset_base": "/painting-assets/<user_id>/<token1>/",
      "image_width": 1600,
      "image_height": 1200,
      "stages": ["ground", "sky"],
      "ops": 2100,
      "created_at": "2026-09-26T12:00:00+00:00"
    }
  ]
}
```

The top-level fields describe the latest version; clients show its `final.png`
immediately without animating. `versions` lists every version of the current
piece, oldest first (the last entry is the latest). `init` also carries
top-level `"title"` (set by the agent's `name_piece` tool, else `null`) and
`"prompt"` (the `direction` of the `new_canvas` that started the piece, else
`null`) whether or not a version exists yet. When the agent names the piece,
the title is also broadcast live as `piece_title` (see below).

`new_canvas` and `clear` reset the painting to none (blank canvas) and its
version list to empty. `new_canvas` with a `direction` records it as the new
piece's prompt (after saving the previous piece); `new_canvas` without one and
`clear` reset the prompt to `null`. A paint run that finishes after the
painting was reset is discarded rather than recorded into the new piece.

`workspace.json` stores the list as `painting_versions` and also writes the
latest version under the legacy `painting` key so an older server can load it.
Pieces in progress when version history shipped have only their latest version
in history.

### Turn state and title

The server is the authority for whether the painter is working and what the
piece is called:

- `{"type": "turn_state", "active": true|false}` when an agent turn starts and
  ends (always `false` after a turn, even one that failed). `init.turn_active`
  reports the state at connect time. Clients show the painter as thinking while
  a turn is active and nothing else is streaming, instead of idle.
- `{"type": "piece_title", "piece_number": 12, "title": "Harbor Fog"}` after a
  successful `name_piece`: the naming agent's orchestrator stores the title in
  its own workspace and broadcasts it. `init.title` seeds it on connect; clients
  ignore a title for a different piece and do not read it from the tool call.

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
`"image_token": "<token>"` (the final version) in its gallery JSON (strokes may
be empty), plus every version of the piece, oldest first:

```json
"prompt": "a stormy sea",
"versions": [
  {
    "version": 1,
    "token": "<token1>",
    "image_width": 1600,
    "image_height": 1200,
    "stages": ["ground", "sky"],
    "ops": 2100,
    "created_at": "2026-09-26T12:00:00+00:00"
  }
]
```

`prompt` is written for every piece (`null` when started without a direction).
Pieces saved before version history have no `versions` or `prompt`; readers
treat them as a single version built from `image_token` (stages `[]`, ops `0`).

The gallery listing's `stroke_count` is the final version's `ops` for raster
pieces (vector stroke count otherwise, including legacy raster pieces).
A malformed `versions` list reads as the legacy single version, and an
unreadable piece is skipped in listings rather than failing them.

Thumbnail/OG/share endpoints serve the stored final image. Clients showing a
raster gallery piece load `/painting-assets/{user_id}/{token}/final.png`.
`GET /gallery/{n}/strokes` and the public strokes endpoint
(`GET /public/gallery/{user_id}/{piece_id}/strokes`) include `format`,
`image_url` (absolute-path URL of `final.png`, raster only), `title`, `prompt`,
`stroke_count`, `drawing_style`, and `versions` — the same shape as
`init.painting.versions` (`version`, `asset_base`, `image_width`,
`image_height`, `stages`, `ops`, `created_at`). Strokes-format pieces return
`versions: []`; legacy raster pieces return one synthesized version. Clients
replay a piece version by version from `versions`, and can read each
version's program at `{asset_base}painting.py`.

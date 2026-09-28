# Program Painting (paint mode)

Paint mode renders on the server. The agent writes a Python painting program
(`studio/painting.py` in its workspace) against `code_monet.paintlib`, runs it
with the `paint` tool, looks at the result, edits the program, and runs it
again. Every successful run is a **version**. Clients never rasterize paint
strokes; they reveal server-rendered keyframe images along the recorded brush
footprints, so viewers watch each version paint in stroke by stroke.

Plotter mode is unchanged (vector paths, `draw_paths` / `generate_svg`).

## Revisions paint over the canvas

A piece is painted, then revised the way a painter revises: by painting over it.
The first version's program paints on a blank canvas. Each later run starts with
`cv` holding the current version's canvas — its paint, relief, tooth and surface
settings, saved as the version's `canvas.npz` (float16, ~14 MB at 1600x1200,
never served) — and paints only what it adds or changes. So a revision's strokes
*are* its new strokes: viewers watch exactly those land on the current picture.

**Erasing is not allowed.** A revision only moves the picture forward: new forms
are painted directly over old ones, and where parts of an old form must go, what
belongs there is painted over just those parts, as finished paint, after the new
form. `cv.ground(...)` primes the canvas of a piece's first version only; in a
revision it raises (the run fails and the picture is unchanged). Painting an area
out to background before repainting it cannot be told apart from layering
mechanically, so the paint prompt and library reference state it as a rule.

- After a successful run the server archives the program as
  `studio/versions/v{n}.py` and resets `studio/painting.py` to a short stub
  (re-running a whole program would paint it all again on top). A failed run
  leaves the program in place to fix.
- The runner gets `--previous <latest version dir>` when that version has a
  canvas state; versions from before canvas states were saved start fresh.
- `reveal.json` carries `"continues": true` when the run painted over the
  previous canvas. A version's `ops` is then the picture's total marks
  (previous `ops` + this run's).
- Only the latest version's `canvas.npz` is kept: it is deleted when the next
  version is recorded, and when the piece ends (new canvas / clear).
- Each version's published `painting.py` is that revision's program; a piece's
  full recipe is its versions' programs in order.


## Version assets

Each version is written to `{user_dir}/paintings/{token}/` where `token` is a
random 32-char hex capability id. Files:

| File | Content |
|---|---|
| `kf_00.jpg` … `kf_NN.jpg` | Keyframe images: the finished look at the end of each painting stage |
| `final.png` | Final image (identical content to the last keyframe) |
| `preview.jpg` | Final image downscaled to ≤1200px wide |
| `reveal.json` | Stage labels and brush footprints (below) |
| `performance.bin` | The performance: every pixel each paint op changed, in paint order, streamed live while the program runs ([Live performance](#live-performance)) |
| `painting.py` | The painting program that rendered this version (served as `text/plain; charset=utf-8`). The server reads `studio/painting.py` (refusing a symlink), runs a throwaway copy, and after the run writes those exact bytes here as a fresh regular file, so a program that rewrites itself cannot change what is published. |

Served without auth (capability URL, like share tokens):

```
GET /painting-assets/{user_id}/{token}/{file}
```

`file` must match
`kf_\d{2}\.jpg|final\.png|preview\.jpg|reveal\.json|painting\.py|performance\.bin`.
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
  reveal the keyframe image inside this rectangle with broad brush sweeps.

A keyframe is the picture after its ops, so each op reveals whatever the
keyframe holds inside its footprint. The library keeps that close to the op's
own paint: an area op covering at least 2% of the canvas gets a keyframe of
its own (closed on the surface just before it, and again just after it), so a
lay-in fill shows only the fill and the marks painted over it reveal
themselves. Stages also split every 2500 ops; at most 64 keyframes are kept
(adjacent small ones merge).

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
- Plotter mode's `generate_svg` code (`tools/python_sandbox.py`) runs the
  same way — `python -I` from a throwaway directory with `paint_env` — so it
  has the same scrubbed environment and the same residual reach.

A real boundary needs OS-level isolation of both the paint run and the
agent's shell: a separate user with no access to server data or secrets, no
network, and process/memory limits (for example a sandbox container, or
Landlock plus seccomp in the child).

## Live performance

Viewers watch the program paint while it runs. The paint library records
every paint op right after it runs: it diffs the op's box against a shadow of
the surface from before the op and emits **patches** — the finished (lit,
varnished) colour of the pixels the op changed, plus each pixel's draw order
within its stroke. The runner appends patches to `performance.bin` in the
version's directory as the program paints.

**The pixel order is a painter's** (`paintlib/performance.py`,
`paintlib/brushplan.py`):

- A brush mark (`stroke`, `dab`, `flow`, ...) is one patch whose pixels appear
  along its path.
- `paint_region` lays its marks in a painter's traversal, not at random: the
  region is worked in patches of about 7x7 marks, back and forth along its
  long axis; inside a patch, marks go side by side. (This is paint order, so it
  decides overlaps: the picture is the one painted in that order.)
- An area op (`fill`, `wash`, `glaze`, `smear`, `blur`, `striate`, `crackle`,
  direct `cv.rgb` edits, and the finishing varnish/lighting) is laid in by a
  **brush plan**: broad strokes whose union is exactly the op's changed
  pixels — elongated, slightly turned lozenges with ragged edges on a
  jittered brickwork grid along the region's main axis, row by row, back and
  forth, fronts ragged like bristles. Each planned stroke is its own patch.
  Pixel values are the op's own; only the pattern and timing are the plan.
- A crisp `shape` is outlined first (strokes travelling around its edge), then
  filled in the same way.
- `ground` prepares the canvas: the performance starts on the primed canvas
  (one instant patch).

**Timing is a time-lapse of one hand**: strokes follow each other (never two
at once); each takes time for how much it visibly changes the picture —
`0.5 ms x change^0.85`, change = summed colour change in pixels of full
change, clamped to 5–2000 ms — so broad lay-ins and the subject's shapes take
time and faint texture dabs go by quickly; the brush travels between strokes
(40 px/ms, at most 40 ms). Times are *hand time* in ms; clients play them at a
chosen speed (the studio plays live runs at 3x: a piece in about 1–2.5 min).

**Stream format** — append-only frames, readable while being written:

```
frame := part(json) part(index) part(color) part(order);  part := u32le len | bytes
```

- Header (first frame, other parts empty):
  `{"kind": "header", "width": W, "height": H, "format": 1, "base": "blank" | "previous"}`.
  `previous`: a revision, performed over the previous version's `final.png`.
  The studio plays first versions at 3x and revisions at 1x, sped up just
  enough never to lag what has arrived by more than 60 s of video
  (`playbackRate`): small revisions play at their natural pace, big repaints
  and long pieces finish about a minute after their strokes arrive.
- Chunk: the patches painted in ~0.5 s of run time (so a live viewer is at
  most about that far behind the program):
  - json `{"kind": "chunk", "stage": label, "atlas": [aw, ah], "patches": n}`;
  - index: `n` records of `<f4 t_ms, <f4 dur_ms`, then `<u2` `atlas_x,
    atlas_y, w, h, x, y` (20 bytes each; patches are in paint order);
  - color: lossy WebP atlas (RGB) holding each patch's rect;
  - order: lossless WebP atlas (L) at 1/4 resolution (atlas coordinates / 4):
    per 4x4 block, `1..255` = draw order (the block appears at
    `t + dur x (order - 1) / 254`), `0` = nothing changed there (paste at
    `t + dur`). Pasting a patch's unchanged pixels is harmless: its colour is
    the current picture.
- End: `{"kind": "end", "ms": total}` after a final patch that brings the
  picture to `final.png` (varnish, lighting); or `{"kind": "error"}` if the
  program raised.

`GET .../performance.bin` of a finished stream is an immutable file. While the
run is writing it, the response follows the file as it grows
(`Cache-Control: no-store`) until the end or error frame, until the run's
directory is discarded (a failed run), or for at most the paint timeout + 30 s
and 256 MB. The stream is the program's output, like its images: clients
treat it as untrusted data (bounds-check every patch).

Measured on six local pieces (2.8k–20k ops at 1600x1200): 0.6–5.6 MB per
version, 11–41 chunks, about 1–4 s of added render time.

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

When a paint run starts (before the program runs), and if it fails:

```json
{"type": "painting_live", "piece_number": 12,
 "asset_base": "/painting-assets/<user_id>/<token>/",
 "image_width": 1600, "image_height": 1200}
{"type": "painting_live_failed", "piece_number": 12,
 "asset_base": "/painting-assets/<user_id>/<token>/"}
```

A successful run is then recorded and announced as `painting_version` with
the same `asset_base`; a client already playing that stream does not replay
it, and settles on the version's `final.png` when its playback ends. On
`painting_live_failed` the client drops the stream and shows the previous
picture. `init.painting_live` carries a run streaming at connect time (or
`null`), so a joining viewer can follow it.

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

Clients play performances; they no longer reveal keyframes.

- The canvas shows the **base**: the current version's `final.png` (blank for
  a piece with no version yet).
- `painting_live` starts a performance: play `{asset_base}performance.bin`
  over the base as it streams (see [Live performance](#live-performance)).
  The matching `painting_version` confirms it without replaying; when both
  the stream has played and the version is confirmed, it becomes the base.
  `painting_live_failed` drops it.
- A `painting_version` that did not stream live (e.g. after a reconnect)
  performs its recorded stream the same way; a version without a stream
  (recorded before performances) shows its `final.png`.
- A new performance arriving mid-performance finishes the current one (jump
  to its final) and starts the new one.
- The stage bar shows the version's stage labels; while performing, the
  current stage comes from the stream's chunk labels.
- Human strokes (rose) remain vector strokes drawn on top.

`reveal.json` and the keyframe images are still written for iOS builds
installed before performances; current clients read neither. Remove them from
the server once those builds are retired.

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
The public piece page replays a piece version by version: v1 performs over a
blank canvas, each later version over the previous version's `final.png`, at
a viewer-chosen multiple (1x/2x/4x/8x, default 2x) of the studio's pace; at 1x
no version plays longer than a minute.

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

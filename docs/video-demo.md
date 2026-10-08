# Video recognition demo

The README GIF pairs a real video with observations made by Codex after inspecting
video frames. It is not the mock provider and the footage is not generated.
It replays recorded analysis; GIF playback does not call a model.

## What was reviewed

- Procedure: [handwashing.md](../examples/handwashing.md).
- Footage: [source.webm](assets/video-demo/source.webm), 23 seconds.
- Results: [review.json](assets/video-demo/review.json), including a source SHA-256,
  the reviewer, reasons, confidence estimates, and evidence timestamps.
- Attribution: [SOURCE.md](assets/video-demo/SOURCE.md).

The local MCP server was called with a Python MCP client. Its image-content responses
were saved locally and visually inspected by Codex using the session's image-view tool.
Codex's observations were then written with the MCP `record_review` tool.
This session used a tool adapter; it did not install the server into the user's host settings.

Reviewed source times: **0.3, 1.5, 3.5, 5.5, 9.5, 12.5, 14.5, 18.5, 21.5, 22.0, 22.4, 22.8 seconds**.
The frames show soap, lathering, rinsing, paper-towel drying, and disposal.
Pre-soap wetting is not shown, so that step remains **unknown**.
Confidence values are subjective model estimates, not calibrated probabilities.

## Review through MCP

Install the optional demo dependencies and make `ffmpeg` and `ffprobe` available on `PATH`:

```bash
python -m pip install -r scripts/requirements-demo.txt
python scripts/video_mcp.py
```

The script is a **stdio MCP server**. Configure an image-capable MCP host to launch
your Python executable with the absolute path to `scripts/video_mcp.py` as its argument.
The server is built with the [official MCP Python SDK v2](https://py.sdk.modelcontextprotocol.io/servers/tools/).

The host performs recognition using these tools:

| Tool | Purpose |
| --- | --- |
| `inspect_video()` | Return duration, dimensions, procedure steps, and review instructions. |
| `read_frame(timestamp_seconds)` | Return the actual decoded frame as MCP image content. |
| `record_review(reviewer, observations)` | Validate and save one observation per step with evidence timestamps. |

Ask the host to inspect frames across the clip, compare them with the procedure, and
record `index`, `status`, `confidence`, `reason`, and `evidence_seconds` for every step.
An action absent from the evidence is `unknown`; use `not_done` only when visible
evidence supports that verdict. For sequential actions, inspect more than one frame.

The MCP server provides images and stores observations. It does not call a model,
infer verdicts, or replace the web app's `VisionProvider`. The connected host must
support image tool responses and perform the visual reasoning.

Defaults point to the included video and `review.json`. To review a different local video,
set `STEPCHECK_DEMO_VIDEO` and `STEPCHECK_DEMO_REVIEW` in the host's process environment.
The procedure is the included handwashing checklist; adapt `PROCEDURE` in the script
for another task. `record_review` writes the configured review file, replacing a prior review.

## Render the GIF

```bash
python scripts/generate_readme_gif.py
```

The renderer checks the video hash against the review and replays the footage at five
frames per second. Results appear at the last supporting evidence timestamp; steps
awaiting evidence remain pending. The final checklist is held for three seconds.
The generator renders the bundled example. For another video, adapt its asset paths
alongside the MCP configuration.

The web app and HTTP API continue to accept images. Video upload and automatic
video-provider inference remain on the roadmap.

## Checks

```bash
python -m unittest discover -s scripts/tests -v
```

The integration checks exercise the actual MCP image response, reject invalid evidence
timestamps and duplicate steps, and verify source hashing and saved observations.

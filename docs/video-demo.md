# Video flow verification demo

The README GIF plays a real video **in source chronology** through four stage panels.
An expected procedure flow sits above the video. Observations become visible at their
recorded confirmation times, and a sequence checker compares those times with the
expected order. Future stage images stay hidden until their source time is reached.

The GIF replays a recorded Codex review. It does not run inference during playback,
and it is not a recording of the web UI.

## Expected flow and observations

- Procedure: [handwashing.md](../examples/handwashing.md).
- Expected flow: [handwashing-flow.json](../examples/handwashing-flow.json), defined
  separately from the observed results.
- Video: [source.webm](assets/video-demo/source.webm), [attribution](assets/video-demo/SOURCE.md).
- Recorded visual observations: [review.json](assets/video-demo/review.json).
- Computed sequence checks: [order-review.json](assets/video-demo/order-review.json).
- Reviewed-frame box annotations: [regions.json](assets/video-demo/regions.json).

Expected: **Wet hands → Soap → Rub / lather → Rinse → Dry → Discard**.

| Recorded action | Confirmation time |
| --- | --- |
| Soap visible in a palm | 0.3 s |
| Lather rubbing over palms and backs | 3.5 s |
| Rinsing under running water | 12.5 s |
| Drying with a paper towel | 18.5 s |
| Used towel lowered into the bin | 22.8 s |

The recorded confirmations are consistent with the expected order for **steps 2–6**.
Step 1, wetting before soap, is not visible. The **full flow remains unknown**;
the checker does not treat missing evidence as a successful transition.

Confirmation time is the last supporting frame time listed for a step. It is not an
estimated action start or end time. The comparison establishes order among these
sampled observations; it does not prove that no extra, repeated, or out-of-order
actions happened between sampled frames.

## How the order check works

[`check_video_flow.py`](../scripts/check_video_flow.py) compares the independent expected
sequence with the recorded times. It detects inversions, preserves unknown steps,
and treats equal confirmation times as ambiguous. A full `verified` result requires
every expected step to be observed with strictly increasing confirmation times.
During replay, evidence from later source times stays pending.

```bash
python scripts/check_video_flow.py
```

The demo's output is `observed_order_status: consistent` and `overall_status: unknown`.
These values are computed from the saved evidence, not assigned by the GIF renderer.

## Evidence boxes, not heatmaps

Boxes are regions that Codex visually annotated on specific inspected source frames.
They appear **only on those exact decoded frames**. Unreviewed intermediate frames
have no box; the renderer does not interpolate regions or simulate object tracking.

There is no attention map in this demo. No internal model attention tensors or
pixel saliency scores were captured. The renderer draws only rectangle corner marks
and a label identifying the annotation and source timestamp. It does not color the
image interior to suggest a model response.

## Review through MCP

Install the optional demo dependencies and make `ffmpeg` and `ffprobe` available on `PATH`:

```bash
python -m pip install -r scripts/requirements-demo.txt
python scripts/video_mcp.py
```

The script is a stdio MCP server. Configure an image-capable host to launch your Python
executable with the absolute path to `scripts/video_mcp.py`. It uses the
[official MCP Python SDK v2](https://py.sdk.modelcontextprotocol.io/servers/tools/).

| Tool | Purpose |
| --- | --- |
| `inspect_video()` | Return duration, dimensions, procedure, and review instructions. |
| `read_frame(timestamp_seconds)` | Return an actual decoded frame as MCP image content. |
| `record_review(reviewer, observations)` | Save the host's observations and supporting timestamps. |
| `check_flow()` | Compare the saved timestamps with the expected flow and save the order report. |

This session used a Python MCP client to retrieve image responses, the session's image
viewer for Codex visual inspection, and `record_review` to save the resulting observations.
It did not install the server into the user's host settings. The host supplies the vision
reasoning; the MCP server does not call a model or generate verdicts.

The original action review inspected 0.3, 1.5, 3.5, 5.5, 9.5, 12.5, 14.5, 18.5,
21.5, 22.0, 22.4, and 22.8 seconds. Additional frames used for box annotations are
listed in `regions.json`. Confidence estimates in `review.json` are subjective.

Defaults point to the included video and review. Set `STEPCHECK_DEMO_VIDEO` and
`STEPCHECK_DEMO_REVIEW` for other local files. Adapt the procedure and expected flow
for another task. `record_review` replaces the configured review file; `check_flow`
writes `order-review.json` beside it.

## Render and verify

```bash
python scripts/generate_readme_gif.py
python -m unittest discover -s scripts/tests -v
```

The renderer validates source hashes and annotation coordinates, plays source frames
at approximately five frames per second, and includes exact reviewed frames. Completed
stage panels retain their supporting reviewed frame while the next panel advances. The final
result holds for three seconds. The four panels cover source time 0.0–22.8 seconds;
the flow updates at the recorded confirmation times.

Tests include reversed rinse/dry timestamps, missing intermediate evidence, tied times,
future evidence hiding, MCP result persistence, source mismatch, and unreviewed frames
remaining free of invented boxes.

The web app and HTTP API still accept images. Native video upload and automatic
video-provider inference remain on the roadmap.

# Detect a flow from one video

The README GIF shows **open-ended flow discovery**, using one real video without
passing a predefined procedure to the detection tool. `detect_flow()` decodes
timestamped frames and requests visual recognition from the connected MCP host.
The returned action list is ordered by its supporting sample times; overlapping
evidence makes a transition ambiguous rather than establishing a strict order.

The GIF replays the saved recognition. Its four panels are equal time quarters,
independent of action labels. Future panels and action labels stay hidden until
their supporting source times are reached. Inference does not run during playback.

## Discovered actions

Results: [detected-flow.json](assets/video-demo/detected-flow.json).

| Recognized action | Supporting sample times |
| --- | --- |
| Dispense soap | 0–0.75 s |
| Rub hands with lather | 1.5–10.5 s |
| Rinse under running water | 12–12.75 s |
| Pull a paper towel | 14.25–15 s |
| Dry hands with the towel | 15.75–19.5 s |
| Hold the door handle through the towel | 21.75 s |
| Lower the towel into the bin | 22.5–22.903 s |

Ranges summarize discrete supporting samples, **not action start/end estimates**.
Door opening is not established, and the towel's exact release is obscured.
Pre-soap wetting was not visible and was not added to the discovered flow.
The source has scene cuts and a crossfade, so the result cannot prove uninterrupted
execution or completeness. The JSON preserves these limitations.

This run used actual MCP sampling requests: the file adapter exported the requested
images, Codex inspected them in this session, and the adapter returned Codex's JSON
over MCP. No canned model response was used. This session had also performed the
earlier procedure comparison below; this is **not a blinded accuracy evaluation**.
No expected procedure or earlier observations are included in the sampling request.

## Run detection

Install `scripts/requirements-demo.txt` and make `ffmpeg` and `ffprobe` available.
Launch `scripts/video_mcp.py` as a stdio MCP server in a vision-capable host with
[MCP sampling support](https://py.sdk.modelcontextprotocol.io/handlers/dependencies/).
Call `detect_flow(sample_interval_seconds=0.75)`; no procedure argument is needed.
The server requests images-based inference from the host and validates its JSON,
including whether each evidence timestamp refers to a supplied sample.

For another local video, set `STEPCHECK_DEMO_VIDEO` to its absolute file path.
Set `STEPCHECK_DETECTED_FLOW` to the output JSON path; the default is
`docs/assets/video-demo/detected-flow.json`. Detection replaces that output only
after validation. At most 96 frames are sampled per request; increase the interval
for long videos. It processes samples from the video, not continuous motion.

If your host does not support sampling, use `inspect_video_for_flow()`,
`read_frame(timestamp_seconds)` and `record_detected_flow(...)`: the host must
actually inspect the images before recording observations. Recording alone performs
no inference and trusts the host's attestation of reviewed timestamps.

The included adapter supports a vision session that can inspect image files:

```bash
python scripts/run_flow_detection.py --bridge-dir .tmp-flow-new
```

It exports the **actual sampling request images** and waits for that session to
write `response.json` in the fresh bridge directory. The response must contain
`title`, `actions` (each with `label`, `reason`, `evidence_seconds`, `uncertainty`),
and `limitations`. This adapter does not call a model by itself. An ordinary
sampling-capable host can call the tool directly without the adapter.

To reproduce the README GIF from the included source and recorded detection:

```bash
python scripts/generate_detected_flow_gif.py
python -m unittest discover -s scripts/tests -v
```

The renderer reads the recognized actions from JSON; it does not define a correct
action list, invent attention, or run a model. The web app still accepts images;
this single-video workflow is currently exposed through MCP.

## Separate demo: verify an expected flow

The older [comparison GIF](assets/demo.gif) and tools below retain the independent
expected-flow check. Discovery lists observed actions; verification asks whether
those observations satisfy a separately written procedure.

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
| `inspect_video_for_flow()` | Return metadata and instructions without reading a procedure. |
| `detect_flow(sample_interval_seconds)` | Request host vision inference through MCP sampling and save the detected flow. |
| `record_detected_flow(reviewer, detection, reviewed_seconds)` | Record a host's open-ended visual review when sampling is unavailable. |
| `inspect_video()` | Return duration, dimensions, procedure, and review instructions. |
| `read_frame(timestamp_seconds)` | Return an actual decoded frame as MCP image content. |
| `record_review(reviewer, observations)` | Save the host's observations and supporting timestamps. |
| `check_flow()` | Compare the saved timestamps with the expected flow and save the order report. |

This session used a Python MCP client to retrieve image responses, the session's image
viewer for Codex visual inspection, and `record_review` to save the resulting observations.
It did not install the server into the user's host settings. The host supplies the vision
reasoning; the server has no model credentials. `detect_flow` requests host inference
through sampling; `record_review` and `record_detected_flow` only save supplied reviews.

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

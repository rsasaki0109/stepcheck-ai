# Sampling comparison attribution

This known-video experiment reuses the prior **actual Qwen initial answer** from
`../qwen3-web-auto-small/api-response.json` unchanged. It performs **one new real
GPU follow-up**, not two new inferences or a fresh Web API upload. The model receives
only the unknown criteria and selected source images. No expected action times,
synthetic predictions, attention maps or confidence values are supplied.

Source: **Hand Washing**, by **Anthony Albright**, **CC BY-SA 2.0**.

- https://commons.wikimedia.org/wiki/File:Hand_Washing_video.webm
- https://www.flickr.com/photos/anthonyalbright/4997782896/
- https://creativecommons.org/licenses/by-sa/2.0/
- Source file: `../new-video-transfer/source.webm`, unchanged.
- Changes: timestamp-based JPEG extraction and resizing to fit 640 × 640.
  These derived frames retain CC BY-SA 2.0. The creator does not endorse this work.

The code is MIT. Model weights are not distributed. `manifest.json` preserves
the new GPU inference, raw input/output hashes and code bytes. `sampling-chart-manifest.json`
binds the separate timing diagram to both real records. Timing gaps are sampling
geometry, not recognition accuracy or spatial attention. See
`docs/adaptive-reference-sampling.md` for results and limits.

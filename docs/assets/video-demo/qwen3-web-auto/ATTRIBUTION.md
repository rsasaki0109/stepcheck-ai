# Real local-Qwen Web API capture

This directory records a real local Qwen3-VL-4B-Instruct GPU experiment through
`POST /api/video-flow/verify`. It uses the previously reviewed source video and
given reference; it is **not an accuracy benchmark**. Validating model JSON and
citations does not establish that the depicted action satisfies its criterion.
No synthetic answer, confidence score or spatial attention map is supplied.

`manifest.json` records the executed model revision, packages, settings, source
hash, code hashes, API outcome and the actual calls. Each pass preserves the
submitted JPEG bytes, image labels, prompt and raw model text. `api-response.json`
is the application's response, including errors. A failed response is not a
successful flow verification. `code/` preserves the code bytes used by this run;
`run.py` is the recorder and refuses to replace an existing capture.

Source: **Hand Washing**, by **Anthony Albright**.

- Wikimedia page: https://commons.wikimedia.org/wiki/File:Hand_Washing_video.webm
- Original: https://www.flickr.com/photos/anthonyalbright/4997782896/
- License: **CC BY-SA 2.0**, https://creativecommons.org/licenses/by-sa/2.0/
- Source in this repository: `../new-video-transfer/source.webm` (unchanged).
- Changes: JPEG frames extracted at recorded source times and resized to fit
  640 × 640, preserving aspect ratio. Derived frames retain CC BY-SA 2.0.
  The creator does not endorse this experiment.

Application and recorder code retain the repository's MIT license. Model weights
are not distributed here. See `docs/web-reference-verification.md` for the
outcome, evidence review and limits of this experiment.

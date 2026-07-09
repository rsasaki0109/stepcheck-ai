# Examples

Sample procedures you can paste into the StepCheck UI (left panel) and pair with your
own photos.

| File | Domain |
| --- | --- |
| [`pc-build.md`](./pc-build.md) | Assembling a desktop PC |
| [`coffee-brewing.md`](./coffee-brewing.md) | Pour-over coffee |

You can also verify via the API directly:

```bash
curl -X POST http://localhost:8000/api/verify \
  -F "procedure=$(cat examples/pc-build.md)" \
  -F "images=@/path/to/photo1.jpg" \
  -F "images=@/path/to/photo2.jpg"
```

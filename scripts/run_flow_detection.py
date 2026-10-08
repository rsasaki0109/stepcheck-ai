"""MCP sampling adapter for a vision session that can inspect and write files.

Exports the server's actual sampling images, waits for the connected session's JSON
answer file, and returns it over MCP. Does not contain canned detections or call a model.
Normal sampling-capable MCP hosts can call detect_flow directly without this adapter.
"""

import argparse
import asyncio
import base64
import json
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters
from mcp.types import CreateMessageResult, TextContent


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-dir", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=0.75)
    parser.add_argument("--reviewer", default="vision session through file MCP adapter")
    args = parser.parse_args()
    args.bridge_dir.mkdir(parents=True, exist_ok=True)
    response_path = args.bridge_dir / "response.json"
    if response_path.exists():
        raise ValueError("Use a fresh bridge directory; response.json already exists.")

    async def sampling_callback(context, params):
        image_index = 0
        for message in params.messages:
            blocks = message.content if isinstance(message.content, list) else [message.content]
            for block in blocks:
                if block.type == "text":
                    print(block.text, flush=True)
                elif block.type == "image":
                    path = args.bridge_dir / f"sampling-{image_index}.png"
                    path.write_bytes(base64.b64decode(block.data))
                    print(f"SAMPLING_IMAGE {path.resolve()}", flush=True)
                    image_index += 1
        print(f"AWAITING_VISION_JSON: inspect these images and write {response_path.resolve()}", flush=True)
        for _ in range(1200):
            if response_path.exists():
                break
            await asyncio.sleep(0.5)
        else:
            raise TimeoutError("No vision response file received within ten minutes.")
        answer = response_path.read_text(encoding="utf-8")
        json.loads(answer)
        return CreateMessageResult(role="assistant", model=args.reviewer,
                                   content=TextContent(type="text", text=answer))

    server = StdioServerParameters(command=sys.executable,
                                   args=[str(Path(__file__).with_name("video_mcp.py"))])
    async with Client(server, sampling_callback=sampling_callback, read_timeout_seconds=660) as client:
        result = await client.call_tool("detect_flow", {"sample_interval_seconds": args.interval})
        for content in result.content:
            if content.type == "text":
                print(content.text, flush=True)
        if result.is_error:
            raise RuntimeError("Flow detection failed; see MCP result above.")


if __name__ == "__main__":
    asyncio.run(main())

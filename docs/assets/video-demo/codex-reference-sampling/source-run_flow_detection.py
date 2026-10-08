"""MCP sampling adapter for a vision session that can inspect and write files.

Exports the server's actual sampling images, waits for the connected session's JSON
answer file, and returns it over MCP. Does not contain canned detections or call a model.
Normal sampling-capable MCP hosts can call detect_flow directly without this adapter.
"""

import argparse
import asyncio
import base64
import json
import hashlib
import os
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters
from mcp.types import CreateMessageResult, TextContent


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-dir", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=0.75)
    parser.add_argument("--reviewer", default="vision session through file MCP adapter")
    parser.add_argument("--reference", type=Path, help="Given reference JSON; calls verify_reference_flow instead of discovery")
    parser.add_argument("--output", type=Path, help="Server output JSON (required with --reference)")
    args = parser.parse_args()
    args.bridge_dir.mkdir(parents=True, exist_ok=True)
    response_path = args.bridge_dir / "response.json"
    if any(args.bridge_dir.iterdir()):
        raise ValueError("Use a fresh, empty bridge directory.")
    if args.reference and not args.output:
        raise ValueError("Specify --output with --reference to preserve earlier evidence.")
    arguments = {"sample_interval_seconds": args.interval}
    if args.reference:
        arguments["reference"] = json.loads(args.reference.read_text(encoding="utf-8"))
    tool_name = "verify_reference_flow" if args.reference else "detect_flow"
    (args.bridge_dir / "tool-request.json").write_text(json.dumps({"tool": tool_name,
        "arguments": arguments, "reviewer": args.reviewer}, indent=2), encoding="utf-8")

    async def sampling_callback(context, params):
        image_index = 0
        exported = []
        prompts = []
        for message in params.messages:
            blocks = message.content if isinstance(message.content, list) else [message.content]
            for block in blocks:
                if block.type == "text":
                    print(block.text, flush=True)
                    prompts.append(block.text)
                elif block.type == "image":
                    path = args.bridge_dir / f"sampling-{image_index}.png"
                    path.write_bytes(base64.b64decode(block.data))
                    exported.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
                    print(f"SAMPLING_IMAGE {path.resolve()}", flush=True)
                    image_index += 1
        (args.bridge_dir / "sampling-request.json").write_text(json.dumps({
            "text": prompts, "images": exported, "include_context": params.include_context,
            "temperature": params.temperature, "max_tokens": params.max_tokens,
            "adapter_note": "Exports actual MCP sampling content to the connected vision session; invokes no model API itself."
        }, indent=2, ensure_ascii=False), encoding="utf-8")
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

    server_env = dict(os.environ)
    if args.output:
        server_env["STEPCHECK_REFERENCE_REVIEW" if args.reference else "STEPCHECK_DETECTED_FLOW"] = str(args.output.resolve())
    server = StdioServerParameters(command=sys.executable, env=server_env,
                                   args=[str(Path(__file__).with_name("video_mcp.py"))])
    async with Client(server, sampling_callback=sampling_callback, read_timeout_seconds=660) as client:
        result = await client.call_tool(tool_name, arguments)
        (args.bridge_dir / "tool-result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        for content in result.content:
            if content.type == "text":
                print(content.text, flush=True)
        if result.is_error:
            raise RuntimeError("Flow detection failed; see MCP result above.")


if __name__ == "__main__":
    asyncio.run(main())

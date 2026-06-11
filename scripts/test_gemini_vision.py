"""
Standalone Gemini vision smoke test.

Sends one (or two) local image files to the configured Gemini model and prints
the structured damage assessment. Use it to confirm your GEMINI_API_KEY and
model name work before wiring up the full claim pipeline.

Usage:
    uv run python scripts/test_gemini_vision.py <item_image.jpg> [label_image.jpg] \
        [--claim-type damaged] [--product "Sony WH-1000XM5 headphones"]

With no GEMINI_API_KEY set, this prints the deterministic mock result so you can
see the output shape offline.
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.langgraph_agent.tools import gemini_client  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini vision smoke test")
    parser.add_argument("item_image", help="Path to the damaged-item photo")
    parser.add_argument("label_image", nargs="?", help="Optional path to the shipping-label photo")
    parser.add_argument("--claim-type", default="damaged")
    parser.add_argument("--product", default="Unknown product")
    args = parser.parse_args()

    with open(args.item_image, "rb") as fh:
        item_bytes = fh.read()
    label_bytes = None
    if args.label_image:
        with open(args.label_image, "rb") as fh:
            label_bytes = fh.read()

    result = await gemini_client.analyze_damage(
        item_image=item_bytes,
        label_image=label_bytes,
        claim_type=args.claim_type,
        product_description=args.product,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

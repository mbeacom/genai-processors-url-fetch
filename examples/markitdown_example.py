#!/usr/bin/env python3
"""Simple example demonstrating markitdown content processor.

This script shows how to configure the UrlFetchProcessor with markitdown
to convert HTML content to rich markdown format.
"""

import asyncio

from genai_processors import processor

from genai_processors_url_fetch import FetchConfig, UrlFetchProcessor


async def main() -> None:
    """Demonstrate markitdown content processor."""
    print("🚀 Markitdown Content Processor Demo")
    print("=" * 40)

    # Use a reliable test URL
    test_url = "https://example.com"

    # Configure with markitdown processor
    config = FetchConfig(
        content_processor="markitdown",
        include_original_part=False,
        timeout=10.0,
        markitdown_options={
            "extract_tables": True,
        },
    )

    print(f"Fetching: {test_url}")
    print("Using markitdown processor...")

    # Create processor and process URL
    url_processor = UrlFetchProcessor(config)

    # Create a ProcessorPart with the URL
    input_part = processor.ProcessorPart(test_url)

    async for part in url_processor.call(input_part):
        if (
            hasattr(part, "substream_name")
            and part.substream_name == processor.STATUS_STREAM
        ):
            print(f"Status: {part.text}")
        elif part.text and part.metadata.get("fetch_status") == "success":
            print("\n📄 Markitdown Output:")
            print("-" * 30)
            print(part.text[:500] + ("..." if len(part.text) > 500 else ""))
            print(f"\nTotal length: {len(part.text):,} characters")
            print("✅ Demo completed successfully!")
            break
        elif part.metadata.get("fetch_status") == "failure":
            error_msg = part.metadata.get("fetch_error", "Unknown error")
            print(f"❌ Error: {error_msg}")
            break


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ImportError as e:
        if "markitdown" in str(e):
            print("❌ Markitdown not installed. Install with:")
            print("   pip install genai-processors-url-fetch[markitdown]")
        else:
            print(f"❌ Import error: {e}")
    except (RuntimeError, ValueError, ConnectionError) as e:
        print(f"❌ Error: {e}")

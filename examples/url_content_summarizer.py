"""URL Content Summarizer CLI.

This example demonstrates the UrlFetchProcessor by building a simple tool
that extracts URLs from user input, fetches their content, and provides
summaries using a GenAI model.

Setup:
    Set the GEMINI_API_KEY environment variable:
    export GEMINI_API_KEY=your_api_key_here

Usage:
    python url_content_summarizer.py

Then enter text containing URLs. The tool will:
1. Extract URLs from your input
2. Fetch the content from those URLs
3. Summarize the content using Gemini
4. Display the results

Example input:
    "Please summarize these articles: https://example.com/news and
    https://docs.python.org/3/"

"""

import asyncio
import os
import time
from collections.abc import AsyncIterable

from genai_processors import content_api, processor, streams
from genai_processors.core import genai_model
from google.genai import types as genai_types

from genai_processors_url_fetch.url_fetch import (
    ContentProcessor,
    FetchConfig,
    UrlFetchProcessor,
)

# Get API key from environment
API_KEY = os.environ.get("GEMINI_API_KEY", "")


@processor.processor_function
async def summarize_content(
    content: AsyncIterable[content_api.ProcessorPart],
) -> AsyncIterable[content_api.ProcessorPart]:
    """Summarize fetched URL content."""
    async for part in content:
        # Only process successfully fetched content
        if part.metadata.get("fetch_status") == "success":
            source_url = part.metadata.get("source_url", "Unknown URL")
            content_text = part.text

            # Create a summary request
            summary_prompt = (
                f"Please provide a concise summary of this webpage content "
                f"from {source_url}:\n\n{content_text}"
            )

            yield content_api.ProcessorPart(
                summary_prompt,
                metadata={**part.metadata, "summary_requested": True},
            )
        else:
            # Pass through non-successful parts unchanged
            yield part


async def run_url_summarizer() -> None:
    """Run the URL summarizer CLI."""
    if not API_KEY:
        print("Error: GEMINI_API_KEY environment variable not set.")
        print("Get an API key from Google AI Studio and set it with:")
        print("  export GEMINI_API_KEY=your_api_key_here")
        return

    # Configure URL fetcher with security settings
    fetch_config = FetchConfig(
        timeout=10.0,
        max_response_size=2 * 1024 * 1024,  # 2MB limit
        include_original_part=False,  # Only show fetched content
        content_processor=ContentProcessor.BEAUTIFULSOUP,  # Extract clean text
        # Security: Only allow HTTPS and block private IPs
        allowed_schemes=["https"],
        block_private_ips=True,
    )

    # Create the processing pipeline
    url_fetcher = UrlFetchProcessor(fetch_config)

    # Only create GenAI model if we have an API key
    summarizer = genai_model.GenaiModel(
        api_key=API_KEY,
        model_name="models/gemini-2.5-flash-lite-preview-06-17",
        generate_content_config=genai_types.GenerateContentConfig(
            system_instruction=(
                "You are a helpful assistant that summarizes webpage content. "
                "Provide concise, informative summaries that capture the key "
                "points of the content. Keep summaries to 2-3 sentences."
            ),
        ),
    )

    # Build the complete pipeline
    pipeline = url_fetcher + summarize_content + summarizer

    print("🌐 URL Content Summarizer")
    print("=" * 40)
    print("Enter text containing URLs to summarize their content.")
    print("Only HTTPS URLs are allowed for security.")
    print("Use Ctrl+D to quit.\n")

    while True:
        try:
            user_input = await asyncio.to_thread(input, "Enter text with URLs > ")
        except EOFError:
            print("\nGoodbye!")
            return

        if not user_input.strip():
            continue

        print(f"\n{time.perf_counter():.2f} - Processing URLs...")

        # Process the input through our pipeline
        input_stream = streams.stream_content([user_input])

        fetched_count = 0
        summarized_count = 0
        in_summary = False

        async for part in pipeline(input_stream):
            timestamp = f"{time.perf_counter():.2f}"

            # Handle status messages
            if part.substream_name == processor.STATUS_STREAM:
                print(f"{timestamp} - {part.text}")

                # Count successful fetches from status messages
                if part.text.startswith("✅ Fetched successfully:"):
                    fetched_count += 1

            # Handle summary responses from GenAI model
            elif (
                not part.substream_name
                and part.text.strip()
                and part.metadata.get("model_version")
            ):  # GenAI response

                if not in_summary:
                    # Starting a new summary
                    in_summary = True
                    summarized_count += 1
                    print(f"\n📄 Summary #{summarized_count}:")
                    print(part.text, end="", flush=True)
                else:
                    # Continuing the current summary
                    print(part.text, end="", flush=True)

        # Finish the last summary if we were in one
        if in_summary:
            print("\n")

        if fetched_count == 0:
            print("No URLs were successfully fetched.")
        elif summarized_count == 0:
            print("Content was fetched but no summaries were generated.")


if __name__ == "__main__":
    asyncio.run(run_url_summarizer())

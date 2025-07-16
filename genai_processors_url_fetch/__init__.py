"""genai-processors-url-fetch: A URL fetch processor for genai-processors.

This package provides a UrlFetchProcessor that detects URLs in incoming text
parts, fetches their content concurrently, and yields new ProcessorParts
containing the page content. It is a powerful and secure tool for enabling AI
agents to access and process information from the web.

This is an independent contrib processor for the genai-processors ecosystem.
"""

from .url_fetch import FetchConfig, UrlFetchProcessor

__version__ = "0.1.0"
__all__ = ["UrlFetchProcessor", "FetchConfig"]

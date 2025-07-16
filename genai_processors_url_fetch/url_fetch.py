"""Processor that fetches URLs found in text and returns the page content."""

import asyncio
import ipaddress
import re
from collections.abc import AsyncIterable
from dataclasses import dataclass, field
from typing import Final, NamedTuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from genai_processors import processor

__all__ = ["UrlFetchProcessor", "FetchConfig"]

URL_REGEX: Final[re.Pattern[str]] = re.compile(
    r"""https?://[^\s<>"'\u200B]+""",
    re.IGNORECASE,
)


@dataclass
class FetchConfig:
    """Configuration for UrlFetchProcessor behavior."""

    # Basic behavior
    timeout: float = 15.0  # Per-request HTTP timeout in seconds
    max_concurrent_fetches_per_host: int = 3  # Max parallel fetches per host
    user_agent: str = "GenAI-Processors/UrlFetchProcessor"  # User-Agent header
    include_original_part: bool = True  # Yield original part after processing
    fail_on_error: bool = False  # Raise exception on first fetch failure
    extract_text_only: bool = True  # Convert HTML to text vs return raw HTML

    # Security controls
    block_private_ips: bool = True  # Block private IP ranges (RFC 1918)
    block_localhost: bool = True  # Block localhost/loopback addresses
    block_metadata_endpoints: bool = True  # Block cloud metadata endpoints
    allowed_domains: list[str] | None = None  # Only allow these domains
    blocked_domains: list[str] | None = None  # Block these domains
    allowed_schemes: list[str] = field(
        default_factory=lambda: ["http", "https"],
    )
    max_response_size: int = 10 * 1024 * 1024  # Max response size (10MB)


class FetchResult(NamedTuple):
    """Represents the outcome of a fetch operation."""

    url: str
    ok: bool
    content: str | None
    error_message: str | None


class UrlFetchProcessor(processor.PartProcessor):
    """Detects URLs in text parts, fetches them, and emits content parts.

    This processor inspects incoming text parts for URLs, fetches them
    concurrently, and yields the fetched content as new parts. It provides
    rich feedback through the status stream and can be configured for
    different behaviors.

    Example:
        ```python
        from genai_processors_url_fetch import UrlFetchProcessor, FetchConfig

        # Basic URL fetcher
        fetcher = UrlFetchProcessor()

        # Customized fetcher
        config = FetchConfig(
            timeout=30.0,
            fail_on_error=True,
            extract_text_only=False  # Keep HTML
        )
        strict_fetcher = UrlFetchProcessor(config)
        ```

    """

    def __init__(self, config: FetchConfig | None = None) -> None:
        """Initialize the processor with fetch configuration.

        Args:
            config: Fetch configuration. Uses defaults if None.

        """
        self.config = config or FetchConfig()
        self._host_locks: dict[str, asyncio.Semaphore] = {}

    def match(self, part: processor.ProcessorPart) -> bool:
        """Determine if this part should be processed.

        Args:
            part: The ProcessorPart to check.

        Returns:
            True if the part contains text with URLs.

        """
        return bool(part.text and URL_REGEX.search(part.text))

    async def _get_host_semaphore(self, host: str) -> asyncio.Semaphore:
        """Return a semaphore to limit parallel fetches per host."""
        if host not in self._host_locks:
            self._host_locks[host] = asyncio.Semaphore(
                self.config.max_concurrent_fetches_per_host,
            )
        return self._host_locks[host]

    def _is_private_ip(self, ip_str: str) -> bool:
        """Check if an IP address is private or reserved."""
        try:
            ip = ipaddress.ip_address(ip_str)
            return (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
            )
        except ValueError:
            return False

    def _is_metadata_endpoint(self, host: str) -> bool:
        """Check if host is a cloud metadata endpoint."""
        metadata_hosts = {
            "169.254.169.254",  # AWS, GCP, Azure metadata
            "metadata.google.internal",  # GCP
            "metadata",  # Docker
        }
        return host.lower() in metadata_hosts

    async def _validate_url(self, url: str) -> tuple[bool, str | None]:
        """Validate URL against security policies.

        Returns:
            Tuple of (is_valid, error_message)

        """
        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in self.config.allowed_schemes:
                return False, f"Scheme '{parsed.scheme}' not allowed"

            # Check domain allow/block lists
            host = parsed.hostname or ""

            if self.config.allowed_domains and not any(
                host == domain or host.endswith(f".{domain}")
                for domain in self.config.allowed_domains
            ):
                return False, f"Domain '{host}' not in allowed list"

            if self.config.blocked_domains and any(
                host == domain or host.endswith(f".{domain}")
                for domain in self.config.blocked_domains
            ):
                return False, f"Domain '{host}' is blocked"

            # Check metadata endpoints
            if self.config.block_metadata_endpoints and self._is_metadata_endpoint(
                host,
            ):
                return False, f"Metadata endpoint '{host}' is blocked"

            # Check IP restrictions (resolve DNS if needed)
            if self.config.block_private_ips or self.config.block_localhost:
                try:
                    # Check if it's already an IP address or hostname
                    if (
                        self._is_private_ip(host)  # Already an IP
                        and self.config.block_private_ips
                    ):
                        return False, f"Private IP '{host}' is blocked"

                    # Check localhost specifically
                    localhost_addrs = ["localhost", "127.0.0.1", "::1"]
                    if self.config.block_localhost and host in localhost_addrs:
                        return False, f"Localhost '{host}' is blocked"

                except (OSError, ValueError):
                    # If we can't resolve, be conservative and block
                    return False, f"Unable to resolve hostname '{host}'"

            return True, None

        except (ValueError, TypeError) as e:
            return False, f"URL validation error: {str(e)}"

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convert raw HTML to plain text with basic whitespace collapse."""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(
            [
                "script",
                "style",
                "noscript",
                "nav",
                "footer",
                "header",
            ],
        ):
            tag.decompose()
        return " ".join(soup.get_text(separator=" ").split())

    async def _fetch_one(
        self,
        url: str,
        client: httpx.AsyncClient,
    ) -> FetchResult:
        """Download a single URL and return a structured FetchResult."""
        # First validate the URL against security policies
        is_valid, error_msg = await self._validate_url(url)
        if not is_valid:
            return FetchResult(
                url=url,
                ok=False,
                content=None,
                error_message=f"Security validation failed: {error_msg}",
            )

        try:
            host = httpx.URL(url).host or ""
            sem = await self._get_host_semaphore(host)
            async with sem:
                resp = await client.get(
                    url,
                    timeout=self.config.timeout,
                    follow_redirects=True,
                )
                resp.raise_for_status()

                # Check response size if configured
                content_length = resp.headers.get("content-length")
                if (
                    content_length
                    and int(content_length) > self.config.max_response_size
                ):
                    return FetchResult(
                        url=url,
                        ok=False,
                        content=None,
                        error_message=(f"Response too large: {content_length} bytes"),
                    )

                # Read content with size limit
                content_bytes = b""
                async for chunk in resp.aiter_bytes():
                    content_bytes += chunk
                    if len(content_bytes) > self.config.max_response_size:
                        max_size = self.config.max_response_size
                        return FetchResult(
                            url=url,
                            ok=False,
                            content=None,
                            error_message=f"Response exceeded {max_size} bytes",
                        )

                # Process content based on configuration
                content_text = content_bytes.decode("utf-8", errors="replace")
                if self.config.extract_text_only:
                    content = await asyncio.to_thread(
                        self._html_to_text,
                        content_text,
                    )
                else:
                    content = content_text

                return FetchResult(
                    url=url,
                    ok=True,
                    content=content,
                    error_message=None,
                )
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP Error: {e.response.status_code} for URL: {e.request.url}"
            return FetchResult(
                url=url,
                ok=False,
                content=None,
                error_message=error_msg,
            )
        except httpx.RequestError as e:
            error_msg = f"Request Error: {type(e).__name__} for URL: {e.request.url}"
            return FetchResult(
                url=url,
                ok=False,
                content=None,
                error_message=error_msg,
            )
        except UnicodeDecodeError:
            error_msg = "Encoding Error: Unable to decode response as UTF-8"
            return FetchResult(
                url=url,
                ok=False,
                content=None,
                error_message=error_msg,
            )

    async def _create_success_part(
        self,
        result: FetchResult,
        original_part: processor.ProcessorPart,
    ) -> processor.ProcessorPart:
        """Create a ProcessorPart for a successful fetch."""
        mimetype = (
            "text/plain; charset=utf-8"
            if self.config.extract_text_only
            else "text/html; charset=utf-8"
        )

        if result.content is None:
            msg = f"Content is None for successful fetch of {result.url}"
            raise ValueError(msg)

        return processor.ProcessorPart(
            result.content,
            mimetype=mimetype,
            metadata={
                **original_part.metadata,
                "source_url": result.url,
                "fetch_status": "success",
            },
        )

    async def _create_failure_part(
        self,
        result: FetchResult,
        original_part: processor.ProcessorPart,
    ) -> processor.ProcessorPart:
        """Create a ProcessorPart for a failed fetch."""
        return processor.ProcessorPart(
            # Empty content for failures
            "",
            metadata={
                **original_part.metadata,
                "source_url": result.url,
                "fetch_status": "failure",
                "fetch_error": result.error_message,
            },
        )

    async def call(
        self,
        part: processor.ProcessorPart,
    ) -> AsyncIterable[processor.ProcessorPart]:
        """Fetch URLs found in the part and yield results."""
        urls = set(URL_REGEX.findall(part.text or ""))

        if not urls:
            # No URLs found, just pass through if configured to do so
            if self.config.include_original_part:
                yield part
            return

        headers = {"User-Agent": self.config.user_agent}
        async with httpx.AsyncClient(headers=headers) as client:
            # Collect all results by fetching URLs sequentially
            # This ensures compatibility across async backends
            results = []
            for url in urls:
                result = await self._fetch_one(url, client)
                results.append(result)

            # Process all results
            for result in results:

                if result.ok:
                    yield processor.status(
                        f"✅ Fetched successfully: {result.url}",
                    )
                    yield await self._create_success_part(result, part)
                else:
                    yield processor.status(f"❌ Fetch failed: {result.url}")
                    if self.config.fail_on_error:
                        raise RuntimeError(result.error_message)
                    yield await self._create_failure_part(result, part)

        # Finally, yield the original part if configured to do so
        if self.config.include_original_part:
            yield part

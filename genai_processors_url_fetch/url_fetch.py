"""Processor that fetches URLs found in text and returns the page content."""

import asyncio
import importlib.util
import ipaddress
import re
import warnings
from collections.abc import AsyncIterable
from dataclasses import dataclass, field
from typing import Any, Final, Literal, NamedTuple
from urllib.parse import ParseResult, urlparse

import httpx
from bs4 import BeautifulSoup
from genai_processors import processor

# Check markitdown availability
HAS_MARKITDOWN = importlib.util.find_spec("markitdown") is not None

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

    # Content processing options
    content_processor: Literal["beautifulsoup", "markitdown", "raw"] = "beautifulsoup"
    markitdown_options: dict[str, Any] = field(default_factory=dict)

    # Deprecated - for backward compatibility
    extract_text_only: bool | None = None  # Use content_processor instead

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

    def __post_init__(self) -> None:
        """Handle backward compatibility and validation."""
        # Handle deprecated extract_text_only parameter
        if self.extract_text_only is not None:
            warnings.warn(
                "extract_text_only is deprecated. Use content_processor instead. "
                "extract_text_only=True maps to content_processor='beautifulsoup', "
                "extract_text_only=False maps to content_processor='raw'.",
                DeprecationWarning,
                stacklevel=2,
            )
            if self.content_processor == "beautifulsoup":  # Default wasn't changed
                self.content_processor = (
                    "beautifulsoup" if self.extract_text_only else "raw"
                )

        # Validate markitdown availability
        if self.content_processor == "markitdown" and not HAS_MARKITDOWN:
            msg = (
                "markitdown is required for content_processor='markitdown'. "
                "Install with: pip install genai-processors-url-fetch[markitdown]"
            )
            raise ImportError(msg)


class FetchResult(NamedTuple):
    """Represents the outcome of a fetch operation."""

    url: str
    ok: bool
    content: str | None
    mimetype: str | None
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
        self._host_locks_lock = asyncio.Lock()

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
        async with self._host_locks_lock:
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

    def _validate_scheme_and_domain(
        self,
        parsed_url: ParseResult,
    ) -> tuple[bool, str | None]:
        """Validate URL scheme and domain restrictions."""
        # Check scheme
        if parsed_url.scheme not in self.config.allowed_schemes:
            return False, f"Scheme '{parsed_url.scheme}' not allowed"

        # Check domain allow/block lists
        host = parsed_url.hostname or ""

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
        if self.config.block_metadata_endpoints and self._is_metadata_endpoint(host):
            return False, f"Metadata endpoint '{host}' is blocked"

        return True, None

    async def _validate_ip_restrictions(
        self,
        host: str,
    ) -> tuple[bool, str | None]:
        """Validate IP restrictions including DNS resolution."""
        if not (self.config.block_private_ips or self.config.block_localhost):
            return True, None

        try:
            # First check if it's already an IP address
            if self._is_private_ip(host) and self.config.block_private_ips:
                return False, f"Private IP '{host}' is blocked"

            # Check localhost addresses specifically
            localhost_addrs = ["localhost", "127.0.0.1", "::1"]
            if self.config.block_localhost and host in localhost_addrs:
                return False, f"Localhost '{host}' is blocked"

            # If it's not an IP, resolve it to check IPs it points to
            if not self._is_private_ip(host) and host not in localhost_addrs:
                return await self._check_resolved_ips(host)

        except (OSError, ValueError) as e:  # e.g., socket.gaierror
            # If we can't resolve, be conservative and block
            return (
                False,
                f"Unable to resolve hostname '{host}': {e}",
            )

        return True, None

    async def _check_resolved_ips(self, host: str) -> tuple[bool, str | None]:
        """Check resolved IP addresses for security violations."""
        loop = asyncio.get_running_loop()
        # Resolve hostname to IP addresses. getaddrinfo robust
        addr_info = await loop.getaddrinfo(host, None)
        resolved_ips = {addr[4][0] for addr in addr_info}

        for ip_str in resolved_ips:
            ip = ipaddress.ip_address(ip_str)
            if self.config.block_private_ips and (
                ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved
            ):
                return (
                    False,
                    f"Resolved IP '{ip_str}' for host "
                    f"'{host}' is private and blocked.",
                )
            if self.config.block_localhost and ip.is_loopback:
                return (
                    False,
                    f"Resolved IP '{ip_str}' for host "
                    f"'{host}' is a loopback address and "
                    "blocked.",
                )

        return True, None

    async def _validate_url(self, url: str) -> tuple[bool, str | None]:
        """Validate URL against security policies.

        Returns:
            Tuple of (is_valid, error_message)

        """
        try:
            parsed = urlparse(url)

            # Validate scheme and domain restrictions
            is_valid, error = self._validate_scheme_and_domain(parsed)
            if not is_valid:
                return False, error

            # Validate IP restrictions
            host = parsed.hostname or ""
            return await self._validate_ip_restrictions(host)

        except (ValueError, TypeError) as e:
            return False, f"URL validation error: {str(e)}"

    @staticmethod
    def _beautifulsoup_to_text(html: str) -> str:
        """Convert raw HTML to plain text using BeautifulSoup."""
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

    def _markitdown_to_text(self, content: str, url: str) -> str:
        """Convert content to markdown using markitdown."""
        if not HAS_MARKITDOWN:
            msg = (
                "markitdown is required but not installed. "
                "Install with: pip install genai-processors-url-fetch[markitdown]"
            )
            raise ImportError(msg)

        # Import required modules
        from io import BytesIO

        from markitdown import MarkItDown, StreamInfo  # noqa: PLC0415

        # Create MarkItDown instance with user options
        markitdown_converter = MarkItDown(**self.config.markitdown_options)

        # Create StreamInfo with URL context for better conversion
        content_stream = BytesIO(content.encode("utf-8"))
        stream_info = StreamInfo(
            url=url,
            extension=".html",
            mimetype="text/html; charset=utf-8",
        )

        # Use markitdown to convert the content with URL context
        result = markitdown_converter.convert_stream(
            content_stream,
            stream_info=stream_info,
        )
        return result.text_content

    async def _process_content(
        self,
        content: str,
        url: str,
    ) -> tuple[str, str]:
        """Process content according to configuration.

        Returns:
            Tuple of (processed_content, mimetype)

        """
        if self.config.content_processor == "raw":
            return content, "text/html; charset=utf-8"
        if self.config.content_processor == "beautifulsoup":
            processed = await asyncio.to_thread(
                self._beautifulsoup_to_text,
                content,
            )
            return processed, "text/plain; charset=utf-8"
        if self.config.content_processor == "markitdown":
            processed = await asyncio.to_thread(
                self._markitdown_to_text,
                content,
                url,
            )
            return processed, "text/markdown; charset=utf-8"
        msg = f"Unknown content_processor: {self.config.content_processor}"
        raise ValueError(msg)

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
                mimetype=None,
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
                    error_msg = f"Response too large: {content_length} bytes"
                    return FetchResult(
                        url=url,
                        ok=False,
                        content=None,
                        mimetype=None,
                        error_message=error_msg,
                    )

                # Read content with size limit
                chunks = []
                total_size = 0
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    total_size += len(chunk)
                    if total_size > self.config.max_response_size:
                        max_size = self.config.max_response_size
                        error_msg = f"Response exceeded {max_size} bytes"
                        return FetchResult(
                            url=url,
                            ok=False,
                            content=None,
                            mimetype=None,
                            error_message=error_msg,
                        )

                content_bytes = b"".join(chunks)

                # Process content based on configuration
                content_text = content_bytes.decode("utf-8", errors="replace")
                content_result = await self._process_content(content_text, url)
                processed_content, content_mimetype = content_result

                return FetchResult(
                    url=url,
                    ok=True,
                    content=processed_content,
                    mimetype=content_mimetype,
                    error_message=None,
                )
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            request_url = e.request.url
            error_msg = f"HTTP Error: {status_code} for URL: {request_url}"
            return FetchResult(
                url=url,
                ok=False,
                content=None,
                mimetype=None,
                error_message=error_msg,
            )
        except httpx.RequestError as e:
            error_type = type(e).__name__
            request_url = e.request.url
            error_msg = f"Request Error: {error_type} for URL: {request_url}"
            return FetchResult(
                url=url,
                ok=False,
                content=None,
                mimetype=None,
                error_message=error_msg,
            )
        except UnicodeDecodeError:
            error_msg = "Encoding Error: Unable to decode response as UTF-8"
            return FetchResult(
                url=url,
                ok=False,
                content=None,
                mimetype=None,
                error_message=error_msg,
            )

    async def _create_success_part(
        self,
        result: FetchResult,
        original_part: processor.ProcessorPart,
    ) -> processor.ProcessorPart:
        """Create a ProcessorPart for a successful fetch."""
        if result.content is None:
            msg = f"Content is None for successful fetch of {result.url}"
            raise ValueError(msg)

        if result.mimetype is None:
            msg = f"Mimetype is None for successful fetch of {result.url}"
            raise ValueError(msg)

        return processor.ProcessorPart(
            result.content,
            mimetype=result.mimetype,
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
        urls = list(dict.fromkeys(URL_REGEX.findall(part.text or "")))

        if not urls:
            # No URLs found, just pass through if configured to do so
            if self.config.include_original_part:
                yield part
            return

        headers = {"User-Agent": self.config.user_agent}
        async with httpx.AsyncClient(headers=headers) as client:
            # Create tasks to fetch all URLs concurrently
            tasks = [self._fetch_one(url, client) for url in urls]
            results = await asyncio.gather(*tasks)

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

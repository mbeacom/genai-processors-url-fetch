"""Test suite for UrlFetchProcessor in genai_processors_url_fetch.url_fetch."""

from collections.abc import AsyncIterable
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from genai_processors import processor

from genai_processors_url_fetch.url_fetch import (
    URL_REGEX,
    FetchConfig,
    UrlFetchProcessor,
)


class TestUrlFetchProcessor:
    """Comprehensive test suite for UrlFetchProcessor.

    Tests both core functionality and security features including:
    - URL matching and extraction
    - HTTP fetching with proper error handling
    - Configuration options and behavior
    - Security controls (IP blocking, domain filtering, etc.)
    - Response processing and size limits
    """

    @pytest.mark.anyio
    async def test_match_function(self) -> None:
        """Test the match function correctly identifies parts with URLs."""
        p = UrlFetchProcessor()

        # Should match parts with URLs
        url_part = processor.ProcessorPart("Check out https://example.com")
        assert p.match(url_part) is True

        # Should not match parts without URLs
        no_url_part = processor.ProcessorPart("This is just plain text")
        assert p.match(no_url_part) is False

        # Should not match empty parts
        empty_part = processor.ProcessorPart("")
        assert p.match(empty_part) is False

    @pytest.mark.anyio
    async def test_url_extraction_inline(self) -> None:
        """Test URL extraction using the inline regex method."""
        # Single URL
        text = "Visit https://example.com for more info"
        urls = set(URL_REGEX.findall(text))
        assert urls == {"https://example.com"}

        # Multiple URLs
        text = "Check https://site1.com and https://site2.com"
        urls = set(URL_REGEX.findall(text))
        assert urls == {"https://site1.com", "https://site2.com"}

        # No URLs
        urls = set(URL_REGEX.findall("No links here"))
        assert urls == set()

    @pytest.mark.anyio
    async def test_passthrough_non_matching_parts(self) -> None:
        """Test that parts without URLs are passed through when configured."""
        p = UrlFetchProcessor()
        part = processor.ProcessorPart("No URLs here")

        results = [r async for r in p.call(part)]

        assert len(results) == 1
        assert results[0].text == "No URLs here"

    @pytest.mark.anyio
    async def test_config_include_original_part(self) -> None:
        """Test the include_original_part configuration option."""
        # Test with include_original_part=False
        config = FetchConfig(include_original_part=False)
        p = UrlFetchProcessor(config)
        part = processor.ProcessorPart("No URLs here")

        results = [r async for r in p.call(part)]

        # Should not include original part when no URLs found
        assert len(results) == 0

    @pytest.mark.anyio
    async def test_successful_fetch_with_mocking(self) -> None:
        """Test successful URL fetching with proper mocking."""
        config = FetchConfig(include_original_part=False)
        p = UrlFetchProcessor(config)

        # Mock the HTTP client
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock successful response - use MagicMock for sync methods
            mock_response = MagicMock()
            mock_response.text = "<html><body><h1>Test Content</h1></body></html>"
            mock_response.headers = {}
            mock_response.raise_for_status.return_value = None

            # Mock aiter_bytes to return the HTML content as bytes
            html_content = "<html><body><h1>Test Content</h1></body></html>"

            async def mock_aiter_bytes() -> AsyncIterable[bytes]:
                yield html_content.encode("utf-8")

            mock_response.aiter_bytes = mock_aiter_bytes
            mock_client.get.return_value = mock_response

            # Mock asyncio.to_thread for HTML parsing
            with patch("asyncio.to_thread") as mock_to_thread:
                mock_to_thread.return_value = "Test Content"

                part = processor.ProcessorPart("Visit https://example.com")
                results = [r async for r in p.call(part)]

                # Should have status and success parts
                status_parts = [
                    r for r in results if r.substream_name == processor.STATUS_STREAM
                ]
                content_parts = [
                    r for r in results if r.metadata.get("fetch_status") == "success"
                ]

                assert len(status_parts) == 1
                assert "Fetched successfully" in status_parts[0].text
                assert len(content_parts) == 1
                assert content_parts[0].text == "Test Content"
                assert content_parts[0].metadata["source_url"] == "https://example.com"

    @pytest.mark.anyio
    async def test_failed_fetch_with_mocking(self) -> None:
        """Test failed URL fetching with proper mocking."""
        config = FetchConfig(include_original_part=False)
        p = UrlFetchProcessor(config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_context = mock_client_class.return_value.__aenter__
            mock_context.return_value = mock_client

            # Mock failed response
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_request = MagicMock()
            mock_request.url = "https://notfound.com"
            mock_response.request = mock_request

            error = httpx.HTTPStatusError(
                "Not Found",
                request=mock_request,
                response=mock_response,
            )
            mock_client.get.side_effect = error

            part = processor.ProcessorPart("Visit https://notfound.com")
            results = [r async for r in p.call(part)]

            # Should have status and failure parts
            status_parts = [
                r for r in results if r.substream_name == processor.STATUS_STREAM
            ]
            failure_parts = [
                r for r in results if r.metadata.get("fetch_status") == "failure"
            ]

            assert len(status_parts) == 1
            assert "Fetch failed" in status_parts[0].text
            assert len(failure_parts) == 1
            assert failure_parts[0].text == ""  # Empty content for failures
            assert "404" in failure_parts[0].metadata["fetch_error"]

    @pytest.mark.anyio
    async def test_fail_on_error_config(self) -> None:
        """Test that fail_on_error configuration raises exceptions."""
        config = FetchConfig(fail_on_error=True)
        p = UrlFetchProcessor(config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_context = mock_client_class.return_value.__aenter__
            mock_context.return_value = mock_client

            # Mock failed response
            mock_request = MagicMock()
            mock_request.url = "https://error.com"
            error = httpx.RequestError(
                "Connection failed",
                request=mock_request,
            )
            mock_client.get.side_effect = error

            part = processor.ProcessorPart("Visit https://error.com")

            with pytest.raises(RuntimeError):
                async for _ in p.call(part):
                    pass

    @pytest.mark.anyio
    async def test_extract_text_only_config(self) -> None:
        """Test the extract_text_only configuration option."""
        config = FetchConfig(
            extract_text_only=False,
            include_original_part=False,
        )
        p = UrlFetchProcessor(config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_context = mock_client_class.return_value.__aenter__
            mock_context.return_value = mock_client

            # Mock response with HTML - use MagicMock for sync methods
            mock_response = MagicMock()
            html_content = "<html><body><h1>Raw HTML</h1></body></html>"
            mock_response.headers = {}
            mock_response.raise_for_status.return_value = None

            # Mock aiter_bytes to return the HTML content as bytes

            async def mock_aiter_bytes() -> AsyncIterable[bytes]:
                yield html_content.encode("utf-8")

            mock_response.aiter_bytes = mock_aiter_bytes
            mock_client.get.return_value = mock_response

            part = processor.ProcessorPart("Visit https://example.com")
            results = [r async for r in p.call(part)]

            content_parts = [
                r for r in results if r.metadata.get("fetch_status") == "success"
            ]
            assert len(content_parts) == 1
            assert "<html>" in content_parts[0].text  # Should preserve HTML
            assert content_parts[0].mimetype == "text/html; charset=utf-8"

    def test_fetch_config_initialization(self) -> None:
        """Test FetchConfig initialization with different parameters."""
        # Default config
        config = FetchConfig()
        assert config.timeout == 15.0
        assert config.include_original_part is True
        assert config.fail_on_error is False
        assert config.extract_text_only is True

        # Custom config
        config = FetchConfig(
            timeout=30.0,
            include_original_part=False,
            fail_on_error=True,
            extract_text_only=False,
        )
        assert config.timeout == 30.0
        assert config.include_original_part is False
        assert config.fail_on_error is True
        assert config.extract_text_only is False

    def test_processor_initialization(self) -> None:
        """Test UrlFetchProcessor initialization."""
        # Default initialization
        p = UrlFetchProcessor()
        assert p.config.timeout == 15.0

        # With custom config
        config = FetchConfig(timeout=45.0)
        p = UrlFetchProcessor(config)
        assert p.config.timeout == 45.0

    @pytest.mark.anyio
    async def test_default_security_settings(self) -> None:
        """Test that security is enabled by default."""
        config = FetchConfig()
        assert config.block_private_ips is True
        assert config.block_localhost is True
        assert config.block_metadata_endpoints is True
        assert config.max_response_size == 10 * 1024 * 1024

    @pytest.mark.anyio
    async def test_private_ip_blocking(self) -> None:
        """Test blocking of private IP addresses."""
        p = UrlFetchProcessor()

        # Test private IP validation
        private_urls = [
            "http://192.168.1.1",
            "http://10.0.0.1",
            "http://172.16.0.1",
            "http://127.0.0.1",
            "http://localhost",
        ]

        for url in private_urls:
            is_valid, error = await p._validate_url(url)
            assert not is_valid
            assert error is not None
            assert "blocked" in error.lower()

    @pytest.mark.anyio
    async def test_metadata_endpoint_blocking(self) -> None:
        """Test blocking of cloud metadata endpoints."""
        p = UrlFetchProcessor()

        metadata_urls = [
            "http://169.254.169.254/metadata",
            "http://metadata.google.internal",
            "http://metadata/service",
        ]

        for url in metadata_urls:
            is_valid, error = await p._validate_url(url)
            assert not is_valid
            assert error is not None
            assert "metadata" in error.lower()

    @pytest.mark.anyio
    async def test_scheme_validation(self) -> None:
        """Test URL scheme validation."""
        config = FetchConfig(allowed_schemes=["https"])
        p = UrlFetchProcessor(config)

        # HTTP should be blocked
        is_valid, error = await p._validate_url("http://example.com")
        assert not is_valid
        assert error is not None
        assert "scheme" in error.lower()

        # HTTPS should be allowed
        is_valid, error = await p._validate_url("https://example.com")
        assert is_valid

    @pytest.mark.anyio
    async def test_domain_allowlist(self) -> None:
        """Test domain allow list functionality."""
        config = FetchConfig(allowed_domains=["example.com", "trusted.org"])
        p = UrlFetchProcessor(config)

        # Allowed domain should pass
        is_valid, error = await p._validate_url("https://example.com/page")
        assert is_valid

        # Subdomain should pass
        is_valid, error = await p._validate_url("https://sub.example.com")
        assert is_valid

        # Blocked domain should fail
        is_valid, error = await p._validate_url("https://malicious.com")
        assert not is_valid
        assert error is not None
        assert "not in allowed list" in error

    @pytest.mark.anyio
    async def test_domain_blocklist(self) -> None:
        """Test domain block list functionality."""
        config = FetchConfig(blocked_domains=["malicious.com", "spam.org"])
        p = UrlFetchProcessor(config)

        # Normal domain should pass
        is_valid, error = await p._validate_url("https://example.com")
        assert is_valid

        # Blocked domain should fail
        is_valid, error = await p._validate_url("https://malicious.com")
        assert not is_valid
        assert error is not None
        assert "is blocked" in error

        # Subdomain of blocked domain should fail
        is_valid, error = await p._validate_url("https://sub.malicious.com")
        assert not is_valid

    @pytest.mark.anyio
    async def test_security_can_be_disabled(self) -> None:
        """Test that security features can be disabled if needed."""
        config = FetchConfig(
            block_private_ips=False,
            block_localhost=False,
            block_metadata_endpoints=False,
        )
        p = UrlFetchProcessor(config)

        # These should now be allowed
        test_urls = [
            "http://127.0.0.1",
            "http://localhost",
            "http://169.254.169.254",
        ]

        for url in test_urls:
            is_valid, error = await p._validate_url(url)
            msg = f"URL {url} should be valid when security disabled"
            assert is_valid, msg

    @pytest.mark.anyio
    async def test_config_with_security_fields(self) -> None:
        """Test FetchConfig with security fields."""
        config = FetchConfig(
            allowed_domains=["example.com"],
            blocked_domains=["bad.com"],
            allowed_schemes=["https"],
            max_response_size=5 * 1024 * 1024,
        )

        assert config.allowed_domains == ["example.com"]
        assert config.blocked_domains == ["bad.com"]
        assert config.allowed_schemes == ["https"]
        assert config.max_response_size == 5 * 1024 * 1024

    @pytest.mark.anyio
    async def test_url_validation_integration(self) -> None:
        """Test URL validation integrated with the processor."""
        config = FetchConfig(
            allowed_domains=["example.com"],
            include_original_part=False,
        )
        p = UrlFetchProcessor(config)

        # Test with blocked domain
        part = processor.ProcessorPart("Visit https://malicious.com")
        results = [r async for r in p.call(part)]

        # Should have status and failure parts
        status_parts = [
            r for r in results if r.substream_name == processor.STATUS_STREAM
        ]
        failure_parts = [
            r for r in results if r.metadata.get("fetch_status") == "failure"
        ]

        assert len(status_parts) == 1
        assert "Fetch failed" in status_parts[0].text
        assert len(failure_parts) == 1
        error_msg = failure_parts[0].metadata["fetch_error"]
        assert "Security validation failed" in error_msg

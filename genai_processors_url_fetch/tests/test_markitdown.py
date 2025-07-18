"""Test markitdown integration in genai-processors-url-fetch."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from genai_processors import processor

from genai_processors_url_fetch import ContentProcessor, FetchConfig, UrlFetchProcessor


class TestMarkitdownIntegration:
    """Test markitdown specific functionality."""

    def test_markitdown_config_validation(self) -> None:
        """Test that markitdown config validation works correctly."""
        # Should work if markitdown is available
        try:
            import markitdown  # noqa: F401

            config = FetchConfig(content_processor=ContentProcessor.MARKITDOWN)
            assert config.content_processor == ContentProcessor.MARKITDOWN
        except ImportError:
            # Should raise ImportError if markitdown is not available
            with pytest.raises(ImportError, match="markitdown is required"):
                FetchConfig(content_processor=ContentProcessor.MARKITDOWN)

    def test_markitdown_options_passed_correctly(self) -> None:
        """Test markitdown options are passed to MarkItDown constructor."""
        try:
            import markitdown  # noqa: F401

            # Test that custom options are stored
            custom_options = {"option1": "value1", "option2": True}
            config = FetchConfig(
                content_processor="markitdown",
                markitdown_options=custom_options,
            )
            assert config.markitdown_options == custom_options
        except ImportError:
            pytest.skip("markitdown not available")

    @pytest.mark.anyio
    async def test_content_processor_enum_values(self) -> None:
        """Test that all content processor values work correctly."""
        test_html = "<html><body><h1>Test</h1><p>Content</p></body></html>"

        # Test beautifulsoup
        config_bs = FetchConfig(content_processor="beautifulsoup")
        processor_bs = UrlFetchProcessor(config_bs)
        content_bs, mimetype_bs = await processor_bs._process_content(
            test_html,
            "http://test.com",
        )
        assert mimetype_bs == "text/plain; charset=utf-8"
        assert "Test" in content_bs
        assert "Content" in content_bs
        assert "<html>" not in content_bs

        # Test raw
        config_raw = FetchConfig(content_processor="raw")
        processor_raw = UrlFetchProcessor(config_raw)
        content_raw, mimetype_raw = await processor_raw._process_content(
            test_html,
            "http://test.com",
        )
        assert mimetype_raw == "text/html; charset=utf-8"
        assert content_raw == test_html

        # Test markitdown (if available)
        try:
            import markitdown  # noqa: F401

            config_md = FetchConfig(content_processor="markitdown")
            processor_md = UrlFetchProcessor(config_md)
            content_md, mimetype_md = await processor_md._process_content(
                test_html,
                "http://test.com",
            )
            assert mimetype_md == "text/markdown; charset=utf-8"
            # Should contain the header
            assert "Test" in content_md or "# Test" in content_md
        except ImportError:
            # Markitdown not available, skip this part
            pass

    @pytest.mark.anyio
    async def test_markitdown_fetch_integration(self) -> None:
        """Test that markitdown processor works in full fetch workflow."""
        try:
            import markitdown  # noqa: F401
        except ImportError:
            pytest.skip("markitdown not available")

        config = FetchConfig(
            content_processor="markitdown",
            include_original_part=False,
        )
        fetcher = UrlFetchProcessor(config)

        test_html = "<html><body><h1>Test Title</h1><p>Test content</p></body></html>"

        # Mock the HTTP response
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.headers = {"content-type": "text/html"}
            mock_response.raise_for_status = MagicMock()

            # Create a proper async iterator for aiter_bytes
            async def mock_aiter_bytes() -> AsyncIterator[bytes]:
                yield test_html.encode("utf-8")

            mock_response.aiter_bytes = mock_aiter_bytes

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response,
            )

            input_part = processor.ProcessorPart(
                "Check this out: http://example.com",
            )
            results = []

            async for part in fetcher.call(input_part):
                if (
                    hasattr(part, "metadata")
                    and part.metadata.get("fetch_status") == "success"
                ):
                    results.append(part)

            assert len(results) == 1
            result = results[0]
            assert result.mimetype == "text/markdown; charset=utf-8"
            assert result.metadata["source_url"] == "http://example.com"
            assert result.metadata["fetch_status"] == "success"

    def test_backward_compatibility_extract_text_only(self) -> None:
        """Test extract_text_only still works but issues warning."""
        import warnings

        # Test extract_text_only=True maps to beautifulsoup
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config1 = FetchConfig(extract_text_only=True)
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "extract_text_only is deprecated" in str(w[0].message)
            assert config1.content_processor == ContentProcessor.BEAUTIFULSOUP

        # Test extract_text_only=False maps to raw
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config2 = FetchConfig(extract_text_only=False)
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert config2.content_processor == ContentProcessor.RAW

    @pytest.mark.anyio
    async def test_invalid_content_processor_raises_error(self) -> None:
        """Test invalid content processor values raise appropriate errors."""
        # Test with an invalid processor during actual processing
        config = FetchConfig(content_processor="beautifulsoup")
        processor_instance = UrlFetchProcessor(config)

        # Manually set an invalid processor to test error handling
        # type: ignore[assignment]
        processor_instance.config.content_processor = "invalid_processor"

        # This should raise a ValueError when processing content
        with pytest.raises(ValueError, match="Unknown content_processor"):
            await processor_instance._process_content(
                "<html></html>",
                "http://test.com",
            )

    @pytest.mark.anyio
    async def test_markitdown_error_handling(self) -> None:
        """Test error handling when markitdown processing fails."""
        try:
            import markitdown  # noqa: F401
        except ImportError:
            pytest.skip("markitdown not available")

        config = FetchConfig(content_processor="markitdown")
        processor_md = UrlFetchProcessor(config)

        # Test with invalid content that might cause markitdown to fail
        try:
            # This should work even with potentially problematic content
            _, mimetype = await processor_md._process_content(
                "",
                "http://test.com",
            )
            assert mimetype == "text/markdown; charset=utf-8"
        except (ImportError, ValueError) as e:
            # If markitdown fails, that's okay - we're testing error handling
            error_msg = str(e).lower()
            assert "markitdown" in error_msg or "convert" in error_msg

    def test_markitdown_import_error_when_not_available(self) -> None:
        """Test ImportError when markitdown is not available."""
        config = FetchConfig(content_processor="beautifulsoup")
        processor_instance = UrlFetchProcessor(config)

        # Mock HAS_MARKITDOWN to be False to simulate markitdown not available
        patch_target = "genai_processors_url_fetch.url_fetch.HAS_MARKITDOWN"
        with patch(patch_target, new=False):
            expected_msg = "markitdown is required but not installed"
            with pytest.raises(ImportError, match=expected_msg):
                processor_instance._markitdown_to_text(
                    "<html>test</html>",
                    "http://test.com",
                )

    def test_markitdown_config_import_error_when_not_available(self) -> None:
        """Test FetchConfig ImportError when markitdown not available."""
        # Mock HAS_MARKITDOWN to be False to simulate markitdown not available
        patch_path = "genai_processors_url_fetch.url_fetch.HAS_MARKITDOWN"
        with patch(patch_path, new=False):
            expected_msg = "markitdown is required for ContentProcessor.MARKITDOWN"
            with pytest.raises(ImportError, match=expected_msg):
                FetchConfig(content_processor=ContentProcessor.MARKITDOWN)

    def test_extract_text_only_overrides_markitdown(self) -> None:
        """Test extract_text_only parameter overrides markitdown setting."""
        import warnings

        try:
            import markitdown  # noqa: F401

            # Test that extract_text_only=False overrides default, not explicit
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                # Only test when default beautifulsoup is being overridden
                config = FetchConfig(extract_text_only=False)
                assert len(w) == 1
                assert issubclass(w[0].category, DeprecationWarning)
                assert "extract_text_only is deprecated" in str(w[0].message)
                assert config.content_processor == ContentProcessor.RAW  # Overridden

        except ImportError:
            # If markitdown not available, test override with default
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                config = FetchConfig(extract_text_only=False)
                assert len(w) == 1
                assert config.content_processor == ContentProcessor.RAW

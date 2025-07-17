# genai-processors-url-fetch

[![PyPI version](https://img.shields.io/pypi/v/genai-processors-url-fetch.svg)](https://pypi.org/project/genai-processors-url-fetch/)
[![Validation](https://github.com/mbeacom/genai-processors-url-fetch/actions/workflows/validate.yml/badge.svg)](https://github.com/mbeacom/genai-processors-url-fetch/actions/workflows/validate.yml)
[![codecov](https://codecov.io/github/mbeacom/genai-processors-url-fetch/graph/badge.svg?token=ghq0EnDIZl)](https://codecov.io/github/mbeacom/genai-processors-url-fetch)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

A URL Fetch Processor for Google's genai-processors framework that detects URLs in text, fetches their content concurrently, and yields new ProcessorParts containing the page content.

## UrlFetchProcessor

The UrlFetchProcessor is a PartProcessor that detects URLs in incoming text parts, fetches their content concurrently, and yields new ProcessorParts containing the page content. It is a powerful and secure tool for enabling AI agents to access and process information from the web.

### Motivation

Many advanced AI applications, especially those involving Retrieval-Augmented Generation (RAG) or agentic behavior, need to interact with the outside world. This processor provides the fundamental capability of "reading" a webpage.

* **Enables RAG:** Fetches the content of source URLs so an LLM can use up-to-date information to answer questions.
* **Automates Research:** Allows an agent to follow links to gather context for a research task.
* **Simplifies Tooling:** Abstracts away the complexities of asynchronous HTTP requests, rate-limiting, security validation, and HTML parsing.

### Installation

Install the package using pip:

```bash
pip install genai-processors-url-fetch
```

For enhanced content processing with markitdown support:

```bash
pip install genai-processors-url-fetch[markitdown]
```

Or using uv (recommended):

```bash
uv add genai-processors-url-fetch
# or with markitdown support
uv add genai-processors-url-fetch[markitdown]
```

### Quick Start

```python
from genai_processors import processor
from genai_processors_url_fetch import UrlFetchProcessor, FetchConfig

# Basic usage with defaults (BeautifulSoup text extraction)
fetcher = UrlFetchProcessor()

# Use markitdown for richer content processing
config = FetchConfig(content_processor="markitdown")
markitdown_fetcher = UrlFetchProcessor(config)

# Process text containing URLs
input_text = "Check out https://developers.googleblog.com/en/genai-processors/ for more information"
input_part = processor.ProcessorPart(input_text)

async for result_part in fetcher.call(input_part):
    if result_part.metadata.get("fetch_status") == "success":
        print(f"Fetched: {result_part.metadata['source_url']}")
        print(f"Content: {result_part.text[:100]}...")
```

### Security Features

A primary design goal of this processor is to fetch web content safely. By default, it includes several security controls to prevent common vulnerabilities like Server-Side Request Forgery (SSRF).

* **IP Address Blocking:** Prevents requests to private, reserved, and loopback (localhost) IP address ranges (e.g., 192.168.1.1, 10.0.0.1, 127.0.0.1).
* **Cloud Metadata Protection:** Blocks requests to known cloud provider metadata endpoints (e.g., 169.254.169.254), which can expose sensitive instance information.
* **Domain Filtering:** Allows you to restrict fetches to an explicit list of allowed domains or deny requests to a list of blocked domains.
* **Scheme Enforcement:** By default, only allows http and https schemes, preventing requests to other protocols like file:// or ftp://.
* **Response Size Limiting:** Protects against "zip bomb" type attacks by enforcing a maximum size for response bodies (default is 10MB).

All security features are enabled by default but can be configured via the FetchConfig object.

### Configuration

The processor uses a dataclass-based configuration system for clean, type-safe settings. You can customize the processor's behavior by passing a FetchConfig object during initialization.

```python
from genai_processors_url_fetch import UrlFetchProcessor, FetchConfig

# Example of a customized security configuration
config = FetchConfig(
    timeout=10.0,
    allowed_domains=["github.com", "pypi.org"],  # Only allow these domains
    fail_on_error=True,
    max_response_size=5 * 1024 * 1024  # 5MB limit
)
secure_fetcher = UrlFetchProcessor(config=config)
```

#### FetchConfig Parameters

The `FetchConfig` dataclass provides comprehensive configuration options organized into logical categories:

##### Basic Behavior

* **timeout** (float, default: 15.0): The timeout in seconds for each HTTP request.
* **max_concurrent_fetches_per_host** (int, default: 3): The maximum number of parallel requests to a single hostname.
* **user_agent** (str, default: "GenAI-Processors/UrlFetchProcessor"): The User-Agent string to send with HTTP requests.
* **include_original_part** (bool, default: True): If True, the original ProcessorPart that contained the URL(s) will be yielded at the end of processing.
* **fail_on_error** (bool, default: False): If True, the processor will raise a RuntimeError on the first failed fetch.
* **content_processor** (Literal["beautifulsoup", "markitdown", "raw"], default: "beautifulsoup"): Content processing method.
  - `"beautifulsoup"`: Extract clean text using BeautifulSoup (fastest, good for simple HTML)
  - `"markitdown"`: Convert content to markdown using Microsoft's markitdown library (best for rich content, requires optional dependency)
  - `"raw"`: Return the raw HTML content without processing
* **markitdown_options** (dict[str, Any], default: {}): Options passed to the markitdown MarkItDown constructor when using markitdown processor.
* **extract_text_only** (bool | None, default: None): **Deprecated.** Use `content_processor` instead. For backward compatibility: `True` maps to `"beautifulsoup"`, `False` maps to `"raw"`.

##### Security Controls

* **block_private_ips** (bool, default: True): If True, blocks requests to RFC 1918 and other reserved IP ranges.
* **block_localhost** (bool, default: True): If True, blocks requests to 127.0.0.1, ::1, and localhost.
* **block_metadata_endpoints** (bool, default: True): If True, blocks requests to common cloud metadata services.
* **allowed_domains** (list[str] | None, default: None): If set, only URLs matching a domain in this list (or its subdomains) will be fetched.
* **blocked_domains** (list[str] | None, default: None): If set, any URL matching a domain in this list (or its subdomains) will be blocked.
* **allowed_schemes** (list[str], default: ['http', 'https']): A list of allowed URL schemes.
* **max_response_size** (int, default: 10485760): The maximum size of the response body in bytes (10MB).

### Content Processing Options

The UrlFetchProcessor supports three content processing methods via the `content_processor` configuration:

#### BeautifulSoup (Default)

```python
config = FetchConfig(content_processor="beautifulsoup")
fetcher = UrlFetchProcessor(config)
# Returns: Clean text extracted from HTML, fastest processing
# Mimetype: "text/plain; charset=utf-8"
```

#### Markitdown (Rich Content Processing)

The markitdown processor provides the richest content extraction by converting HTML to structured markdown. It's ideal for preserving formatting, tables, links, and document structure.

```python
config = FetchConfig(
    content_processor="markitdown",
    markitdown_options={
        "extract_tables": True,     # Preserve table structure
        "preserve_links": True,     # Keep link formatting
        # Additional markitdown options can be specified here
    }
)
fetcher = UrlFetchProcessor(config)
# Returns: Rich markdown with preserved formatting, tables, links
# Mimetype: "text/markdown; charset=utf-8"
# Requires: pip install genai-processors-url-fetch[markitdown]
```

**When to use markitdown:**

* Processing documentation pages or wikis
* Extracting structured content with tables and lists
* Preserving links and formatting for downstream processing
* Working with rich content that benefits from markdown structure

**Comparison with other processors:**

* **BeautifulSoup**: Fast text extraction, loses formatting
* **Markitdown**: Rich markdown, preserves structure, slower processing
* **Raw**: Full HTML control, requires custom parsing

#### Raw HTML

```python
config = FetchConfig(content_processor="raw")
fetcher = UrlFetchProcessor(config)
# Returns: Original HTML content without processing
# Mimetype: "text/html; charset=utf-8"
```

### Usage Examples

#### High Security Configuration

```python
config = FetchConfig(
    allowed_domains=["trusted.com", "docs.python.org"],
    allowed_schemes=["https"],
    block_private_ips=True,
    max_response_size=1024 * 1024,  # 1MB
    timeout=10.0
)
fetcher = UrlFetchProcessor(config)
```

#### Fast and Flexible

```python
config = FetchConfig(
    timeout=5.0,
    extract_text_only=False,  # Keep HTML
    include_original_part=False,  # Only return fetched content
    fail_on_error=True  # Stop on first error
)
fetcher = UrlFetchProcessor(config)
```

#### Pipeline Processing

```python
# Configure for pipeline use
config = FetchConfig(include_original_part=False)
fetcher = UrlFetchProcessor(config)

# Process input
results = [part async for part in fetcher.call(input_part)]

# Filter successful fetches
successful_content = [
    part for part in results
    if part.metadata.get("fetch_status") == "success"
]

# Further process the content
for content_part in successful_content:
    source_url = content_part.metadata["source_url"]
    text_content = content_part.text
    # ... your processing logic here
```

#### Markitdown Processing Example

```python
from genai_processors import streams
from genai_processors_url_fetch import UrlFetchProcessor, FetchConfig

# Configure markitdown processor for rich content extraction
config = FetchConfig(
    content_processor="markitdown",
    include_original_part=False,
    markitdown_options={
        "extract_tables": True,
        "preserve_links": True,
    }
)

processor = UrlFetchProcessor(config)

# Process URLs in text
text_with_urls = "Check out https://github.com/microsoft/markitdown for examples"
input_stream = streams.stream_content([text_with_urls])

async for part in processor(input_stream):
    if part.metadata.get("fetch_status") == "success":
        print(f"📄 Fetched from: {part.metadata['source_url']}")
        print(f"📝 Markdown content:\n{part.text}")
        print(f"✨ Content type: {part.mimetype}")
    elif part.substream_name == "status":
        print(f"Status: {part.text}")
```

### Behavior and Output

For each ProcessorPart that contains one or more URLs, the UrlFetchProcessor yields several new parts:

1. **Status Parts:** For each URL, a processor.status() message is yielded, indicating the outcome (✅ Fetched successfully... or ❌ Fetch failed...).
2. **Content Parts:** For each valid and successful fetch, a corresponding content part is yielded.
3. **Failure Parts:** For each fetch that fails due to a network error or security violation, a failure part is yielded (if fail_on_error is False).
4. **Original Part (Optional):** If include_original_part is True, the original part is yielded last.

#### On Successful Fetch

* A ProcessorPart is yielded with metadata['fetch_status'] set to 'success'.
* The metadata['source_url'] contains the URL that was fetched.
* The text of the part contains the page content.
* The mimetype indicates the content type ('text/plain; charset=utf-8' or 'text/html; charset=utf-8').

#### On Failed Fetch

* A ProcessorPart is yielded with metadata['fetch_status'] set to 'failure'.
* The metadata['fetch_error'] contains a string describing the error (e.g., "Security validation failed: Domain '...' is blocked" or "HTTP Error: 404...").
* The part's text will be empty.

### Error Handling

The processor provides detailed error information through metadata:

#### Metadata Fields

* **fetch_status**: "success" or "failure"
* **source_url**: The URL that was fetched
* **fetch_error**: Error message for failed fetches (only present on failures)

#### Example Error Handling

```python
async for part in fetcher.call(input_part):
    status = part.metadata.get("fetch_status")

    if status == "success":
        print(f"✅ Fetched: {part.metadata['source_url']}")
        print(f"Content: {part.text}")
    elif status == "failure":
        print(f"❌ Failed: {part.metadata['source_url']}")
        print(f"Error: {part.metadata['fetch_error']}")
    elif part.substream_name == processor.STATUS_STREAM:
        print(f"📄 Status: {part.text}")
```

### Examples and Testing

#### Working Examples

For complete, runnable examples that demonstrate the UrlFetchProcessor, see:

**URL Content Summarizer** (`examples/url_content_summarizer.py`):
This example builds a URL content summarizer that:

* Fetches content from URLs in user input
* Uses secure configuration (HTTPS only, blocks private IPs)
* Integrates with GenAI models for content summarization
* Shows proper error handling and pipeline construction
* Provides a practical CLI interface

**Markitdown Content Processing** (`examples/markitdown_example.py`):
This example demonstrates markitdown processor capabilities:

* Shows different content processor options (BeautifulSoup, Markitdown, Raw)
* Compares output formats and use cases
* Demonstrates markitdown configuration options
* Shows how to handle different content types

To run the examples:

```bash
# Content summarizer (requires API key)
export GEMINI_API_KEY=your_api_key_here
python examples/url_content_summarizer.py

# Markitdown demo (requires markitdown optional dependency)
pip install genai-processors-url-fetch[markitdown]
python examples/markitdown_example.py
```

#### Test Suite

For comprehensive test coverage including security features, error handling, and all configuration options, see: `genai_processors_url_fetch/tests/test_url_fetch.py`

The test suite includes:

* Basic functionality tests
* Security feature validation
* Error handling scenarios
* Configuration option testing
* Mock implementations for reliable testing

### Considerations

1. **Security First**: Always configure appropriate security controls for your use case
2. **Resource Limits**: Set reasonable timeout and size limits to prevent resource exhaustion
3. **Error Handling**: Handle both successful and failed fetches appropriately in your application logic
4. **Rate Limiting**: Use the built-in per-host rate limiting to be respectful to target servers
5. **Content Processing**: Choose between text extraction and raw HTML based on your downstream processing needs

## Development

For development setup, testing, and contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

This project uses [uv](https://docs.astral.sh/uv/) for dependency management and [Poe the Poet](https://poethepoet.natn.io/) for task automation.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

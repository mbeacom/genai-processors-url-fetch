# genai-processors-url-fetch

The URL Fetch Gemini Processor to be used with Gemini's genai-processors.

## UrlFetchProcessor

The UrlFetchProcessor is a PartProcessor that detects URLs in incoming text parts, fetches their content concurrently, and yields new ProcessorParts containing the page content. It is a powerful and secure tool for enabling AI agents to access and process information from the web.

### Motivation

Many advanced AI applications, especially those involving Retrieval-Augmented Generation (RAG) or agentic behavior, need to interact with the outside world. This processor provides the fundamental capability of "reading" a webpage.

* **Enables RAG:** Fetches the content of source URLs so an LLM can use up-to-date information to answer questions.
* **Automates Research:** Allows an agent to follow links to gather context for a research task.
* **Simplifies Tooling:** Abstracts away the complexities of asynchronous HTTP requests, rate-limiting, security validation, and HTML parsing.

### Installation

The processor requires the httpx and beautifulsoup4 libraries. To use it, install the optional dependencies using the [url_fetcher] extra:

```bash
pip install "genai_processors[url_fetcher]"
```

### Quick Start

```python
from genai_processors import processor
from genai_processors_url_fetch import UrlFetchProcessor, FetchConfig

# Basic usage with defaults
fetcher = UrlFetchProcessor()

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
* **extract_text_only** (bool, default: True): If True, the processor will parse the HTML and return only the clean, readable text. If False, it will return the full, raw HTML content.

##### Security Controls

* **block_private_ips** (bool, default: True): If True, blocks requests to RFC 1918 and other reserved IP ranges.
* **block_localhost** (bool, default: True): If True, blocks requests to 127.0.0.1, ::1, and localhost.
* **block_metadata_endpoints** (bool, default: True): If True, blocks requests to common cloud metadata services.
* **allowed_domains** (list[str] | None, default: None): If set, only URLs matching a domain in this list (or its subdomains) will be fetched.
* **blocked_domains** (list[str] | None, default: None): If set, any URL matching a domain in this list (or its subdomains) will be blocked.
* **allowed_schemes** (list[str], default: ['http', 'https']): A list of allowed URL schemes.
* **max_response_size** (int, default: 10485760): The maximum size of the response body in bytes (10MB).

### **Usage Examples**

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

### **Error Handling**

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

#### Working Example

For a complete, runnable example that demonstrates the UrlFetchProcessor in a real application, see:

```bash
examples/url_content_summarizer.py
```

This example builds a URL content summarizer that:

* Fetches content from URLs in user input
* Uses secure configuration (HTTPS only, blocks private IPs)
* Integrates with GenAI models for content summarization
* Shows proper error handling and pipeline construction
* Provides a practical CLI interface

To run it, set your API key and try it:

```bash
export GOOGLE_API_KEY=your_api_key_here
python examples/url_content_summarizer.py
```

#### Test Suite

For comprehensive test coverage including security features, error handling, and all configuration options, see: `genai_processors/contrib/test/test_url_fetch.py`

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

# Chapter 4: YouTubeTranscriptExtractor

This chapter delves into the `YouTubeTranscriptExtractor` class, a critical component of the `mcp-server-youtube-transcript` project. This class is responsible for handling the complexities of extracting transcripts from YouTube videos, using the `youtube-captions-scraper` library. It handles tasks such as validating input, extracting the video ID, fetching the transcript, and formatting the result. It's used by the MCP server (introduced in the [`Model Context Protocol (MCP) Server`](01_model_context_protocol__mcp__server_.md) chapter) when the [`get_transcript` Tool](02__get_transcript__tool_.md) is called.

The `YouTubeTranscriptExtractor` class has three primary methods: `extractYoutubeId`, `getTranscript`, and `formatTranscript`. Let's examine each of these methods in detail.

## `extractYoutubeId`

The `extractYoutubeId` method is responsible for extracting the YouTube video ID from a given URL or directly from an ID string. It handles various URL formats and validates the input to ensure it's a valid YouTube URL or ID.

```typescript
/**
 * Extracts YouTube video ID from various URL formats or direct ID input
 */
extractYoutubeId(input: string): string {
  if (!input) {
    throw new McpError(
      ErrorCode.InvalidParams,
      'YouTube URL or ID is required'
    );
  }

  // Handle URL formats
  try {
    const url = new URL(input);
    if (url.hostname === 'youtu.be') {
      return url.pathname.slice(1);
    } else if (url.hostname.includes('youtube.com')) {
      const videoId = url.searchParams.get('v');
      if (!videoId) {
        throw new McpError(
          ErrorCode.InvalidParams,
          `Invalid YouTube URL: ${input}`
        );
      }
      return videoId;
    }
  } catch (error) {
    // Not a URL, check if it's a direct video ID
    if (!/^[a-zA-Z0-9_-]{11}$/.test(input)) {
      throw new McpError(
        ErrorCode.InvalidParams,
        `Invalid YouTube video ID: ${input}`
      );
    }
    return input;
  }

  throw new McpError(
    ErrorCode.InvalidParams,
    `Could not extract video ID from: ${input}`
  );
}
```

Here's a breakdown of the `extractYoutubeId` method:

1.  **Input Validation:** The method first checks if the input is provided. If not, it throws an `McpError` with the `ErrorCode.InvalidParams` code, indicating that the URL or ID is required.  See the [`McpError`](07_mcperror_.md) chapter for more information on error types.
2.  **URL Handling:** The method attempts to parse the input as a URL using the `URL` constructor.
    *   If the URL is a `youtu.be` short link, it extracts the video ID from the pathname (e.g., `youtu.be/dQw4w9WgXcQ` becomes `dQw4w9WgXcQ`).
    *   If the URL is a `youtube.com` link, it extracts the video ID from the `v` query parameter (e.g., `youtube.com/watch?v=dQw4w9WgXcQ` becomes `dQw4w9WgXcQ`). If the `v` parameter is missing, it throws an `McpError`.
3.  **Direct ID Handling:** If the input is not a valid URL (the `URL` constructor throws an error), the method assumes it might be a direct video ID. It checks if the input matches the expected format for a YouTube video ID (11 characters long, alphanumeric with underscores and hyphens). If it doesn't match, it throws an `McpError`.
4.  **Error Handling:** If the input is not a valid URL or ID, the method throws an `McpError` indicating that it couldn't extract the video ID.

## `getTranscript`

The `getTranscript` method retrieves the transcript for a given video ID and language using the `youtube-captions-scraper` library. It handles potential errors during the retrieval process.

```typescript
/**
 * Retrieves transcript for a given video ID and language
 */
async getTranscript(videoId: string, lang: string): Promise<string> {
  try {
    const transcript = await getSubtitles({
      videoID: videoId,
      lang: lang,
    });

    return this.formatTranscript(transcript);
  } catch (error) {
    console.error('Failed to fetch transcript:', error);
    throw new McpError(
      ErrorCode.InternalError,
      `Failed to retrieve transcript: ${(error as Error).message}`
    );
  }
}
```

Here's a breakdown of the `getTranscript` method:

1.  **Transcript Retrieval:** The method calls the `getSubtitles` function from the `youtube-captions-scraper` library, passing the `videoId` and `lang` parameters. This function returns a promise that resolves with an array of `TranscriptLine` objects, or rejects if an error occurs.  The `TranscriptLine` interface is described in the [`TranscriptLine Interface`](05_transcriptline_interface_.md) chapter.
2.  **Transcript Formatting:** The method calls the `formatTranscript` method (described below) to format the raw transcript data into a usable string.
3.  **Error Handling:** The method uses a `try...catch` block to handle any errors that occur during the transcript retrieval process. If an error occurs, it logs the error and throws an `McpError` with the `ErrorCode.InternalError` code, indicating that the transcript retrieval failed.

## `formatTranscript`

The `formatTranscript` method takes an array of `TranscriptLine` objects and formats them into a single string. It extracts the text from each line, trims whitespace, filters out empty lines, and joins the lines with spaces.

```typescript
/**
 * Formats transcript lines into readable text
 */
private formatTranscript(transcript: TranscriptLine[]): string {
  return transcript
    .map(line => line.text.trim())
    .filter(text => text.length > 0)
    .join(' ');
}
```

Here's a breakdown of the `formatTranscript` method:

1.  **Mapping:** The method uses the `map` method to iterate over the array of `TranscriptLine` objects and extract the `text` property from each line. The `trim()` method is called on each text to remove any leading or trailing whitespace.
2.  **Filtering:** The method uses the `filter` method to remove any empty lines from the array. This ensures that the final string doesn't contain any unnecessary whitespace.
3.  **Joining:** The method uses the `join` method to join the remaining lines with spaces, creating a single string containing the formatted transcript.

## Usage

The `YouTubeTranscriptExtractor` is used in the `handleToolCall` method of the `TranscriptServer` class (introduced in the [`Model Context Protocol (MCP) Server`](01_model_context_protocol__mcp__server_.md) chapter) when the `get_transcript` tool is called. The `handleToolCall` method calls the `extractYoutubeId` method to extract the video ID from the input URL or ID, and then calls the `getTranscript` method to retrieve the transcript for the specified video ID and language.

```typescript
private async handleToolCall(name: string, args: any): Promise<{ toolResult: CallToolResult }> {
  switch (name) {
    case "get_transcript": {
      const { url: input, lang = "en" } = args;

      // ... (Input validation)

      try {
        const videoId = this.extractor.extractYoutubeId(input);
        console.error(`Processing transcript for video: ${videoId}`);

        const transcript = await this.extractor.getTranscript(videoId, lang);
        console.error(`Successfully extracted transcript (${transcript.length} chars)`);

        // ... (Result formatting)

      } catch (error) {
        // ... (Error handling)
      }
    }
    // ...
  }
}
```

## Summary

In this chapter, we explored the `YouTubeTranscriptExtractor` class in detail. We learned how it extracts YouTube video IDs from URLs or direct IDs, retrieves transcripts using the `youtube-captions-scraper` library, and formats the transcript data into a usable string. This class encapsulates the core logic for extracting transcripts from YouTube videos within the `mcp-server-youtube-transcript` project.

Next, we will examine the [`TranscriptLine Interface`](05_transcriptline_interface_.md), which defines the structure of individual lines in the transcript.


---

Generated by [AI Codebase Knowledge Builder](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)
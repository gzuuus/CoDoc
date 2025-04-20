# Chapter 4: YouTube Transcript Extractor (`YouTubeTranscriptExtractor` class)

Welcome to Chapter 4! In the [previous chapter](03_request_handling___setrequesthandler____handletoolcall___.md), we saw how the `TranscriptServer` receives requests and uses the `handleToolCall` method to manage the process of executing a tool like `get_transcript`. We noted that `handleToolCall` delegates the actual work of fetching the transcript to another component. Now, we'll meet that component: the `YouTubeTranscriptExtractor` class.

Think of the `TranscriptServer` as the manager of a small workshop. The manager takes orders (`handleToolCall`) but relies on a specialist worker to perform the core task. The `YouTubeTranscriptExtractor` is that specialist worker, focused entirely on getting YouTube transcripts.

## What is `YouTubeTranscriptExtractor`?

The `YouTubeTranscriptExtractor` class is designed specifically for one job: extracting transcripts from YouTube videos. It bundles together all the logic needed for this task:

1.  **Parsing Input:** Understanding whether the user provided a full YouTube URL or just a video ID.
2.  **Fetching Data:** Communicating with the underlying YouTube transcript service (via an external library).
3.  **Formatting Output:** Cleaning up the raw transcript data into a simple, usable text format.

By putting all this logic into a separate class, we achieve **separation of concerns**. The `TranscriptServer` doesn't need to know the messy details of how transcripts are fetched; it just needs to know how to ask the `YouTubeTranscriptExtractor` to do it. This makes the overall application easier to understand, maintain, and test.

## Class Structure and Initialization

The `YouTubeTranscriptExtractor` class is defined in `src/index.ts`. It's a standard TypeScript class containing methods to perform its tasks.

```typescript
// src/index.ts (snippet)

// @ts-ignore - Ignoring potential type issues from the JS library
import { getSubtitles } from 'youtube-captions-scraper';
import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";

// Used internally to describe the structure from the scraper library
interface TranscriptLine {
  text: string;
  start: number; // Start time in seconds (not used in our final output)
  dur: number;   // Duration in seconds (not used in our final output)
}

class YouTubeTranscriptExtractor {

  // Method to parse input (URL or ID)
  extractYoutubeId(input: string): string {
    // ... implementation details ...
  }

  // Method to fetch the transcript using the video ID
  async getTranscript(videoId: string, lang: string): Promise<string> {
    // ... implementation details ...
  }

  // Private helper method to format the raw transcript data
  private formatTranscript(transcript: TranscriptLine[]): string {
    // ... implementation details ...
  }
}
```

**Explanation:**

*   **`import { getSubtitles } ...`**: Imports the specific function we need from the `youtube-captions-scraper` library, which does the actual interaction with YouTube.
*   **`import { ErrorCode, McpError } ...`**: Imports necessary types for error handling from the MCP SDK.
*   **`interface TranscriptLine { ... }`**: Defines the expected structure of data returned by `getSubtitles`. This helps TypeScript understand the data type.
*   **`class YouTubeTranscriptExtractor { ... }`**: Defines the class itself.
*   **Methods**: It contains the methods (`extractYoutubeId`, `getTranscript`, `formatTranscript`) that encapsulate the extraction logic. We'll examine each one.

This class is instantiated just once within the `TranscriptServer`'s constructor, as we saw briefly in [Chapter 1: Transcript Server Application (`TranscriptServer` class)](01_transcript_server_application___transcriptserver__class__.md):

```typescript
// src/index.ts (within TranscriptServer class constructor)

constructor() {
  // Create an instance of the extractor
  this.extractor = new YouTubeTranscriptExtractor();
  // ... rest of constructor ...
}
```

This `this.extractor` instance is then used later in the `handleToolCall` method.

## Parsing the Input: `extractYoutubeId`

The first step is to get a clean YouTube video ID from the user's input, which might be a full URL or just the ID itself.

```typescript
// src/index.ts (within YouTubeTranscriptExtractor class)

  /**
   * Extracts YouTube video ID from various URL formats or direct ID input
   */
  extractYoutubeId(input: string): string {
    if (!input) {
      throw new McpError(
        ErrorCode.InvalidParams, // Specific MCP error code
        'YouTube URL or ID is required'
      );
    }

    // Try parsing as a URL
    try {
      const url = new URL(input); // Standard browser/Node.js URL parser
      if (url.hostname === 'youtu.be') {
        // Handle short URLs like https://youtu.be/VIDEO_ID
        return url.pathname.slice(1); // Remove the leading '/'
      } else if (url.hostname.includes('youtube.com')) {
        // Handle standard URLs like https://www.youtube.com/watch?v=VIDEO_ID
        const videoId = url.searchParams.get('v'); // Extract the 'v' query parameter
        if (!videoId) {
          throw new Error("Missing 'v' parameter in YouTube URL"); // Internal error note
        }
        return videoId;
      }
    } catch (error) {
      // If 'new URL(input)' failed, it's not a valid URL.
      // Now check if it looks like a direct video ID (11 chars, specific alphabet)
      if (!/^[a-zA-Z0-9_-]{11}$/.test(input)) {
        throw new McpError(
          ErrorCode.InvalidParams,
          `Invalid YouTube video ID format: ${input}`
        );
      }
      // It looks like a valid ID format
      return input;
    }

    // If it wasn't handled as a URL or a direct ID, throw an error.
    // This is unlikely to be reached given the logic above, but acts as a safeguard.
    throw new McpError(
      ErrorCode.InvalidParams,
      `Could not extract video ID from: ${input}`
    );
  }
```

**Explanation:**

1.  **Input Check:** First, it checks if `input` was provided at all. If not, it throws an `McpError` with `ErrorCode.InvalidParams`. This signals back to the client that their request parameters were invalid. We'll discuss error handling in more detail in [Chapter 7: MCP Error Handling (`McpError`, `onerror`)](07_mcp_error_handling___mcperror____onerror___.md).
2.  **URL Parsing:** It uses a `try...catch` block to attempt parsing the `input` as a URL using the standard `URL` constructor.
    *   If successful, it checks the hostname:
        *   For `youtu.be` (short links), it extracts the ID from the path (e.g., `/dQw4w9WgXcQ` becomes `dQw4w9WgXcQ`).
        *   For `youtube.com` links, it specifically looks for the `v` query parameter (e.g., `watch?v=dQw4w9WgXcQ`). If `v` is missing, it's considered an invalid YouTube URL for our purposes.
3.  **Direct ID Check:** If the `input` is *not* a valid URL (the `catch` block is triggered), it checks if the `input` string matches the typical format of a YouTube video ID (11 characters containing letters, numbers, hyphens, and underscores) using a regular expression (`/^[a-zA-Z0-9_-]{11}$/`). If it doesn't match, it throws another `InvalidParams` error.
4.  **Return Value:** If a valid ID is found (either from a URL or as a direct ID), the method returns the 11-character video ID string.
5.  **Fallback Error:** If none of the checks succeed, a final `InvalidParams` error is thrown.

This method ensures we always work with a consistent video ID format before attempting to fetch the transcript.

## Fetching the Transcript: `getTranscript`

Once we have the `videoId`, we use the external `youtube-captions-scraper` library to fetch the transcript data.

```typescript
// src/index.ts (within YouTubeTranscriptExtractor class)

  /**
   * Retrieves transcript for a given video ID and language
   */
  async getTranscript(videoId: string, lang: string): Promise<string> {
    try {
      // Call the external library function
      const transcriptData: TranscriptLine[] = await getSubtitles({
        videoID: videoId, // Pass the extracted video ID
        lang: lang,       // Pass the desired language code
      });

      // Pass the raw data to our formatting method
      return this.formatTranscript(transcriptData);

    } catch (error) {
      // Handle errors from the external library (e.g., network issue, transcript not found)
      console.error('Failed to fetch transcript:', error);
      // Wrap the original error in an McpError for consistent reporting
      throw new McpError(
        ErrorCode.InternalError, // Use InternalError as the cause is server-side or external
        `Failed to retrieve transcript for video ${videoId} (${lang}): ${(error as Error).message}`
      );
    }
  }
```

**Explanation:**

1.  **`async` / `await`**: The method is marked `async` because fetching data over the network takes time. We use `await getSubtitles(...)` to pause execution until the library returns the transcript data (or an error).
2.  **`try...catch`**: We wrap the call to `getSubtitles` in a `try...catch` block because the operation might fail (e.g., invalid video ID, no transcript available for that language, network problems).
3.  **`getSubtitles({ videoID: videoId, lang: lang })`**: This is the core call to the external library. We pass the `videoId` and the requested `lang` code. The library handles the communication with YouTube. It's expected to return an array of `TranscriptLine` objects (or throw an error).
4.  **`this.formatTranscript(transcriptData)`**: If `getSubtitles` is successful, it returns the raw transcript data (`transcriptData`). We immediately pass this data to our private helper method `formatTranscript` to clean it up. The result of `formatTranscript` (a simple string) is then returned by `getTranscript`.
5.  **Error Handling:** If `getSubtitles` throws an error, the `catch` block executes.
    *   We log the original error to the server console for debugging (`console.error`).
    *   We then throw a *new* `McpError`. We use `ErrorCode.InternalError` because from the client's perspective, the problem wasn't with their request parameters (which were validated earlier), but with the server's ability to fulfill the request (due to an external dependency failure or other internal issue). We include the original error's message for more context.

## Formatting the Output: `formatTranscript`

The `youtube-captions-scraper` library returns the transcript as an array of objects, each containing a piece of text and timing information. Our tool aims to provide a simple, continuous text string. The `formatTranscript` method handles this conversion.

```typescript
// src/index.ts (within YouTubeTranscriptExtractor class)

  /**
   * Formats transcript lines into readable text (private helper method)
   */
  private formatTranscript(transcript: TranscriptLine[]): string {
    // Process the array of transcript lines
    return transcript
      // 1. Extract the 'text' property from each line object
      .map(line => line.text.trim())
      // 2. Remove any empty lines that might result after trimming
      .filter(text => text.length > 0)
      // 3. Join all the text pieces together with a space in between
      .join(' ');
  }
```

**Explanation:**

*   **`private`**: This method is marked `private` because it's only intended for internal use within the `YouTubeTranscriptExtractor` class (specifically, by `getTranscript`). It's not meant to be called directly from outside the class.
*   **Input:** It takes the `transcript` array (of `TranscriptLine` objects) as input.
*   **`.map(line => line.text.trim())`**: The `map` array method creates a *new* array by applying a function to each element of the original array. Here, for each `line` object, it extracts the `text` property and removes leading/trailing whitespace using `.trim()`. The result is an array of strings.
*   **`.filter(text => text.length > 0)`**: The `filter` array method creates a *new* array containing only the elements that pass a certain test. Here, it keeps only the strings that are not empty after trimming.
*   **`.join(' ')`**: The `join` array method combines all elements of an array into a single string, inserting the specified separator (in this case, a space `' '`) between each element.
*   **Return Value:** The final result is a single string containing the concatenated text of the transcript, ready to be sent back to the client.

## Putting It Together

Now we can see the full flow orchestrated by `handleToolCall` in [Chapter 3](03_request_handling___setrequesthandler____handletoolcall___.md):

1.  `handleToolCall` receives the request with `name`="get\_transcript" and `args` (`url`, `lang`).
2.  It validates the basic types of `args`.
3.  It calls `this.extractor.extractYoutubeId(args.url)` to get the `videoId`. This method performs detailed validation on the URL/ID itself, throwing `McpError(InvalidParams)` if needed.
4.  It calls `await this.extractor.getTranscript(videoId, args.lang)`.
    *   Inside `getTranscript`, `getSubtitles` is called.
    *   If successful, `formatTranscript` cleans the data.
    *   The clean transcript string is returned to `handleToolCall`.
    *   If `getSubtitles` fails, `getTranscript` throws `McpError(InternalError)`.
5.  `handleToolCall` receives the transcript string (or catches the `McpError`).
6.  If successful, `handleToolCall` formats the final `toolResult` object with the transcript string and `isError: false`.
7.  If an `McpError` was caught at any step, `handleToolCall` ensures it's properly propagated back to the MCP `Server`.

## Summary

The `YouTubeTranscriptExtractor` class is a crucial component that encapsulates the specific logic for retrieving and processing YouTube transcripts. It keeps this specialized task separate from the general server communication handled by `TranscriptServer` and the MCP `Server`.

*   It provides methods to `extractYoutubeId` (validating and normalizing user input), `getTranscript` (using an external library to fetch data and handling errors), and `formatTranscript` (cleaning the data).
*   It makes effective use of `try...catch` blocks and `McpError` to handle potential issues gracefully, distinguishing between invalid client input (`InvalidParams`) and internal/external failures (`InternalError`).
*   This separation makes the codebase cleaner, more modular, and easier to manage.

So far, we've seen the main application (`TranscriptServer`), how tools are defined (`TOOLS`), how requests are handled (`setRequestHandler`, `handleToolCall`), and the specialist component for the core task (`YouTubeTranscriptExtractor`). Now, let's zoom in on the underlying engine that manages the communication protocol itself: the MCP `Server` class from the SDK.

**Next:** [Chapter 5: MCP Server (`Server` class)](05_mcp_server___server__class__.md)

---

Generated by [AI Codebase Knowledge Builder](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)
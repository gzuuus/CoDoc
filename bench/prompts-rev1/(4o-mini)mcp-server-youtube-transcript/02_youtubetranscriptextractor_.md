# Chapter 2: YouTubeTranscriptExtractor


In this chapter, we will explore the `YouTubeTranscriptExtractor` class, which is a core component of the `mcp-server-youtube-transcript` project. This class is essential for extracting and formatting transcripts from YouTube videos. Understanding how it works will help us appreciate how our server retrieves subtitles from video content effectively.

## What is YouTubeTranscriptExtractor?

Think of the `YouTubeTranscriptExtractor` as a specialized tool for fetching the spoken words from YouTube videos, similar to how a translator captures spoken text in a different language. It identifies video IDs from various URL formats or direct IDs and retrieves the corresponding subtitles using an external library.

### Key Responsibilities

The `YouTubeTranscriptExtractor` class has two primary responsibilities:

1. **Extracting Video ID**: It can handle different formats of YouTube URLs or user-provided video IDs to extract a consistent video ID.
2. **Retrieving Transcripts**: It fetches the subtitles for the specified video ID in a selected language.

Let’s break down the class and its methods.

## Structure of the YouTubeTranscriptExtractor Class

### 1. Constructor

```typescript
class YouTubeTranscriptExtractor {
  constructor() {
    // Initialization logic can be added here in the future if needed
  }
}
```

The constructor is where we can initialize whatever settings or configurations might be needed when we create an instance of this class. Currently, it doesn’t have any specific initialization logic.

### 2. Extracting Video ID

The method responsible for extracting the YouTube video ID is `extractYoutubeId`.

```typescript
extractYoutubeId(input: string): string {
  if (!input) {
    throw new McpError(ErrorCode.InvalidParams, 'YouTube URL or ID is required');
  }
  
  try {
    const url = new URL(input); // Create a URL object from the input string
    if (url.hostname === 'youtu.be') {
      return url.pathname.slice(1); // Extract video ID from shortened URL
    } else if (url.hostname.includes('youtube.com')) {
      const videoId = url.searchParams.get('v'); // Get video ID from query parameters
      if (!videoId) {
        throw new McpError(ErrorCode.InvalidParams, `Invalid YouTube URL: ${input}`);
      }
      return videoId;
    }
  } catch (error) {
    // Handle direct video ID or invalid URL
    if (!/^[a-zA-Z0-9_-]{11}$/.test(input)) {
      throw new McpError(ErrorCode.InvalidParams, `Invalid YouTube video ID: ${input}`);
    }
    return input; // Return input if it's valid direct video ID
  }

  throw new McpError(ErrorCode.InvalidParams, `Could not extract video ID from: ${input}`);
}
```

#### Explanation:

- **Input Validation**: The method checks if the provided input is valid.
- **URL Handling**: It uses the URL API to parse YouTube URLs. Depending on the structure, it extracts the video ID.
- **Error Handling**: If the input isn’t a valid URL or video ID, it throws an error.

### 3. Retrieving the Transcript

Next, we have the method that fetches the transcript:

```typescript
async getTranscript(videoId: string, lang: string): Promise<string> {
  try {
    const transcript = await getSubtitles({
      videoID: videoId,
      lang: lang,
    });

    return this.formatTranscript(transcript); // Format the retrieved transcript
  } catch (error) {
    console.error('Failed to fetch transcript:', error);
    throw new McpError(ErrorCode.InternalError, `Failed to retrieve transcript: ${(error as Error).message}`);
  }
}
```

#### Explanation:

- **Fetching Transcripts**: It uses the `getSubtitles` function from the `youtube-captions-scraper` library to get the transcript.
- **Formatting**: The retrieved subtitles are formatted for readability.
- **Error Handling**: In case of errors while fetching the subtitles, it logs the error and throws a new `McpError`.

### 4. Formatting the Transcript

The final method formats the transcript into readable text:

```typescript
private formatTranscript(transcript: TranscriptLine[]): string {
  return transcript
    .map(line => line.text.trim()) // Trim whitespace from each line
    .filter(text => text.length > 0) // Remove empty lines
    .join(' '); // Join lines into a single string
}
```

#### Explanation:

- **Mapping and Filtering**: The method processes each line to clean it up and eliminate any unnecessary content.
- **Joining**: It combines the cleaned-up lines into a single string for easy consumption.

## Summary

The `YouTubeTranscriptExtractor` class is a crucial component of our project, designed to efficiently extract and format transcripts from YouTube videos. It encapsulates the logic for handling various input formats, error management, and data retrieval using an external library.

By understanding how the `YouTubeTranscriptExtractor` operates, we lay the groundwork for the next component of our server architecture.

Next, we will delve into the **TranscriptServer** class, which manages interactions between the extractor and the server itself. You can find this in the following chapter: [TranscriptServer](03_transcriptserver_.md).

---

Generated by [AI Codebase Knowledge Builder](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)
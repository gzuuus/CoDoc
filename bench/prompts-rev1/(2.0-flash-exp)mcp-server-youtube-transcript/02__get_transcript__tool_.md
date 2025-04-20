# Chapter 2: `get_transcript` Tool

The `get_transcript` tool is the core functionality of the `mcp-server-youtube-transcript` project. It provides a standardized way to extract transcripts from YouTube videos through the Model Context Protocol (MCP). This chapter will detail the tool's purpose, input parameters, and output structure.

The primary function of the `get_transcript` tool is to retrieve the transcript of a YouTube video, given its URL or ID, and an optional language code. It's designed to be called by the MCP server when a client requests a transcript. The tool handles the complexity of interacting with the YouTube transcript extraction library and formats the result into a standardized MCP response.

The tool's definition is part of the `TOOLS` constant, as shown in the previous chapter:

```typescript
const TOOLS: Tool[] = [
  {
    name: "get_transcript",
    description: "Extract transcript from a YouTube video URL or ID",
    inputSchema: {
      type: "object",
      properties: {
        url: {
          type: "string",
          description: "YouTube video URL or ID"
        },
        lang: {
          type: "string",
          description: "Language code for transcript (e.g., 'ko', 'en')",
          default: "en"
        }
      },
      required: ["url", "lang"]
    }
  }
];
```

Let's break down the `inputSchema`:

*   `type: "object"`: Indicates that the input is a JSON object.
*   `properties`: Defines the properties of the input object.
    *   `url`:
        *   `type: "string"`: The `url` property must be a string.
        *   `description`: Provides a human-readable description of the parameter.
    *   `lang`:
        *   `type: "string"`: The `lang` property (language code) must be a string.
        *   `description`:  Provides a human-readable description.
        *   `default: "en"`: If the `lang` parameter is not provided, it defaults to English ("en").
*   `required: ["url", "lang"]`: An array listing the required properties. The `url` property is required. Note that while `lang` is listed in the `properties`, the default value makes it effectively optional from a validation perspective.

When the MCP server receives a [`CallToolRequestSchema & ListToolsRequestSchema`](03_calltoolrequestschema___listtoolsrequestschema_.md) request to execute the `get_transcript` tool, it extracts the `url` and `lang` parameters from the request's `arguments`. The server then passes these parameters to the `handleToolCall` method.

```typescript
private async handleToolCall(name: string, args: any): Promise<{ toolResult: CallToolResult }> {
  switch (name) {
    case "get_transcript": {
      const { url: input, lang = "en" } = args;
      
      if (!input || typeof input !== 'string') {
        throw new McpError(
          ErrorCode.InvalidParams,
          'URL parameter is required and must be a string'
        );
      }

      if (lang && typeof lang !== 'string') {
        throw new McpError(
          ErrorCode.InvalidParams,
          'Language code must be a string'
        );
      }
      
      try {
        const videoId = this.extractor.extractYoutubeId(input);
        console.error(`Processing transcript for video: ${videoId}`);
        
        const transcript = await this.extractor.getTranscript(videoId, lang);
        console.error(`Successfully extracted transcript (${transcript.length} chars)`);
        
        return {
          toolResult: {
            content: [{
              type: "text",
              text: transcript,
              metadata: {
                videoId,
                language: lang,
                timestamp: new Date().toISOString(),
                charCount: transcript.length
              }
            }],
            isError: false
          }
        };
      } catch (error) {
        console.error('Transcript extraction failed:', error);
        
        if (error instanceof McpError) {
          throw error;
        }
        
        throw new McpError(
          ErrorCode.InternalError,
          `Failed to process transcript: ${(error as Error).message}`
        );
      }
    }

    default:
      throw new McpError(
        ErrorCode.MethodNotFound,
        `Unknown tool: ${name}`
      );
  }
}
```

Within the `handleToolCall` method:

1.  **Parameter Extraction and Validation:** The code extracts the `url` (renamed to `input`) and `lang` parameters from the `args` object. It then validates that the `url` is provided and is a string, and that the `lang` parameter (if present) is also a string. If validation fails, an `McpError` is thrown.
2.  **Video ID Extraction:** The `YouTubeTranscriptExtractor.extractYoutubeId()` method (explained in more detail in the [`YouTubeTranscriptExtractor`](04_youtubetranscriptextractor_.md) chapter) is called to extract the YouTube video ID from the provided URL or ID.
3.  **Transcript Retrieval:** The `YouTubeTranscriptExtractor.getTranscript()` method is called to retrieve the transcript for the specified video ID and language.
4.  **Result Formatting:** The extracted transcript is then formatted into a `CallToolResult` object, adhering to the MCP standard. The `CallToolResult` contains:
    *   `content`: An array of content objects. In this case, there is only one content object of `type: "text"` containing the `text` of the transcript.
    *   `metadata`: Metadata about the transcript extraction, including the video ID, language, timestamp, and character count.
    *   `isError`: A boolean indicating whether an error occurred during tool execution (set to `false` in this case, as the transcript was successfully extracted).
5.  **Error Handling:** The `try...catch` block handles any errors that occur during the transcript extraction process. If an error occurs, an appropriate `McpError` is thrown.

The output of the `get_transcript` tool is a `CallToolResult` object, which contains the extracted transcript and associated metadata. This object is then serialized and sent back to the client as the response to the `CallToolRequestSchema`.  The structure of `CallToolResult` is defined in the MCP specification.

## Summary

In this chapter, we examined the `get_transcript` tool in detail, covering its purpose, input parameters, and output structure. We learned how the tool retrieves transcripts from YouTube videos and formats them into a standardized MCP response. This tool is the heart of this server.

Next, we will explore the [`CallToolRequestSchema & ListToolsRequestSchema`](03_calltoolrequestschema___listtoolsrequestschema_.md) which define the structure of requests to the MCP server.


---

Generated by [AI Codebase Knowledge Builder](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)
# Chapter 1: Model Context Protocol (MCP) Server


This chapter introduces the Model Context Protocol (MCP) Server, the central component of the `mcp-server-youtube-transcript` project. This server is responsible for receiving requests, processing them, and returning results according to the MCP standard. Essentially, it acts as the interface between clients and the YouTube transcript extraction functionality.

The server performs several key tasks:

*   **Listens for incoming requests:**  It waits for requests from clients wanting to access the `get_transcript` tool or discover available tools.
*   **Validates requests:** It ensures that incoming requests adhere to predefined schemas, specifically the [`CallToolRequestSchema & ListToolsRequestSchema`](03_calltoolrequestschema___listtoolsrequestschema_.md), guaranteeing that requests are well-formed and contain the necessary information.
*   **Executes tools:**  Based on the request, it executes the appropriate tool. In this project, the main tool is [`get_transcript` Tool](02__get_transcript__tool_.md), which extracts transcripts from YouTube videos.
*   **Returns results:** It formats the results of tool execution into a standardized MCP response and sends it back to the client.
*   **Manages server lifecycle:**  It handles the starting and stopping of the server, as well as any errors that occur during operation.

Let's examine the code that defines the MCP server. The `TranscriptServer` class encapsulates all the server's logic.

```typescript
class TranscriptServer {
  private extractor: YouTubeTranscriptExtractor;
  private server: Server;

  constructor() {
    this.extractor = new YouTubeTranscriptExtractor();
    this.server = new Server(
      {
        name: "mcp-servers-youtube-transcript",
        version: "0.1.0",
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupHandlers();
    this.setupErrorHandling();
  }
```

The `TranscriptServer` class initializes the `YouTubeTranscriptExtractor` (responsible for the actual transcript extraction, described in more detail in the [`YouTubeTranscriptExtractor`](04_youtubetranscriptextractor_.md) chapter) and the MCP `Server` from the `@modelcontextprotocol/sdk`.  It also calls `setupHandlers` and `setupErrorHandling` to configure how the server responds to requests and deals with errors.  The `Server` constructor takes two arguments: the server's metadata (name and version) and its capabilities (in this case, the available tools).

Next, let's explore the `setupHandlers` method, which defines the server's behavior when it receives different types of requests.

```typescript
private setupHandlers(): void {
  // List available tools
  this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOLS
  }));

  // Handle tool calls
  this.server.setRequestHandler(CallToolRequestSchema, async (request) => 
    this.handleToolCall(request.params.name, request.params.arguments ?? {})
  );
}
```

This method uses `server.setRequestHandler` to register handlers for two types of requests, defined by the schemas [`ListToolsRequestSchema`](03_calltoolrequestschema___listtoolsrequestschema_.md) and [`CallToolRequestSchema`](03_calltoolrequestschema___listtoolsrequestschema_.md).

*   When the server receives a request matching `ListToolsRequestSchema`, it responds with a list of available tools (`TOOLS`).  The `TOOLS` constant is defined as follows:

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

This defines a single tool, `get_transcript`, which requires a `url` and accepts an optional `lang` parameter. The structure of the `Tool` interface is specified in the MCP specification.

*   When the server receives a request matching `CallToolRequestSchema`, it calls the `handleToolCall` method to process the request.

The `handleToolCall` method is responsible for executing the requested tool.

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

This method extracts the arguments from the request, validates them, calls the `YouTubeTranscriptExtractor` to retrieve the transcript, and formats the result into a `CallToolResult`. This `CallToolResult` is then returned to the client. Error handling is also present. If an error occurs during transcript extraction, an `McpError` is thrown, containing an error code and a message. For details on error types, see the [`McpError`](07_mcperror_.md) chapter. The `CallToolResult` contains the extracted transcript and metadata about the extraction process.  The transcript itself conforms to the `TranscriptLine` interface, which is detailed in the [`TranscriptLine Interface`](05_transcriptline_interface_.md) chapter.

The `setupErrorHandling` method configures global error handling for the server:

```typescript
private setupErrorHandling(): void {
  this.server.onerror = (error) => {
    console.error("[MCP Error]", error);
  };

  process.on('SIGINT', async () => {
    await this.stop();
    process.exit(0);
  });
}
```

This method sets up a handler for the server's `onerror` event, which logs any errors that occur during request processing. It also sets up a handler for the `SIGINT` signal (usually triggered by pressing Ctrl+C), which gracefully stops the server before exiting.

Finally, the `start` and `stop` methods handle the server's lifecycle:

```typescript
  async start(): Promise<void> {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
  }

  async stop(): Promise<void> {
    try {
      await this.server.close();
    } catch (error) {
      console.error('Error while stopping server:', error);
    }
  }
```

The `start` method creates a `StdioServerTransport` and connects it to the server.  The `StdioServerTransport` is explained further in the [`StdioServerTransport`](06_stdioservertransport_.md) chapter. The `stop` method closes the server connection, allowing the server to shut down gracefully.

## Summary

In this chapter, we introduced the Model Context Protocol (MCP) Server in the `mcp-server-youtube-transcript` project. We discussed its role in handling requests, validating them, executing tools, and returning results. We also examined the key components of the `TranscriptServer` class, including the request handlers, error handling, and lifecycle management.

Next, we'll delve into the [`get_transcript` Tool](02__get_transcript__tool_.md) and explore how it extracts transcripts from YouTube videos.

---

Generated by [AI Codebase Knowledge Builder](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)
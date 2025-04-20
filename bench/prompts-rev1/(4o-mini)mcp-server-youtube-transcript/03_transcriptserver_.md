# Chapter 3: TranscriptServer

In this chapter, we will delve into the `TranscriptServer` class, which acts as the main interface for handling transcript extraction requests in our `mcp-server-youtube-transcript` project. Think of it as the server in a restaurant that takes orders (transcript requests) and serves them to the customers.

## What is TranscriptServer?

The `TranscriptServer` class sets up a server that listens for incoming requests related to transcript extraction, processes these requests, and sends back the appropriate responses. It uses the `YouTubeTranscriptExtractor` to perform the actual retrieval of transcripts based on user input.

### Key Responsibilities

1. **Handling Requests**: It listens for requests to fetch transcripts from YouTube videos.
2. **Processing Commands**: It interacts with the `YouTubeTranscriptExtractor` class to fulfill these requests.
3. **Responding to Clients**: Once a transcript is retrieved, it sends the response back to the client.

## Structure of the TranscriptServer Class

### 1. Constructor

The constructor initializes the server and handles setup procedures.

```typescript
class TranscriptServer {
  private extractor: YouTubeTranscriptExtractor; // Extractor for handling transcripts
  private server: Server; // Server to manage requests

  constructor() {
    this.extractor = new YouTubeTranscriptExtractor(); // Create an instance of the extractor
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

    this.setupHandlers(); // Set up request handlers
    this.setupErrorHandling(); // Set up error handling
  }
}
```

#### Explanation:

- **Extractor Instance**: A new instance of `YouTubeTranscriptExtractor` is created to perform transcript operations.
- **Server Initialization**: The server is created with information about its name and version.
- **Setup Functions**: It calls functions to set up handlers for requests and to manage errors.

### 2. Setting Up Handlers

The server needs to know how to react to incoming requests. This is handled in the `setupHandlers` method.

```typescript
private setupHandlers(): void {
  // List available tools
  this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOLS // Returns the available tools
  }));

  // Handle tool calls
  this.server.setRequestHandler(CallToolRequestSchema, async (request) => 
    this.handleToolCall(request.params.name, request.params.arguments ?? {})
  );
}
```

#### Explanation:

- **Tool Listing**: The server responds to requests asking for a list of available tools (`ListToolsRequestSchema`).
- **Tool Call Handling**: It processes requests to call specific tools (`CallToolRequestSchema`) by delegating to `handleToolCall`.

### 3. Handling Tool Calls

The `handleToolCall` function is responsible for processing requests to extract transcripts.

```typescript
private async handleToolCall(name: string, args: any): Promise<{ toolResult: CallToolResult }> {
  switch (name) {
    case "get_transcript": {
      const { url: input, lang = "en" } = args; // Get URL and language from arguments
      
      // Validate input
      if (!input || typeof input !== 'string') {
        throw new McpError(ErrorCode.InvalidParams, 'URL parameter is required and must be a string');
      }

      if (lang && typeof lang !== 'string') {
        throw new McpError(ErrorCode.InvalidParams, 'Language code must be a string');
      }
      
      try {
        const videoId = this.extractor.extractYoutubeId(input); // Extract video ID
        const transcript = await this.extractor.getTranscript(videoId, lang); // Fetch the transcript
        return {
          toolResult: {
            content: [{
              type: "text",
              text: transcript, // The transcript text
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
        // Handle errors
        throw new McpError(ErrorCode.InternalError, `Failed to process transcript: ${(error as Error).message}`);
      }
    }

    default:
      throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`); // Handle unknown tool calls
  }
}
```

#### Explanation:

- **Input Extraction**: It extracts the URL and language parameters from the incoming request.
- **Validation**: Checks if the provided input is valid.
- **Transcript Retrieval**: Calls methods in the `YouTubeTranscriptExtractor` to fetch the transcript.
- **Response Formation**: Prepares the response with the transcript and additional metadata.

### 4. Setting Up Error Handling

Proper error handling is crucial for server stability.

```typescript
private setupErrorHandling(): void {
  this.server.onerror = (error) => {
    console.error("[MCP Error]", error); // Log server errors
  };

  process.on('SIGINT', async () => {
    await this.stop(); // Graceful shutdown
    process.exit(0);
  });
}
```

#### Explanation:

- **Error Logging**: Logs any server errors that occur.
- **Graceful Shutdown**: When the server is interrupted, it ensures that it stops gracefully.

## Summary

The `TranscriptServer` class is the core interface for our transcript extraction service. It orchestrates requests and interactions with the `YouTubeTranscriptExtractor`, ensuring that users can seamlessly retrieve transcripts from YouTube videos. 

Understanding how the `TranscriptServer` operates is key as we progress to more advanced topics, such as initializing the server and handling asynchronous requests. 

Next, we will explore server initialization, detailing how to get our server up and running. For more information, move on to the next chapter: [Server Initialization](04_server_initialization_.md).

---

Generated by [AI Codebase Knowledge Builder](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)
# Chapter 7: MCP Error Handling (`McpError`, `onerror`)

Welcome to the final chapter of our tutorial! We've journeyed through the entire structure of the `mcp-server-youtube-transcript` project: the main application ([`TranscriptServer`](01_transcript_server_application___transcriptserver__class__.md)), defining tools ([`TOOLS`](02_mcp_tool_definition___tools__constant__.md)), handling requests ([`setRequestHandler`, `handleToolCall`](03_request_handling___setrequesthandler____handletoolcall___.md)), the core transcript logic ([`YouTubeTranscriptExtractor`](04_youtube_transcript_extractor___youtubetranscriptextractor__class__.md)), the underlying MCP engine ([`Server`](05_mcp_server___server__class__.md)), and the communication channel ([`StdioServerTransport`](06_stdio_transport___stdioservertransport__.md)).

No application is perfect, and things can go wrong. A user might provide an invalid URL, the YouTube service might be temporarily unavailable, or there could be unexpected issues within the server itself. This chapter focuses on how our server handles these errors in a way that is consistent with the Model Context Protocol (MCP).

## Why Standardized Errors Matter in MCP

Imagine calling a customer support line. If something goes wrong, getting a specific message like "Invalid account number" is much more helpful than a vague "Error occurred."

MCP aims for similar clarity in communication between software components. When a server encounters an error while processing a client's request, it shouldn't just fail silently or send back a generic error. MCP defines a standard way to report errors so that the client application can understand:

1.  *That* an error occurred.
2.  *What kind* of error it was (e.g., bad input, internal problem).
3.  A descriptive message about the error.

This allows clients to potentially retry the request, inform the user appropriately, or take other automated actions based on the specific error type.

## `McpError`: The Standard MCP Error Object

The MCP SDK provides a specific class for representing errors: `McpError`. This class is designed to be thrown by server-side logic (like our request handlers) when something goes wrong during the processing of a client request.

The `McpError` class typically takes two main arguments:

1.  **`code`**: A standardized error code, usually selected from the `ErrorCode` enum provided by the MCP SDK (`@modelcontextprotocol/sdk/types.js`). This provides a machine-readable classification of the error.
2.  **`message`**: A human-readable string describing the specific error details.

Let's look at how we used `McpError` in our code:

**Example 1: Input Validation Error in `handleToolCall`**

```typescript
// src/index.ts (within handleToolCall)

        // Extract and Validate Arguments
        const { url: input, lang = "en" } = args; 
        
        // Basic validation
        if (!input || typeof input !== 'string') {
          // Throw a specific error if validation fails
          throw new McpError(
            ErrorCode.InvalidParams, // Standard code for bad client input
            'URL parameter is required and must be a string' // Descriptive message
          );
        }
        // ... other validation ...
```

**Explanation:**

*   If the client sends a `CallToolRequest` without a valid `url` argument, we immediately `throw` a `new McpError`.
*   `ErrorCode.InvalidParams`: This clearly signals to the client that the problem lies within the parameters *they* provided.
*   The accompanying message gives specific details.

**Example 2: Tool Not Found Error in `handleToolCall`**

```typescript
// src/index.ts (within handleToolCall)

      // Handle cases where the requested tool name is not known
      default:
        throw new McpError(
          ErrorCode.MethodNotFound, // Standard code for unknown method/tool
          `Unknown tool: ${name}`   // Specific detail
        );
```

**Explanation:**

*   If the client asks to run a tool (e.g., "get\_weather") that our server doesn't support, the `switch` statement hits the `default` case.
*   `ErrorCode.MethodNotFound`: This tells the client the requested operation doesn't exist on this server.

**Example 3: Internal Processing Error in `getTranscript`**

```typescript
// src/index.ts (within YouTubeTranscriptExtractor.getTranscript)

    } catch (error) {
      // Handle errors from the external library 
      console.error('Failed to fetch transcript:', error);
      // Wrap the original error in an McpError
      throw new McpError(
        ErrorCode.InternalError, // Standard code for server-side issues
        `Failed to retrieve transcript for video ${videoId} (${lang}): ${(error as Error).message}`
      );
    }
```

**Explanation:**

*   If the `youtube-captions-scraper` library fails (e.g., YouTube returns an error, network issue), the `catch` block executes.
*   `ErrorCode.InternalError`: We use this code because the problem isn't with the client's request parameters *per se*, but with the server's ability to fulfill the request due to an internal or external dependency issue.
*   The message includes context and the original error message from the underlying library.

When a request handler (like the one registered with `setRequestHandler(CallToolRequestSchema, ...)` in [Chapter 3](03_request_handling___setrequesthandler____handletoolcall___.md)) throws an `McpError`, the MCP `Server` engine catches it automatically. Instead of sending back a normal response, the engine constructs a standard MCP error response containing the `code` and `message` from the `McpError` and sends *that* back to the client via the transport layer.

## Handling Errors During Tool Execution (`try...catch`)

In our `handleToolCall` method, we wrap the core logic for the `get_transcript` tool in a `try...catch` block. This is crucial for robust error handling during the actual execution phase.

```typescript
// src/index.ts (within handleToolCall, inside the "get_transcript" case)

        // 2. Execute the Core Logic 
        try {
          const videoId = this.extractor.extractYoutubeId(input);
          // ... (potentially throwing McpError if ID extraction fails) ...
          
          const transcript = await this.extractor.getTranscript(videoId, lang);
          // ... (potentially throwing McpError if transcript fetch fails) ...
          
          // 3. Format the Successful Result
          return { /* ... success object ... */ };

        } catch (error) {
          // 4. Handle Errors during Extraction/Processing
          console.error('Transcript extraction failed:', error); // Log server-side
          
          // If it's already an McpError (e.g., from extractYoutubeId or getTranscript), re-throw it
          if (error instanceof McpError) {
            throw error; // The MCP Server will catch this and send it to the client
          }
          
          // Otherwise, wrap it in a generic InternalError McpError
          throw new McpError(
            ErrorCode.InternalError,
            `Failed to process transcript: ${(error as Error).message}`
          );
        }
```

**Explanation:**

1.  **`try { ... }`**: Contains the main steps: extracting the video ID and getting the transcript. These steps might throw errors (often `McpError`s, as we saw).
2.  **`catch (error) { ... }`**: This block executes if any error occurs within the `try` block.
3.  **`console.error(...)`**: We first log the error to the server's console (`stderr`) for debugging purposes. This log is not sent to the client.
4.  **`if (error instanceof McpError)`**: We check if the caught error is *already* an `McpError`. This could happen if `extractYoutubeId` or `getTranscript` threw one (e.g., `InvalidParams` or `InternalError`). If it is, we simply `throw error` again. The MCP `Server` is expecting this and will handle sending the appropriate error response to the client.
5.  **`else { throw new McpError(...) }`**: If the caught error is *not* an `McpError` (it might be a more generic JavaScript `Error` from an unexpected place), we wrap it. We create a *new* `McpError` with `ErrorCode.InternalError` and include the original error's message. This ensures that even unexpected errors are reported back to the client in the standard MCP format, rather than causing the server to crash or send a non-standard response.

## Handling Low-Level Errors: `server.onerror`

`McpError` is perfect for errors related to specific client requests handled by our logic. But what about errors that happen at a lower level, within the MCP `Server` engine itself or the transport layer (`StdioServerTransport`)? Examples could include:

*   Receiving a completely garbled message from the client that doesn't conform to the MCP protocol structure.
*   An issue writing data to `stdout` because the client process closed the connection unexpectedly.

The MCP `Server` class provides a hook for these situations: the `onerror` property. We can assign a function to this property, and the `Server` engine will call it if it encounters an error *outside* the normal request-handler execution flow.

```typescript
// src/index.ts (within TranscriptServer class)

  private setupErrorHandling(): void {
    // Assign an error handler function to the MCP Server instance's 'onerror' property
    this.server.onerror = (error) => {
      // This function gets called for low-level errors in the MCP engine or transport
      console.error("[MCP Error]", error); // Log these errors to the server console (stderr)
    };

    // Optional: Handling OS signals like Ctrl+C gracefully
    process.on('SIGINT', async () => {
      console.error("Received SIGINT. Shutting down...");
      await this.stop(); // Ensure polite shutdown
      process.exit(0); // Exit the process
    });
  }
```

**Explanation:**

*   `this.server.onerror = (error) => { ... };`: We assign a simple function to the `onerror` property of our `server` instance (the MCP `Server` engine).
*   `console.error("[MCP Error]", error);`: Inside this handler function, we simply log the error object to the server's standard error stream (`stderr`). This makes these low-level issues visible to the person running or monitoring the server.
*   **Important Distinction**: Errors caught by `onerror` are typically *not* automatically sent back to the client as structured MCP error responses. They represent problems with the communication channel or the protocol engine itself, rather than a failure to process a specific, valid request. Our configured handler just logs them server-side.

```mermaid
graph TD
    subgraph "Error Handling Scenarios"
        direction LR

        subgraph "Handler Error (e.g., InvalidParams)"
            ClientRequest --> Handler[Request Handler Logic (handleToolCall)]
            Handler -->|Throws McpError| MCPServer[MCP Server Engine]
            MCPServer -->|Formats Standard Error| Transport[Stdio Transport]
            Transport --> ClientResponse[Client Receives MCP Error Response]
        end

        subgraph "Low-Level Error (e.g., Malformed Message)"
            ClientBadData --> TransportIn[Stdio Transport (stdin)]
            TransportIn -->|Invalid Data| MCPServerEngine[MCP Server Engine]
            MCPServerEngine -->|Invokes onerror| OnErrorHandler[server.onerror Handler (Our Code)]
            OnErrorHandler -->|Logs Error| ServerConsole[Server Console (stderr)]
            %% Note: Usually no direct error response sent back to client for this type %%
        end
    end

    style Handler fill:#ccf,stroke:#333,stroke-width:1px
    style MCPServer fill:#f9f,stroke:#333,stroke-width:1px
    style MCPServerEngine fill:#f9f,stroke:#333,stroke-width:1px
    style OnErrorHandler fill:#ccf,stroke:#333,stroke-width:1px
```
*Diagram: Contrasting how `McpError` from handlers and `onerror` callbacks are typically processed.*

## Summary

Robust error handling is essential for reliable communication. MCP provides a standardized approach:

*   The **`McpError` class** is used within request handling logic (`handleToolCall`, `YouTubeTranscriptExtractor`) to represent errors related to specific client requests. It uses standard `ErrorCode` values (`InvalidParams`, `InternalError`, `MethodNotFound`) and descriptive messages.
*   Throwing an `McpError` from a request handler results in the MCP `Server` engine sending a **standardized MCP error response** back to the client.
*   **`try...catch` blocks** are used within handlers to catch both expected `McpError`s and unexpected internal errors, ensuring all failures are converted to `McpError`s before being thrown back to the engine.
*   The **`server.onerror` handler** is configured on the MCP `Server` instance to catch lower-level errors occurring within the protocol engine or transport layer. These are typically logged server-side for diagnostics.

By leveraging `McpError` and the `onerror` hook, our `mcp-server-youtube-transcript` ensures that errors are handled gracefully and communicated clearly, adhering to the principles of the Model Context Protocol.

This concludes our tutorial on the `mcp-server-youtube-transcript` project. We hope this step-by-step exploration has provided a clear understanding of how to build a functional MCP tool server, from application structure and request handling to specific implementation details and error management. You can now explore the code further, experiment with modifications, or delve deeper into the Model Context Protocol SDK documentation. Happy coding!

---

Generated by [AI Codebase Knowledge Builder](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)
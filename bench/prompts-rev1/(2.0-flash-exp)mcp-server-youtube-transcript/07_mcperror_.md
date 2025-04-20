# Chapter 7: McpError

This chapter focuses on the `McpError` class, a custom error class used within the `mcp-server-youtube-transcript` project for consistent error handling. It's crucial for understanding how errors are structured and propagated throughout the application. The `McpError` class extends the standard JavaScript `Error` class, providing additional information about the error, such as a specific error code. This error code allows client applications to easily identify the type of error and handle it appropriately.

The `McpError` class is defined in the `@modelcontextprotocol/sdk/types.js` module. Let's examine its structure:

```typescript
class McpError extends Error {
  code: ErrorCode;

  constructor(code: ErrorCode, message: string) {
    super(message);
    this.code = code;
    this.name = "McpError"; // Optional: Setting the error name
    Object.setPrototypeOf(this, McpError.prototype); // Required for custom errors in some environments
  }
}
```

Here's a breakdown of the `McpError` class:

*   `extends Error`: This indicates that `McpError` inherits from the built-in `Error` class in JavaScript. This inheritance provides the basic error handling capabilities, such as the `message` property and the stack trace.
*   `code: ErrorCode`: This property stores the specific error code associated with the error. The `ErrorCode` is an enumeration (or a set of predefined constants) that represents the different types of errors that can occur in the application.
*   `constructor(code: ErrorCode, message: string)`: The constructor of the `McpError` class takes two arguments: the error code and the error message. It calls the constructor of the parent `Error` class with the error message, sets the `code` property to the provided error code, sets the `name` property to "McpError", and sets the prototype.  Setting the prototype correctly is important for `instanceof` checks to work correctly, especially in older JavaScript environments.

The `ErrorCode` enumeration defines the possible error codes that can be used in the `McpError` class. Here are some common error codes defined in `@modelcontextprotocol/sdk/types.js`:

```typescript
export enum ErrorCode {
  ParseError = -32700,
  InvalidRequest = -32600,
  MethodNotFound = -32601,
  InvalidParams = -32602,
  InternalError = -32603,
  ServerError = -32000,
}
```

Let's break down the `ErrorCode` enum:

*   `ParseError`: Indicates that the server failed to parse the request. This usually happens when the request is not a valid JSON string.
*   `InvalidRequest`: Indicates that the request is not a valid MCP request. This can happen if the request is missing required fields or if the fields have invalid values.
*   `MethodNotFound`: Indicates that the requested method (tool) does not exist on the server. This happens when the client tries to call a tool that is not defined in the `TOOLS` constant (introduced in the [`Model Context Protocol (MCP) Server`](01_model_context_protocol__mcp__server_.md) chapter).
*   `InvalidParams`: Indicates that the parameters passed to the method (tool) are invalid. This can happen if the parameters are missing, have the wrong type, or are outside the allowed range.
*   `InternalError`: Indicates that an unexpected error occurred on the server. This is a general error code that should be used when no other more specific error code applies.
*   `ServerError`: Indicates a server-defined error.

Here are some examples of how `McpError` is used in the `mcp-server-youtube-transcript` project:

```typescript
if (!input || typeof input !== 'string') {
  throw new McpError(
    ErrorCode.InvalidParams,
    'URL parameter is required and must be a string'
  );
}
```

This code snippet (from the [`get_transcript` Tool](02__get_transcript__tool_.md) chapter) checks if the `url` parameter is provided and is a string. If not, it throws an `McpError` with the `ErrorCode.InvalidParams` code and a descriptive error message.

```typescript
throw new McpError(
  ErrorCode.MethodNotFound,
  `Unknown tool: ${name}`
);
```

This code snippet (also from the [`get_transcript` Tool](02__get_transcript__tool_.md) chapter) is used when the server receives a request to call a tool that does not exist. It throws an `McpError` with the `ErrorCode.MethodNotFound` code and a message indicating the unknown tool name.

When an `McpError` is thrown, the MCP server catches it and formats it into a standardized error response, which is then sent back to the client. The client can then inspect the error code and message to determine the cause of the error and take appropriate action.

## Summary

In this chapter, we explored the `McpError` class, a custom error class used within the `mcp-server-youtube-transcript` project for consistent error handling. We learned how it extends the standard `Error` class, providing additional information about the error, such as a specific error code. We also examined the different error codes defined in the `ErrorCode` enumeration and saw examples of how `McpError` is used in the project. Understanding `McpError` and its associated error codes is crucial for building robust and reliable MCP applications.

This concludes the tutorial for the `mcp-server-youtube-transcript` project. You now have a solid understanding of all the key components, from the MCP server to the `YouTubeTranscriptExtractor`, the request and response schemas, and the error handling mechanisms.


---

Generated by [AI Codebase Knowledge Builder](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)
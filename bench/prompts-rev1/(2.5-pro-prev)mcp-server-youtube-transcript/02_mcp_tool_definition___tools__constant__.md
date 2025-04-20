# Chapter 2: MCP Tool Definition (`TOOLS` constant)


Welcome to Chapter 2! In the [previous chapter](01_transcript_server_application___transcriptserver__class__.md), we learned about the `TranscriptServer` class, the main orchestrator of our application. We saw that it sets up the server's basic information and capabilities. Now, let's dive into *how* we precisely define those capabilities.

Imagine you walk into a store. How do you know what services they offer? Usually, there's a sign or a service list. In the world of software and protocols like the Model Context Protocol (MCP), we need a similar, standardized way for a server (our transcript service) to tell a client (any application wanting a transcript) exactly what it can do. This is where the `TOOLS` constant comes in.

## What is the `TOOLS` Constant?

The `TOOLS` constant is a data structure, specifically an array, defined in our project (`src/index.ts`). It formally lists and describes each "tool" or function that our server provides according to the MCP specification. For our server, the main tool is the ability to get a YouTube transcript.

Think of `TOOLS` as the official service menu for our transcript server. It lists the available services (`get_transcript`), what they do, and what information (`url`, `lang`) you need to provide to use them.

## Anatomy of a Tool Definition

Let's look at the `TOOLS` constant defined in `src/index.ts`:

```typescript
// src/index.ts (snippet)

import { Tool } from "@modelcontextprotocol/sdk/types.js";

// Define tool configurations
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
      required: ["url", "lang"] // Note: While 'lang' has a default, MCP requires definition here if always needed. Actual enforcement can vary.
    }
  }
];
```

**Explanation:**

1.  **`const TOOLS: Tool[] = [...]`**: This declares a constant variable named `TOOLS`. The `: Tool[]` part is TypeScript syntax indicating that `TOOLS` is expected to be an array (`[]`) where each item in the array is of type `Tool` (imported from the MCP SDK).
2.  **`[...]`**: The square brackets define the array. Currently, it contains just one element, representing our single tool.
3.  **`{ ... }`**: This object defines one specific tool. Let's break down its properties:
    *   **`name: "get_transcript"`**: This is the unique machine-readable identifier for the tool. When a client wants to use this specific function, it will refer to it by this name.
    *   **`description: "Extract transcript..."`**: This provides a human-readable explanation of what the tool does. This helps developers (and potentially end-users) understand the tool's purpose.
    *   **`inputSchema: { ... }`**: This is arguably the most important part for automation. It defines the *structure and rules* for the input data (arguments) that must be provided when calling this tool. It uses a format called **JSON Schema**.

## Dissecting the `inputSchema` (JSON Schema)

JSON Schema is a standard way to describe the structure and constraints of JSON data. Think of it like a blueprint for the expected input. Our `inputSchema` tells clients exactly what parameters are needed for the `get_transcript` tool:

```json
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "description": "YouTube video URL or ID"
    },
    "lang": {
      "type": "string",
      "description": "Language code for transcript (e.g., 'ko', 'en')",
      "default": "en"
    }
  },
  "required": ["url", "lang"]
}
```

*   **`"type": "object"`**: This specifies that the input parameters should be provided as a JSON object (a collection of key-value pairs, like `{ "url": "...", "lang": "..." }`).
*   **`"properties": { ... }`**: This defines the individual parameters (keys) expected within that input object.
    *   **`"url": { ... }`**: Defines the `url` parameter.
        *   `"type": "string"`: The value provided for `url` must be a string (text).
        *   `"description": "..."`: A description explaining this specific parameter.
    *   **`"lang": { ... }`**: Defines the `lang` parameter.
        *   `"type": "string"`: The value for `lang` must also be a string.
        *   `"description": "..."`: Explains the language code.
        *   `"default": "en"`: Specifies a default value. If the client doesn't provide `lang`, it will default to English (`"en"`). Note that the actual implementation logic needs to handle applying this default.
*   **`"required": ["url", "lang"]`**: This lists the parameters that *must* be provided by the client. Even though `lang` has a default, listing it here signifies that it's a conceptually required part of the tool's input structure as defined by this schema. A client should ideally always provide it, but the server logic can apply the default if it's missing.

```mermaid
graph LR
    A[Input Arguments] -- must be an --> B(Object);
    B -- must have properties --> C{url};
    B -- must have properties --> D{lang};
    C -- must be a --> E[String];
    C -- description --> F["YouTube URL or ID"];
    D -- must be a --> G[String];
    D -- description --> H["Language code (e.g., 'en')"];
    D -- can default to --> I["en"];
    B -- required properties --> J(["url", "lang"]);

    style B fill:#f9f,stroke:#333,stroke-width:2px
    style E fill:#ccf,stroke:#333,stroke-width:1px
    style G fill:#ccf,stroke:#333,stroke-width:1px
    style J fill:#lightgrey,stroke:#333,stroke-width:1px
```
*Diagram: Visual breakdown of the inputSchema requirements.*

## Why Define Tools This Way?

Defining tools using this structured format provides several benefits:

1.  **Discoverability:** Clients can ask the server "What tools do you have?" (using an MCP `ListTools` request). The server responds with the data from the `TOOLS` constant. This allows clients to automatically discover the server's capabilities without needing prior knowledge.
2.  **Clear Contract:** The `inputSchema` acts as a contract. It clearly defines what input the server expects. Clients know exactly how to format their requests.
3.  **Validation:** The schema allows for automatic validation of incoming requests. The server (or the MCP SDK) can check if the client provided the required parameters and if they have the correct types *before* even running the tool's logic.
4.  **Interoperability:** By adhering to the MCP standard for tool definition, our server can be understood and used by any MCP-compatible client.

## Connection to `TranscriptServer`

In [Chapter 1](01_transcript_server_application___transcriptserver__class__.md), we saw the `TranscriptServer` setting up request handlers. One of those handlers specifically responds to the `ListToolsRequestSchema`. When the server receives such a request, its response will contain the contents of this `TOOLS` constant.

```typescript
// src/index.ts (within TranscriptServer.setupHandlers)

    // List available tools
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: TOOLS // <-- Here's where TOOLS is used!
    }));
```

This connects the formal definition in `TOOLS` to the actual behavior of the server when asked about its capabilities.

## Summary

The `TOOLS` constant is a fundamental part of our MCP server. It's an array containing structured definitions for each capability (tool) the server offers. Each tool definition includes its `name`, `description`, and a detailed `inputSchema` (using JSON Schema) that specifies required parameters, their types, and descriptions. This formal definition enables discoverability, clear communication, validation, and interoperability within the MCP ecosystem. It acts as the server's public "service menu".

Now that we know how the server *describes* its tools, let's move on to see how it actually *handles* requests to *use* those tools.

**Next:** [Chapter 3: Request Handling (`setRequestHandler`, `handleToolCall`)](03_request_handling___setrequesthandler____handletoolcall___.md)

---

Generated by [AI Codebase Knowledge Builder](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)
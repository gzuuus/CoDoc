# Chapter 1: MCP Tool Definition

## Introduction

The Model Context Protocol (MCP) framework provides a standardized way for AI models to interact with external tools and services. At the heart of this framework lies the concept of **Tool Definitions** - the structured specifications that establish what tools are available and how they can be used.

In this chapter, we'll explore what MCP Tool Definitions are, how they're structured, and why they're crucial for building reliable AI tool integrations like our YouTube transcript extractor.

## What is an MCP Tool Definition?

An MCP Tool Definition is a configuration object that serves as a contract between an MCP server (which provides functionality) and clients (typically AI models or applications that want to use that functionality). Each definition specifies:

1. What the tool does
2. What parameters it accepts
3. What constraints those parameters have

Think of a tool definition as a detailed instruction manual that tells AI models exactly how to use a particular capability.

## Anatomy of a Tool Definition

Let's examine the structure of an MCP Tool Definition by looking at our project's tool definition:

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

This tool definition consists of three key components:

### 1. Name

The `name` field provides a unique identifier for the tool. In our example, we're using `"get_transcript"` as the tool name. Clients will use this name to specify which tool they want to invoke.

### 2. Description

The `description` field provides a human-readable explanation of what the tool does. This helps users understand the tool's purpose and functionality. Our tool's description clearly states that it extracts transcripts from YouTube videos.

### 3. Input Schema

The `inputSchema` defines the expected structure of the input parameters using JSON Schema. This is the most complex part of a tool definition and includes:

- The type of the input (typically an object)
- The properties that can be provided
- Descriptions for each property
- Default values (optional)
- Required properties

In our example, the input schema specifies two parameters:
- `url`: A string containing a YouTube video URL or ID (required)
- `lang`: A language code string, defaulting to "en" for English

## JSON Schema for Input Validation

MCP uses JSON Schema as the standard for defining input parameters. JSON Schema is a powerful vocabulary that allows you to validate, document, and interact with JSON data structures.

Here's a breakdown of how our schema works:

```typescript
inputSchema: {
  type: "object",                // Input must be a JSON object
  properties: {
    url: {
      type: "string",            // The url parameter must be a string
      description: "YouTube video URL or ID"
    },
    lang: {
      type: "string",            // The lang parameter must be a string
      description: "Language code for transcript (e.g., 'ko', 'en')",
      default: "en"              // If not provided, use "en"
    }
  },
  required: ["url", "lang"]      // Both parameters are required
}
```

The schema ensures that:
1. Clients must provide a valid object with the correct parameters
2. The parameters must be of the correct types
3. Required parameters cannot be omitted

## Tool Definition Arrays

In MCP, tools are typically organized in arrays, allowing servers to offer multiple capabilities:

```typescript
const TOOLS: Tool[] = [
  // First tool
  {
    name: "get_transcript",
    // ...tool definition...
  },
  // You could add more tools here
];
```

While our example has only one tool, the array structure allows for easy expansion. For instance, we might later add tools like:
- `get_video_metadata`
- `extract_video_subtitles`
- `translate_transcript`

## How Tool Definitions Are Used

When an MCP server starts, it registers its tool definitions. Clients can then:

1. **Discover tools**: Query the server to list available tools and their specifications
2. **Validate requests**: Ensure parameters meet the requirements before sending a request
3. **Make informed calls**: Use the descriptions to understand how to use each tool properly

In our project, the tools are registered with the server in the `TranscriptServer` class:

```typescript
this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS
}));
```

This handler responds to "list tools" requests by returning our defined tools.

## The Importance of Well-Designed Tool Definitions

Creating clear and comprehensive tool definitions is crucial for several reasons:

1. **Discoverability**: AI models can automatically discover what your tool can do
2. **Self-documentation**: The schema documents how to use your tool correctly
3. **Validation**: The server can automatically validate incoming requests
4. **Error prevention**: Clear definitions reduce the chance of runtime errors

## Example: Calling Our Tool

When a client wants to use our `get_transcript` tool, they would send a request like:

```json
{
  "name": "get_transcript",
  "arguments": {
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "lang": "en"
  }
}
```

The MCP server would validate this against our tool definition to ensure:
- All required fields are present
- All fields have the correct types
- Any additional constraints are met

Only then would it proceed to extract the transcript.

## Summary

MCP Tool Definitions are essential configuration objects that define the contract between MCP servers and clients. They specify:

- What tools are available (through the `name` field)
- What each tool does (through the `description` field)
- What input parameters are expected (through the `inputSchema` field)

By creating clear and comprehensive tool definitions, we enable AI models to discover, understand, and correctly use our tools.

In the next chapter, we'll explore the [TranscriptServer](02_transcriptserver_.md) class, which implements the server-side logic for handling tool requests and manages the overall MCP communication process.

---

Generated by [AI Codebase Knowledge Builder](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)
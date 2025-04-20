<h1 align="center">Turns Codebase into Easy Tutorial with AI</h1>

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

> **This is a fork of [`The-Pocket/Tutorial-Codebase-Knowledge`](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)**
>
> Use it with any OpenAI-compatible model provider by simply changing your API endpoint and model—no code changes required!

## 🆕 What's Different in This Fork?

- **OpenAI-Compatible API Focus:**
  - Easily configure your own API endpoint and model (OpenAI, Azure, local, etc.).
  - No vendor lock-in, use any model that implements the OpenAI API.
- **Prompting:**
  - We are exploring different prompt strategies to generate better tutorials.
- **Benchmarking:**
  - We are benchmarking different models and prompts.
  - See the [`bench/`](./bench/) directory for results.

---

## 🚀 Getting Started
We are using `uv` as the package manager and virtual environment manager, but you can just use `python`, `pip` and `venv` if you prefer.

1. **Clone this repository**

Optionally create a virtual environment using `uv venv` and activate it

2. **Install dependencies:**
   ```bash
   uv pip install -r requirements.txt
   ```

3. **Set up your LLM provider**
   Edit [`utils/call_llm.py`](./utils/call_llm.py) or set the following environment variables:
     ```
     OPENAI_API_KEY=your_api_key
     OPENAI_API_BASE=your_api_base
     OPENAI_MODEL=your_model
     ```

4. **Generate a codebase tutorial:**
   ```bash
   # Analyze a GitHub repository
   uv run main.py --repo https://github.com/username/repo

   # You can also specify additional options:
   uv run main.py --repo https://github.com/username/repo --include "*.py" "*.js" --exclude "tests/*" --max-size 50000

   # Or, analyze a local directory
   uv run main.py --dir /path/to/your/codebase --include "*.py" --exclude "*test*"

   # Or, generate a tutorial in Chinese
   uv run main.py --repo https://github.com/username/repo --language "Chinese"
   ```

   - `--repo` or `--dir`: Specify either a GitHub repo URL or a local directory path (required, mutually exclusive)
   - `-n, --name`: Project name (optional, derived from URL/directory if omitted)
   - `-t, --token`: GitHub token (or set GITHUB_TOKEN environment variable)
   - `-o, --output`: Output directory (default: ./output)
   - `-i, --include`: Files to include (e.g., `"*.py" "*.js"`)
   - `-e, --exclude`: Files to exclude (e.g., `"tests/*" "docs/*"`)
   - `-s, --max-size`: Maximum file size in bytes (default: 100KB)
   - `--language`: Language for the generated tutorial (default: "english")

The application will crawl the repository, analyze the codebase structure, generate tutorial content in the specified language, and save the output in the specified directory (default: `./output`).

---

## 🙏 Credits

- Original project: [The-Pocket/Tutorial-Codebase-Knowledge](https://github.com/The-Pocket/Tutorial-Codebase-Knowledge)
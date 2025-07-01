import os
import re
import yaml
from pocketflow import Node, BatchNode
from utils.crawl_git_repo import crawl_git_repo, parse_github_url
from utils.call_llm import call_llm
from utils.crawl_local_files import crawl_local_files
import asyncio
from utils.nostr_publisher import publish_long_form_content_event

# Shared prompt constants to reduce redundancy
STRICT_ACCURACY_REQUIREMENTS = """
**STRICT ACCURACY**: Do NOT invent, fabricate, or assume any information not explicitly present in the provided code. This includes:
- Variable names, function names, or class names not shown in the code
- Configuration values, settings, or parameters not evident in the files
- Dependencies, imports, or external libraries not explicitly referenced
- Functionality, behavior, or features not demonstrated in the actual code
- Relationships or interactions not clearly evident in the provided context

If uncertain about any detail, omit it rather than fabricate. Base all content strictly on the provided code and documentation.
"""

PROFESSIONAL_TONE_GUIDELINES = """
## Style Guidelines
- Use neutral, encyclopedic tone suitable for technical reference documentation
- Write in structured, professional language avoiding overly engaging phrases
- Be concise and focused: Avoid verbose descriptions that overemphasize component importance
- Eliminate redundancy: Do not repeat explanations across different sections
- Maintain proportional coverage: Match explanation depth to actual component significance
- Focus on clarity, accuracy, essential information, design decisions, architectural patterns, system relationships, and the "why" over "what" (architectural purpose, design rationale)
- Organize content logically with clear headers and sections
"""

OUTPUT_FORMAT_INSTRUCTIONS = """
## Output Format
- Provide your response in valid Markdown format
- Use appropriate headers (##, ###) for section organization
- Use bullet points and numbered lists for clarity
- Ensure all content is well-structured and readable
"""


# Helper to get content for specific file indices
def get_content_for_indices(files_data, indices):
    content_map = {}
    for i in indices:
        if 0 <= i < len(files_data):
            path, content = files_data[i]
            content_map[f"{i} # {path}"] = (
                content  # Use index + path as key for context
            )
    return content_map


# Helper function to check if language is non-English and get language hints
def get_language_context(language):
    """Returns language context information for prompt generation."""
    is_non_english = language.lower() != "english"
    lang_cap = language.capitalize() if is_non_english else ""
    
    return {
        "is_non_english": is_non_english,
        "lang_cap": lang_cap,
        "lang_hint": "" if not is_non_english else f" (in {language})",
        "lang_note": "" if not is_non_english else f" (Note: Provided in {lang_cap})"
    }


# Helper function to extract common shared context values
def get_common_context(shared):
    """Extract commonly used values from shared context."""
    return {
        "files_data": shared["files"],
        "project_name": shared["project_name"],
        "git_info": shared.get("git_info", {}),
        "language": shared.get("language", "English"),
        "use_cache": shared.get("use_cache", True)
    }


# Shared utility function to create directory tree representation
def create_directory_tree(files_data, max_items_per_level=15, max_total_lines=40, max_depth=3):
    """Create a directory tree representation from files data.
    
    Args:
        files_data: List of (path, content) tuples or list of file paths
        max_items_per_level: Maximum items to show per directory level
        max_total_lines: Maximum total lines in output
        max_depth: Maximum depth to traverse
        
    Returns:
        str: Formatted directory tree
    """
    # Handle different input formats
    if files_data and isinstance(files_data[0], tuple):
        paths = [path for path, _ in files_data]
    else:
        paths = [file_info[0] for file_info in files_data if isinstance(file_info, tuple) and len(file_info) >= 2]
    
    # Build directory structure
    tree_dict = {}
    for path in paths:
        parts = path.split('/')
        current = tree_dict
        for part in parts[:-1]:  # directories
            if part not in current:
                current[part] = {}
            current = current[part]
        # Add file
        if parts:
            filename = parts[-1]
            if isinstance(current, dict):
                current[filename] = None  # None indicates it's a file
    
    # Convert to readable tree format
    def format_tree(tree_dict, prefix="", current_depth=0):
        if current_depth >= max_depth:
            return []
        
        lines = []
        items = sorted(tree_dict.items()) if isinstance(tree_dict, dict) else []
        
        for i, (name, subtree) in enumerate(items[:max_items_per_level]):
            is_last = i == len(items) - 1
            current_prefix = "└── " if is_last else "├── "
            lines.append(f"{prefix}{current_prefix}{name}")
            
            if subtree is not None and isinstance(subtree, dict) and subtree:
                next_prefix = prefix + ("    " if is_last else "│   ")
                lines.extend(format_tree(subtree, next_prefix, current_depth + 1))
        
        if len(items) > max_items_per_level:
            lines.append(f"{prefix}... ({len(items) - max_items_per_level} more items)")
        
        return lines
    
    tree_lines = format_tree(tree_dict)
    return "\n".join(tree_lines[:max_total_lines])


# Helper function to parse YAML from LLM responses with multiple strategies
def parse_yaml_from_llm_response(response):
    """Parse YAML from LLM response using multiple fallback strategies.
    
    Args:
        response (str): The LLM response text
        
    Returns:
        dict/list: Parsed YAML data
        
    Raises:
        ValueError: If YAML cannot be parsed with detailed error information
    """
    yaml_str = None
    
    # Strategy 1: Look for ```yaml code blocks
    if "```yaml" in response:
        try:
            yaml_str = response.strip().split("```yaml")[1].split("```")[0].strip()
        except IndexError:
            pass
    
    # Strategy 2: Look for ``` code blocks (without yaml specifier)
    if yaml_str is None and "```" in response:
        try:
            # Find content between first pair of ```
            parts = response.strip().split("```")
            if len(parts) >= 3:
                yaml_str = parts[1].strip()
                # Remove language specifier if present (e.g., "yaml\n")
                if yaml_str.startswith(('yaml\n', 'yml\n')):
                    yaml_str = yaml_str.split('\n', 1)[1]
        except (IndexError, AttributeError):
            pass
    
    # Strategy 3: Try to parse the entire response as YAML
    if yaml_str is None:
        yaml_str = response.strip()
    
    # Parse YAML with error handling
    try:
        return yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML from LLM response. YAML Error: {e}\n\nResponse content:\n{response[:500]}...")


# Simple LLM-based repository type detection using directory tree
def detect_repository_type(files_data, shared_context=None):
    """Detect repository type using LLM analysis of directory tree structure"""
    # Check if we already have the result cached in shared context
    if shared_context and "repository_type" in shared_context:
        return shared_context["repository_type"]
    # Create directory tree using shared utility
    directory_tree = create_directory_tree(files_data, max_items_per_level=15, max_total_lines=40)
    doc_context = extract_documentation_context(files_data)
    prompt = f"""Analyze this repository directory structure and determine its type. Respond with ONLY ONE of these exact types: monorepo, library, application, framework, documentation, infrastructure, or mixed.

Directory Structure:
{directory_tree}

README file content to help contextualize the repository:
{doc_context["readme_content"][:3000]}

Repository type definitions:
- monorepo
- library
- framework
- documentation
- application
- mixed

Respond with only the repository type:"""
    response = call_llm(prompt, use_cache=True)
    repo_type = response.strip().lower()
    
    if shared_context is not None:
        shared_context["repository_type"] = repo_type
        print(f"Repository type detected: {repo_type}")
    return repo_type


# Extract documentation context from various sources
def extract_documentation_context(files_data):
    """Extract valuable context from documentation files and directories"""
    doc_context = {
        'readme_content': '',
        'architecture_docs': [],
        'api_docs': [],
        'design_docs': [],
        'contributing_guides': [],
        'docs_structure': []
    }
    
    for path, content in files_data:
        path_lower = path.lower()
        filename = os.path.basename(path_lower)
        
        # README files
        if filename.startswith('readme'):
            doc_context['readme_content'] = content  # First 2000 chars for context
        
        # Architecture documentation
        elif any(term in path_lower for term in ['architecture', 'arch', 'design', 'adr']):
            doc_context['architecture_docs'].append({
                'path': path,
                'content': content[:5000]  # First 1000 chars
            })
        
        # API documentation
        elif any(term in path_lower for term in ['api', 'swagger', 'openapi']):
            doc_context['api_docs'].append({
                'path': path,
                'content': content[:2000]
            })
        
        # Design documents
        elif any(term in filename for term in ['design', 'spec', 'specification']):
            doc_context['design_docs'].append({
                'path': path,
                'content': content[:2000]
            })
        
        # Contributing guides
        elif any(term in filename for term in ['contributing', 'development', 'dev-guide']):
            doc_context['contributing_guides'].append({
                'path': path,
                'content': content[:2000]
            })
        
        # Documentation structure (files in docs directories)
        elif '/docs/' in path_lower or path_lower.startswith('docs/'):
            doc_context['docs_structure'].append(path)
    
    return doc_context


class FetchRepo(Node):
    def prep(self, shared):
        repo_url = shared.get("repo_url")
        local_dir = shared.get("local_dir")
        project_name = shared.get("project_name")

        if not project_name:
            # Basic name derivation from URL or directory
            if repo_url:
                project_name = repo_url.split("/")[-1].replace(".git", "")
            else:
                project_name = os.path.basename(os.path.abspath(local_dir))
            shared["project_name"] = project_name

        # Get file patterns directly from shared
        include_patterns = shared["include_patterns"]
        exclude_patterns = shared["exclude_patterns"]
        max_file_size = shared["max_file_size"]

        return {
            "repo_url": repo_url,
            "local_dir": local_dir,
            "token": shared.get("github_token"),
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
            "max_file_size": max_file_size,
            "use_relative_paths": True,
        }

    def exec(self, prep_res):
        
        if prep_res["repo_url"]:
            print(f"Crawling repository: {prep_res['repo_url']}...")
            # Parse GitHub URL to extract components
            clean_repo_url, branch, subdirectory = parse_github_url(prep_res["repo_url"])
            result = crawl_git_repo(
                repo_url=clean_repo_url,
                token=prep_res["token"],
                include_patterns=prep_res["include_patterns"],
                exclude_patterns=prep_res["exclude_patterns"],
                max_file_size=prep_res["max_file_size"],
                use_relative_paths=prep_res["use_relative_paths"],
                branch=branch,
                subdirectory=subdirectory
            )
        else:
            print(f"Crawling directory: {prep_res['local_dir']}...")

            result = crawl_local_files(
                directory=prep_res["local_dir"],
                include_patterns=prep_res["include_patterns"],
                exclude_patterns=prep_res["exclude_patterns"],
                max_file_size=prep_res["max_file_size"],
                use_relative_paths=prep_res["use_relative_paths"]
            )

        # Convert dict to list of tuples: [(path, content), ...]
        files_list = list(result.get("files", {}).items())
        if len(files_list) == 0:
            raise (ValueError("Failed to fetch files"))
        print(f"Fetched {len(files_list)} files.")
        
        # Extract git information if available (from git repos)
        git_info = result.get("git_info", {})
        
        return {"files": files_list, "git_info": git_info}

    def post(self, shared, prep_res, exec_res):
        shared["files"] = exec_res["files"]  # List of (path, content) tuples
        shared["git_info"] = exec_res["git_info"]  # Git repository information


class IdentifyAbstractions(Node):
    def prep(self, shared):
        ctx = get_common_context(shared)
        max_abstraction_num = shared.get("max_abstraction_num", 20)

        # Helper to create context from files, prioritizing contextual files
        def create_llm_context(files_data):
            # Separate contextual files (README, docs, etc.) from code files
            contextual_files = []
            code_files = []
            
            for i, (path, content) in enumerate(files_data):
                filename = path.lower().split('/')[-1]
                if any(ctx_file in filename for ctx_file in ['readme', 'doc', 'guide', 'overview', 'architecture']):
                    contextual_files.append((i, path, content))
                else:
                    code_files.append((i, path, content))
            
            # Build context with contextual files first, then code files
            context = ""
            file_info = []  # Store tuples of (index, path)
            
            # Add contextual files first for better understanding
            if contextual_files:
                context += "=== PROJECT CONTEXT AND DOCUMENTATION ===\n\n"
                for i, path, content in contextual_files:
                    entry = f"--- File Index {i}: {path} (CONTEXTUAL) ---\n{content}\n\n"
                    context += entry
                    file_info.append((i, path))
                context += "\n=== CODE FILES ===\n\n"
            
            # Add code files
            for i, path, content in code_files:
                entry = f"--- File Index {i}: {path} ---\n{content}\n\n"
                context += entry
                file_info.append((i, path))

            return context, file_info, len(contextual_files)  # Return contextual file count

        context, file_info, contextual_file_count = create_llm_context(ctx["files_data"])
        # Detect repository type and extract documentation context for better guidance
        repo_type = detect_repository_type(ctx["files_data"], shared)
        doc_context = extract_documentation_context(ctx["files_data"])
        
        return (
            context,
            len(ctx["files_data"]),
            ctx["project_name"],
            ctx["language"],
            ctx["use_cache"],
            max_abstraction_num,
            contextual_file_count,
            repo_type,
            doc_context,
        )  # Return all parameters

    def exec(self, prep_res):
        (
            context,
            file_count,
            project_name,
            language,
            use_cache,
            max_abstraction_num,
            contextual_file_count,
            repo_type,
            doc_context,
        ) = prep_res  # Unpack all parameters
        print(f"Identifying abstractions using LLM...")

        # Get language context
        lang_ctx = get_language_context(language)
        language_instruction = ""
        name_lang_hint = ""
        desc_lang_hint = ""
        
        if lang_ctx["is_non_english"]:
            language_instruction = f"IMPORTANT: Generate the `name` and `description` for each abstraction in **{lang_ctx['lang_cap']}** language. Do NOT use English for these fields.\n\n"
            name_lang_hint = f" (value in {lang_ctx['lang_cap']})"
            desc_lang_hint = f" (value in {lang_ctx['lang_cap']})"

        prompt = f"""
## Role and Task
You are an expert software architect and technical documentation specialist. Your task is to identify the 1-{max_abstraction_num} top core code abstractions in this repository for comprehensive wiki documentation that serves as a definitive reference for developers.

## Critical Requirements
{STRICT_ACCURACY_REQUIREMENTS}

## Context
**Project**: `{project_name}`
**Available Files**:
{self._generate_file_listing_for_prompt(contextual_file_count, file_count, context)}

**Documentation Context**: {f'README content available - use it to understand project goals and key components. ' if doc_context['readme_content'] else ''}{f'Architecture docs found ({len(doc_context["architecture_docs"])}) - leverage for system design insights. ' if doc_context['architecture_docs'] else ''}{f'API documentation available ({len(doc_context["api_docs"])}) - prioritize documented interfaces. ' if doc_context['api_docs'] else ''}{f'Design documents found ({len(doc_context["design_docs"])}) - use for understanding intended abstractions. ' if doc_context['design_docs'] else ''}{f'Documentation structure in /docs/ directory - consider documented components as higher priority.' if doc_context['docs_structure'] else 'No structured documentation directory found.'}

**Repository Type**: {repo_type} - {'Focus on distinct functional areas and services across multiple packages/modules.' if repo_type == 'monorepo' else 'Focus on public APIs, core algorithms, and main interfaces that users interact with.' if repo_type == 'library' else 'Prioritize business logic components, data models, and user-facing features over infrastructure.' if repo_type == 'application' else 'Emphasize extensibility points, plugin systems, and core processing engines.' if repo_type == 'framework' else 'Focus on content organization, generation systems, and publishing workflows.' if repo_type == 'documentation' else 'Focus on deployment configurations, infrastructure components, and automation systems.' if repo_type == 'infrastructure' else 'Analyze the primary purpose first, then apply appropriate abstraction strategy.'}

## Codebase to Analyze
{context}

{language_instruction}## Required Output Format
Provide your analysis as a YAML list following this exact structure:

```yaml
- name: |
    Core Authentication System{name_lang_hint}
  description: |
    Manages user authentication, session handling, and access control across the application.
    Serves as the central security gateway that validates user credentials and permissions.{desc_lang_hint}
  file_indices:
    - 0 # auth/login.py
    - 2 # middleware/auth.py
- name: |
    Data Processing Pipeline{name_lang_hint}
  description: |
    Transforms raw input data through multiple validation and processing stages.
    Acts as the core data transformation engine that ensures data quality and format consistency.{desc_lang_hint}
  file_indices:
    - 1 # processors/main.py
    - 4 # utils/transform.py
```"""
        response = call_llm(prompt, use_cache=(use_cache and self.cur_retry == 0))  # Use cache only if enabled and not retrying

        # --- Validation ---
        abstractions = parse_yaml_from_llm_response(response)

        if not isinstance(abstractions, list):
            raise ValueError("LLM Output is not a list")

        validated_abstractions = []
        for item in abstractions:
            if not isinstance(item, dict) or not all(
                k in item for k in ["name", "description", "file_indices"]
            ):
                raise ValueError(f"Missing keys in abstraction item: {item}")
            if not isinstance(item["name"], str):
                raise ValueError(f"Name is not a string in item: {item}")
            if not isinstance(item["description"], str):
                raise ValueError(f"Description is not a string in item: {item}")
            if not isinstance(item["file_indices"], list):
                raise ValueError(f"file_indices is not a list in item: {item}")

            # Validate indices
            validated_indices = []
            for idx_entry in item["file_indices"]:
                try:
                    if isinstance(idx_entry, int):
                        idx = idx_entry
                    elif isinstance(idx_entry, str) and "#" in idx_entry:
                        idx = int(idx_entry.split("#")[0].strip())
                    else:
                        idx = int(str(idx_entry).strip())

                    if not (0 <= idx < file_count):
                        raise ValueError(
                            f"Invalid file index {idx} found in item {item['name']}. Max index is {file_count - 1}."
                        )
                    validated_indices.append(idx)
                except (ValueError, TypeError):
                    raise ValueError(
                        f"Could not parse index from entry: {idx_entry} in item {item['name']}"
                    )

            item["files"] = sorted(list(set(validated_indices)))
            # Store only the required fields
            validated_abstractions.append(
                {
                    "name": item["name"],  # Potentially translated name
                    "description": item[
                        "description"
                    ],  # Potentially translated description
                    "files": item["files"],
                }
            )

        print(f"Identified {len(validated_abstractions)} abstractions.")
        return validated_abstractions

    def post(self, shared, prep_res, exec_res):
        shared["abstractions"] = (
            exec_res  # List of {"name": str, "description": str, "files": [int]}
        )

    def _generate_file_listing_for_prompt(self, contextual_file_count, file_count, context_str):
        """Dynamically generates a file listing from the context string, similar to how it was done before."""
        lines = context_str.split('\n')
        file_listing = []
        
        # Track if we are in the contextual files section or code files section
        in_contextual_section = False
        in_code_section = False

        for i, line in enumerate(lines):
            if "=== PROJECT CONTEXT AND DOCUMENTATION ===" in line:
                in_contextual_section = True
                in_code_section = False
                continue
            elif "=== CODE FILES ===" in line:
                in_code_section = True
                in_contextual_section = False
                continue

            if in_contextual_section or in_code_section:
                # Look for lines marking file entries, e.g., "--- File Index X: path ---"
                match = re.match(r"--- File Index (\d+): (.*?) ---", line)
                if match:
                    file_index = match.group(1)
                    file_path = match.group(2)
                    file_listing.append(f"- {file_index} # {file_path}")
        
        if not file_listing and file_count > 0:
            # Fallback: if dynamic parsing failed, and files exist, provide a generic message
            return f"({file_count} files available, details provided in 'Codebase to Analyze' section.)"

        return "\n".join(file_listing)


class AnalyzeRelationships(Node):
    def prep(self, shared):
        ctx = get_common_context(shared)
        abstractions = shared[
            "abstractions"
        ]  # Now contains 'files' list of indices, name/description potentially translated

        # Get the actual number of abstractions directly
        num_abstractions = len(abstractions)

        # Create context with abstraction names, indices, descriptions, and relevant file snippets
        context = "Identified Abstractions:\\n"
        all_relevant_indices = set()
        abstraction_info_for_prompt = []
        for i, abstr in enumerate(abstractions):
            # Use 'files' which contains indices directly
            file_indices_str = ", ".join(map(str, abstr["files"]))
            # Abstraction name and description might be translated already
            info_line = f"- Index {i}: {abstr['name']} (Relevant file indices: [{file_indices_str}])\\n  Description: {abstr['description']}"
            context += info_line + "\\n"
            abstraction_info_for_prompt.append(
                f"{i} # {abstr['name']}"
            )  # Use potentially translated name here too
            all_relevant_indices.update(abstr["files"])

        context += "\\nRelevant File Snippets (Referenced by Index and Path):\\n"
        # Get content for relevant files using helper
        relevant_files_content_map = get_content_for_indices(
            ctx["files_data"], sorted(list(all_relevant_indices))
        )
        # Format file content for context
        file_context_str = "\\n\\n".join(
            f"--- File: {idx_path} ---\\n{content}"
            for idx_path, content in relevant_files_content_map.items()
        )
        context += file_context_str
        
        # Detect repository type and extract documentation context for better analysis
        repo_type = detect_repository_type(ctx["files_data"], shared)
        doc_context = extract_documentation_context(ctx["files_data"])

        return (
            context,
            "\n".join(abstraction_info_for_prompt),
            num_abstractions, # Pass the actual count
            ctx["project_name"],
            ctx["language"],
            ctx["use_cache"],
            repo_type,
            doc_context,
        )  # Return use_cache and new context

    def exec(self, prep_res):
        (
            context,
            abstraction_listing,
            num_abstractions, # Receive the actual count
            project_name,
            language,
            use_cache,
            repo_type,
            doc_context,
         ) = prep_res  # Unpack use_cache and new context
        print(f"Analyzing relationships using LLM...")

        # Add language instruction and hints only if not English
        language_instruction = ""
        lang_hint = ""
        list_lang_note = ""
        if language.lower() != "english":
            language_instruction = f"IMPORTANT: Generate the `summary` and relationship `label` fields in **{language.capitalize()}** language. Do NOT use English for these fields.\n\n"
            lang_hint = f" (in {language.capitalize()})"
            list_lang_note = f" (Names might be in {language.capitalize()})"  # Note for the input list

        prompt = f"""
## Role and Task
You are an expert software architect and technical documentation specialist. Your task is to analyze code abstractions and their relationships to create a comprehensive project overview for wiki documentation.

## Critical Requirements
{STRICT_ACCURACY_REQUIREMENTS}

**IMPORTANT**: Base your analysis ONLY on the actual code and abstractions provided. Do NOT:
- Reference external frameworks, libraries, or tools not shown in the code
- Create fictional documentation links, URLs, or external resources
- Mention design patterns or concepts not clearly evident in the provided code
- Assume relationships that aren't explicitly demonstrated in the code

## Analysis Instructions
1. **Create a concise project summary** that objectively describes what this codebase accomplishes, its primary purpose, and key capabilities
2. **Map concrete relationships** between abstractions based on verifiable code interactions (imports, function calls, inheritance, data flow, configuration)
3. **Prioritize significant relationships** - focus on connections that are architecturally important, not every minor interaction
4. **Use neutral, encyclopedic tone** - precise technical language that remains accessible
5. **Focus on architectural clarity** - provide a clear mental model of the system's structure
6. **Maintain proportional emphasis** - give more attention to core system relationships, less to peripheral connections
7. **Ensure complete coverage** - every abstraction should be connected to the overall system design

## Context
**Project**: `{project_name}`
**Repository Type**: {repo_type.title()} - {'Focus on relationships between distinct functional areas and services across multiple packages/modules.' if repo_type == 'monorepo' else 'Emphasize public API relationships, core algorithm interactions, and main interface connections.' if repo_type == 'library' else 'Prioritize business logic relationships, data flow between models, and user-facing feature connections.' if repo_type == 'application' else 'Focus on extensibility relationships, plugin system connections, and core processing engine interactions.' if repo_type == 'framework' else 'Emphasize content organization relationships, generation system connections, and publishing workflow interactions.' if repo_type == 'documentation' else 'Focus on deployment relationships, infrastructure component connections, and automation system interactions.' if repo_type == 'infrastructure' else 'Analyze the primary relationships first, then apply appropriate connection strategy.'}

**Documentation Context**: {f'README content available - use it to understand project goals and key component relationships. ' if doc_context['readme_content'] else ''}{f'Architecture docs found ({len(doc_context["architecture_docs"])}) - leverage for system design relationships. ' if doc_context['architecture_docs'] else ''}{f'API documentation available ({len(doc_context["api_docs"])}) - prioritize documented interface relationships. ' if doc_context['api_docs'] else ''}{f'Design documents found ({len(doc_context["design_docs"])}) - use for understanding intended component relationships. ' if doc_context['design_docs'] else ''}{f'Documentation structure in /docs/ directory - consider documented component relationships as higher priority.' if doc_context['docs_structure'] else 'No structured documentation directory found.'}

**Identified Abstractions**{list_lang_note}:
{abstraction_listing}

**Detailed Analysis Context**:
{context}

{language_instruction}## Required Output
Provide a YAML response with two sections:

### 1. Project Summary
Write a concise overview explaining what this project does, its main purpose, and key functionality. Focus on essential information only. Use **bold** and *italic* markdown for emphasis.

### 2. Relationships
List relationships between abstractions based on actual code interactions. Each relationship must specify:
- `from_abstraction`: Source abstraction index and name
- `to_abstraction`: Target abstraction index and name  
- `label`: Brief technical description of the relationship

**Relationship Types to Look For**:
- Function/method calls between abstractions
- Data passing or transformation
- Inheritance or composition
- Configuration or initialization
- Event handling or callbacks

## Output Format
```yaml
summary: |
  This project implements a **web scraping framework** that processes data through multiple stages.
  The system uses a *pipeline architecture* where data flows from collectors to processors to storage.{lang_hint}
relationships:
  - from_abstraction: 0 # DataCollector
    to_abstraction: 1 # DataProcessor
    label: "Feeds raw data"{lang_hint}
  - from_abstraction: 1 # DataProcessor
    to_abstraction: 2 # DataStorage
    label: "Stores processed results"{lang_hint}
  - from_abstraction: 3 # ConfigManager
    to_abstraction: 0 # DataCollector
    label: "Provides settings"{lang_hint}
```

**Remember**: Only describe relationships and functionality that are clearly evident in the provided code context."""
        response = call_llm(prompt, use_cache=(use_cache and self.cur_retry == 0)) # Use cache only if enabled and not retrying

        # --- Validation ---
        relationships_data = parse_yaml_from_llm_response(response)

        if not isinstance(relationships_data, dict) or not all(
            k in relationships_data for k in ["summary", "relationships"]
        ):
            raise ValueError(
                "LLM output is not a dict or missing keys ('summary', 'relationships')"
            )
        if not isinstance(relationships_data["summary"], str):
            raise ValueError("summary is not a string")
        if not isinstance(relationships_data["relationships"], list):
            raise ValueError("relationships is not a list")

        # Validate relationships structure
        validated_relationships = []
        for rel in relationships_data["relationships"]:
            # Check for 'label' key
            if not isinstance(rel, dict) or not all(
                k in rel for k in ["from_abstraction", "to_abstraction", "label"]
            ):
                raise ValueError(
                    f"Missing keys (expected from_abstraction, to_abstraction, label) in relationship item: {rel}"
                )
            # Validate 'label' is a string
            if not isinstance(rel["label"], str):
                raise ValueError(f"Relationship label is not a string: {rel}")

            # Validate indices
            try:
                from_idx = int(str(rel["from_abstraction"]).split("#")[0].strip())
                to_idx = int(str(rel["to_abstraction"]).split("#")[0].strip())
                if not (
                    0 <= from_idx < num_abstractions and 0 <= to_idx < num_abstractions
                ):
                    raise ValueError(
                        f"Invalid index in relationship: from={from_idx}, to={to_idx}. Max index is {num_abstractions-1}."
                    )
                validated_relationships.append(
                    {
                        "from": from_idx,
                        "to": to_idx,
                        "label": rel["label"],  # Potentially translated label
                    }
                )
            except (ValueError, TypeError):
                raise ValueError(f"Could not parse indices from relationship: {rel}")

        print("Generated project summary and relationship details.")
        return {
            "summary": relationships_data["summary"],  # Potentially translated summary
            "details": validated_relationships,  # Store validated, index-based relationships with potentially translated labels
        }

    def post(self, shared, prep_res, exec_res):
        # Structure is now {"summary": str, "details": [{"from": int, "to": int, "label": str}]}
        # Summary and label might be translated
        shared["relationships"] = exec_res


class OrderChapters(Node):
    def prep(self, shared):
        ctx = get_common_context(shared)
        abstractions = shared["abstractions"]  # Name/description might be translated
        relationships = shared["relationships"]  # Summary/label might be translated

        # Prepare context for the LLM
        abstraction_info_for_prompt = []
        for i, a in enumerate(abstractions):
            abstraction_info_for_prompt.append(
                f"- {i} # {a['name']}"
            )  # Use potentially translated name
        abstraction_listing = "\n".join(abstraction_info_for_prompt)

        # Use potentially translated summary and labels
        lang_ctx = get_language_context(ctx["language"])
        summary_note = lang_ctx["lang_note"].replace("Provided", "Project Summary might be")

        context = f"Project Summary{summary_note}:\n{relationships['summary']}\n\n"
        context += "Relationships (Indices refer to abstractions above):\n"
        for rel in relationships["details"]:
            from_name = abstractions[rel["from"]]["name"]
            to_name = abstractions[rel["to"]]["name"]
            # Use potentially translated 'label'
            context += f"- From {rel['from']} ({from_name}) to {rel['to']} ({to_name}): {rel['label']}\n"  # Label might be translated

        list_lang_note = lang_ctx["lang_note"].replace("Provided", "Names might be")

        return (
            abstraction_listing,
            context,
            len(abstractions),
            ctx["project_name"],
            list_lang_note,
            ctx["use_cache"],
        )  # Return use_cache

    def exec(self, prep_res):
        (
            abstraction_listing,
            context,
            num_abstractions,
            project_name,
            list_lang_note,
            use_cache,
        ) = prep_res  # Unpack use_cache
        print("Determining chapter order using LLM...")
        # No language variation needed here in prompt instructions, just ordering based on structure
        # The input names might be translated, hence the note.
        prompt = f"""
## Role and Task
You are an expert software architect and technical documentation specialist. Your task is to determine the optimal organization for presenting code abstractions in a comprehensive wiki for `{project_name}`.

## Critical Requirements
{STRICT_ACCURACY_REQUIREMENTS}

**IMPORTANT**: Base your ordering decisions ONLY on the actual abstractions and relationships provided. Do NOT:
- Reference external concepts, frameworks, or patterns not shown in the context
- Assume dependencies that aren't clearly demonstrated
- Create fictional prerequisites or dependencies
- Mention concepts not explicitly present in the provided abstractions

## Organization Strategy
Apply these principles to create a **logical reference structure** that serves developers seeking to understand the project's key functionality:

1. **Primary Functionality**: Start with abstractions that directly implement the project's main purpose and core features
2. **System Entry Points**: Present main interfaces, APIs, or user-facing components that provide access to core functionality
3. **Core Architecture**: Cover fundamental abstractions that define the system's structure and design patterns
4. **Business Logic**: Include domain-specific functionality, algorithms, and processing components
5. **Data Management**: Present data structures, models, and persistence layers
6. **Supporting Infrastructure**: Include configuration, utilities, and helper components
7. **Proportional Emphasis**: Order components based on their actual importance to the system's core functionality
8. **Reference Logic**: Order for comprehensive understanding

## Context
**Project**: `{project_name}`
**Available Abstractions**{list_lang_note}:
{abstraction_listing}

**Relationships and Project Overview**:
{context}

## Required Output
Provide a YAML list with the optimal organization for presenting these abstractions in a wiki. Each entry should be the abstraction index followed by its name as a comment.

**Consider This Reference Organization Logic**:
- Which abstractions serve as the primary system interfaces or entry points?
- What are the fundamental architectural components that define the system?
- Which abstractions contain the core domain logic and business functionality?
- What supporting infrastructure is architecturally significant (avoid over-emphasizing minor utilities)?
- How much of the system's behavior depends on each component?
- How should components be ordered to reflect their actual importance to the system?
- How can the organization enable effective cross-referencing without redundant coverage?

## Output Format
```yaml
- 0 # CoreDataStructure
- 2 # ConfigurationManager  
- 1 # MainProcessor
- 3 # OutputHandler
```

**Remember**: Base your ordering only on the relationships and functionality clearly shown in the provided context."""
        response = call_llm(prompt, use_cache=(use_cache and self.cur_retry == 0)) # Use cache only if enabled and not retrying

        # --- Validation ---
        ordered_indices_raw = parse_yaml_from_llm_response(response)

        if not isinstance(ordered_indices_raw, list):
            raise ValueError("LLM output is not a list")

        ordered_indices = []
        seen_indices = set()
        for entry in ordered_indices_raw:
            try:
                if isinstance(entry, int):
                    idx = entry
                elif isinstance(entry, str) and "#" in entry:
                    idx = int(entry.split("#")[0].strip())
                else:
                    idx = int(str(entry).strip())

                if not (0 <= idx < num_abstractions):
                    raise ValueError(
                        f"Invalid index {idx} in ordered list. Max index is {num_abstractions-1}."
                    )
                if idx in seen_indices:
                    raise ValueError(f"Duplicate index {idx} found in ordered list.")
                ordered_indices.append(idx)
                seen_indices.add(idx)

            except (ValueError, TypeError):
                raise ValueError(
                    f"Could not parse index from ordered list entry: {entry}"
                )

        # Check if all abstractions are included
        if len(ordered_indices) != num_abstractions:
            raise ValueError(
                f"Ordered list length ({len(ordered_indices)}) does not match number of abstractions ({num_abstractions}). Missing indices: {set(range(num_abstractions)) - seen_indices}"
            )

        print(f"Determined chapter order (indices): {ordered_indices}")
        return ordered_indices  # Return the list of indices

    def post(self, shared, prep_res, exec_res):
        # exec_res is already the list of ordered indices
        shared["chapter_order"] = exec_res  # List of indices


class WriteChapters(BatchNode):
    def prep(self, shared):
        ctx = get_common_context(shared)
        chapter_order = shared["chapter_order"]  # List of indices
        abstractions = shared[
            "abstractions"
        ]  # List of {"name": str, "description": str, "files": [int]}

        # Get already written chapters to provide context
        # We store them temporarily during the batch run, not in shared memory yet
        # The 'previous_chapters_summary' will be built progressively in the exec context
        self.chapters_written_so_far = (
            []
        )  # Use instance variable for temporary storage across exec calls

        # Create a complete list of all chapters
        all_chapters = []
        chapter_filenames = {}  # Store chapter filename mapping for linking
        for i, abstraction_index in enumerate(chapter_order):
            if 0 <= abstraction_index < len(abstractions):
                chapter_num = i + 1
                chapter_name = abstractions[abstraction_index][
                    "name"
                ]  # Potentially translated name
                # Create safe filename (from potentially translated name)
                safe_name = "".join(
                    c if c.isalnum() else "_" for c in chapter_name
                ).lower()
                filename = f"{i+1:02d}_{safe_name}.md"
                # Format with link (using potentially translated name)
                all_chapters.append(f"{chapter_num}. [{chapter_name}]({filename})")
                # Store mapping of chapter index to filename for linking
                chapter_filenames[abstraction_index] = {
                    "num": chapter_num,
                    "name": chapter_name,
                    "filename": filename,
                }

        # Create a formatted string with all chapters
        full_chapter_listing = "\n".join(all_chapters)

        items_to_process = []
        for i, abstraction_index in enumerate(chapter_order):
            if 0 <= abstraction_index < len(abstractions):
                abstraction_details = abstractions[
                    abstraction_index
                ]  # Contains potentially translated name/desc
                # Use 'files' (list of indices) directly
                related_file_indices = abstraction_details.get("files", [])
                # Get content using helper, passing indices
                related_files_content_map = get_content_for_indices(
                    ctx["files_data"], related_file_indices
                )

                # Get previous chapter info for transitions (uses potentially translated name)
                prev_chapter = None
                if i > 0:
                    prev_idx = chapter_order[i - 1]
                    prev_chapter = chapter_filenames[prev_idx]

                # Get next chapter info for transitions (uses potentially translated name)
                next_chapter = None
                if i < len(chapter_order) - 1:
                    next_idx = chapter_order[i + 1]
                    next_chapter = chapter_filenames[next_idx]

                items_to_process.append(
                    {
                        "chapter_num": i + 1,
                        "abstraction_index": abstraction_index,
                        "abstraction_details": abstraction_details,  # Has potentially translated name/desc
                        "related_files_content_map": related_files_content_map,
                        "project_name": ctx["project_name"],  # Add project name
                        "full_chapter_listing": full_chapter_listing,  # Add the full chapter listing (uses potentially translated names)
                        "chapter_filenames": chapter_filenames,  # Add chapter filenames mapping (uses potentially translated names)
                        "prev_chapter": prev_chapter,  # Add previous chapter info (uses potentially translated name)
                        "next_chapter": next_chapter,  # Add next chapter info (uses potentially translated name)
                        "language": ctx["language"],  # Add language for multi-language support
                        "use_cache": ctx["use_cache"], # Pass use_cache flag
                        # previous_chapters_summary will be added dynamically in exec
                    }
                )
            else:
                print(
                    f"Warning: Invalid abstraction index {abstraction_index} in chapter_order. Skipping."
                )

        print(f"Preparing to write {len(items_to_process)} wiki articles...")
        return items_to_process  # Iterable for BatchNode

    def exec(self, item):
        # This runs for each item prepared above
        abstraction_name = item["abstraction_details"][
            "name"
        ]  # Potentially translated name
        abstraction_description = item["abstraction_details"][
            "description"
        ]  # Potentially translated description
        chapter_num = item["chapter_num"]
        project_name = item.get("project_name")
        language = item.get("language", "english")
        use_cache = item.get("use_cache", True) # Read use_cache from item
        print(f"Writing wiki article {chapter_num} for: {abstraction_name} using LLM...")

        # Prepare file context string from the map
        file_context_str = "\n\n".join(
            f"--- File: {idx_path.split('# ')[1] if '# ' in idx_path else idx_path} ---\n{content}"
            for idx_path, content in item["related_files_content_map"].items()
        )

        # Get summary of chapters written *before* this one
        # Use the temporary instance variable
        previous_chapters_summary = "\n---\n".join(self.chapters_written_so_far)

        # Add language instruction and context notes only if not English
        language_instruction = ""
        concept_details_note = ""
        structure_note = ""
        prev_summary_note = ""
        instruction_lang_note = ""
        mermaid_lang_note = ""
        code_comment_note = ""
        link_lang_note = ""
        tone_note = ""
        if language.lower() != "english":
            lang_cap = language.capitalize()
            language_instruction = f"IMPORTANT: Write this ENTIRE tutorial chapter in **{lang_cap}**. Some input context (like concept name, description, chapter list, previous summary) might already be in {lang_cap}, but you MUST translate ALL other generated content including explanations, examples, technical terms, and potentially code comments into {lang_cap}. DO NOT use English anywhere except in code syntax, required proper nouns, or when specified. The entire output MUST be in {lang_cap}.\n\n"
            concept_details_note = f" (Note: Provided in {lang_cap})"
            structure_note = f" (Note: Chapter names might be in {lang_cap})"
            prev_summary_note = f" (Note: This summary might be in {lang_cap})"
            instruction_lang_note = f" (in {lang_cap})"
            mermaid_lang_note = f" (Use {lang_cap} for labels/text if appropriate)"
            code_comment_note = f" (Translate to {lang_cap} if possible, otherwise keep minimal English for clarity)"
            link_lang_note = (
                f" (Use the {lang_cap} chapter title from the structure above)"
            )
            tone_note = f" (appropriate for {lang_cap} readers)"

        prompt = f"""
## Role and Task
You are an expert software architect and technical documentation specialist. Your task is to write a comprehensive wiki article about "{abstraction_name}" for the `{project_name}` codebase repository.

## Critical Requirements
{STRICT_ACCURACY_REQUIREMENTS}

**IMPORTANT**: Base your article content ONLY on the actual code and context provided. Do NOT:
- Reference external libraries, frameworks, or tools not shown in the provided code
- Create fictional URLs, documentation links, or external resources
- Mention design patterns or concepts not clearly evident in the code
- Add code examples that don't exist in the provided context
- Reference files, functions, or classes not present in the code snippets
- Create hypothetical scenarios or use cases not supported by the actual code
- Repeat detailed explanations already covered in other wiki articles
- Over-explain concepts that are peripheral to this component's core functionality

**IMPORTANT**: Focus on:
- Architectural purpose and design rationale
- How this component solves specific problems in the system
- Avoid repeating explanations from other articles

{PROFESSIONAL_TONE_GUIDELINES}

{language_instruction}## Context
**Project**: `{project_name}`
**Article Subject**: {abstraction_name}
**Article Number**: {chapter_num}

**Component Overview**{concept_details_note}:
{abstraction_description}

**Wiki Structure**{structure_note}:
{item["full_chapter_listing"]}

**Related Articles Context**{prev_summary_note}:
{previous_chapters_summary if previous_chapters_summary else "This is the first article in the wiki - no related context yet."}

**Code Context** (Use ONLY this code in your explanations):
{file_context_str if file_context_str else "No specific code snippets provided for this abstraction."}

## Wiki Article Structure Requirements
Your article must include:

1. **Article Title**: `# {abstraction_name}`
2. **Overview**: 
   - Concise explanation of the component's purpose
   - Why this component exists and what problem it solves

3. **Architecture**: 
   - Design decisions and architectural patterns used
   - Brief description of the component's design and structure

4. **Role in System**: 
   - How this component fits into the overall system design
   - Primary usage scenarios within the system

5. **Key Components**:
   - Essential classes, functions, and methods
   - Primary functions and responsibilities

6. **Relationships and Interactions**:
   - Direct connections to other components
   - How it connects to and collaborates with other components

7. **Design Rationale**:
   - Why it was designed this way
   - Critical implementation specifics

8. **Implementation Technical Details**: 
   - Focused walkthrough of key code elements
   - Critical implementation specifics only

9. **See Also**: 
   - References to related wiki articles (if applicable)


**Content Guidelines**:
- Keep each section focused and proportional to the component's actual importance
- Focus on what makes this component architecturally significant, not general programming concepts

## Code Presentation Rules (if applicable)
- Keep code blocks under 20 lines
- Only show code that exists in the provided context
- Add minimal comments only when they clarify complex logic
- Break long code into logical segments with explanations
- Use proper syntax highlighting

## Output Format
Provide ONLY the Markdown content (no code fences around the entire output).
**Remember**: Every code example, function reference, and technical detail must be based on the actual code provided in the context above."""
        chapter_content = call_llm(prompt, use_cache=(use_cache and self.cur_retry == 0)) # Use cache only if enabled and not retrying
        # Basic validation/cleanup
        actual_heading = f"# {abstraction_name}"  # Use potentially translated name
        if not chapter_content.strip().startswith(f"# {abstraction_name}"):
            # Add heading if missing or incorrect, trying to preserve content
            lines = chapter_content.strip().split("\n")
            if lines and lines[0].strip().startswith(
                "#"
            ):  # If there's some heading, replace it
                lines[0] = actual_heading
                chapter_content = "\n".join(lines)
            else:  # Otherwise, prepend it
                chapter_content = f"{actual_heading}\n\n{chapter_content}"

        # Add the generated content to our temporary list for the next iteration's context
        self.chapters_written_so_far.append(chapter_content)

        return chapter_content  # Return the Markdown string (potentially translated)

    def post(self, shared, prep_res, exec_res_list):
        # exec_res_list contains the generated Markdown for each wiki article, in order
        shared["chapters"] = exec_res_list
        # Clean up the temporary instance variable
        del self.chapters_written_so_far
        print(f"Finished writing {len(exec_res_list)} wiki articles.")


class WriteBeginnerFriendlyEpisode(Node):
    def prep(self, shared):
        ctx = get_common_context(shared)
        abstractions = shared["abstractions"]
        relationships = shared["relationships"]
        chapters = shared["chapters"]
        project_name = ctx["project_name"]
        language = ctx["language"]
        use_cache = ctx["use_cache"]

        # Combine wiki chapters into a single string for context
        combined_wiki_content = "\n\n".join(chapters)

        # Prepare context for the LLM
        abstractions_overview = "\n".join([
            f"- {abstr['name']}: {abstr['description']}"
            for abstr in abstractions
        ])
        
        summary_note = ""
        lang_ctx = get_language_context(language)
        if lang_ctx["is_non_english"]:
            summary_note = f" (Note: Project Summary and Relationships might be in {lang_ctx['lang_cap']})"


        context = f"""
## Project Overview (for your understanding)
Project Name: {project_name}
Project Summary{summary_note}: {relationships["summary"]}

## Core Abstractions (for your understanding)
{abstractions_overview}

## Key Relationships (for your understanding)
{relationships["details"]}

## Detailed Wiki Content (Generated Chapters)
{combined_wiki_content}
"""
        return (
            context,
            project_name,
            language,
            use_cache,
            abstractions,
            relationships,
            chapters
        )

    def exec(self, prep_res):
        (
            context,
            project_name,
            language,
            use_cache,
            abstractions,
            relationships,
            chapters
        ) = prep_res
        print(f"Generating beginner-friendly episode for {project_name}...")

        # Add language instructions and hints if not English
        language_instruction = ""
        if language.lower() != "english":
            lang_cap = language.capitalize()
            language_instruction = f"IMPORTANT: Write this ENTIRE beginner-friendly episode in **{lang_cap}**. Do NOT use English anywhere except required proper nouns.\n\n"

        prompt = f"""
{language_instruction}## Role and Task
You are an expert technical writer and educator. Your task is to transform a detailed technical wiki about a software project into a beginner-friendly overview document. This document should be easy for a non-technical person to understand while still conveying accurate information about the system and its concepts.

## Critical Requirements
{STRICT_ACCURACY_REQUIREMENTS}

The document should prioritize clarity, relevance, and accessibility. The primary goal is to describe what the project does, relationships between modules and parts of the codebase, presenting complex technical concepts and terms in a way that an average non-technical person can understand. The document should be beginner-friendly, precise, and approachable, without oversimplifying the underlying concepts.

## Suggested Document Structure (Adapt as needed)
Note: This structure is purely suggestive and should not be followed rigidly. Combine sections or adapt as necessary to best explain *this specific project*.

1.  **Introduction**
    *   Project overview
    *   Core purpose
    *   System's primary objectives

2.  **System Architecture**
    *   High-level system diagram (conceptual, using mermaid)
    *   Key components
    *   Component interactions

3.  **Module Breakdown**
    *   Core modules
    *   Module responsibilities
    *   Functional interactions

4.  **Key Concepts**
    *   Fundamental technical concepts
    *   Simplified explanations
    *   Conceptual relationships

5.  **Workflow and Data Flow**
    *   System operation process
    *   Data transformation steps
    *   Key processing logic

6.  **Technical Foundations**
    *   Primary design principles
    *   Critical implementation strategies
    *   Core algorithmic approaches

7.  **Glossary**
    *   Essential technical terms
    *   Plain language definitions

## Context
Project Name: {project_name}

{context}

{OUTPUT_FORMAT_INSTRUCTIONS}
- Make technical explanations **accessible to a non-technical audience**.
- Use analogies, and examples to explain complex concepts if necessary
- Avoid jargon where possible, or explain it clearly.
- Focus on the "what" and "why" from a user perspective.
- Be concise
- Don't overuse lists, prefer paragraphs

Provide ONLY the Markdown content for the episode (no code fences around the entire output).
"""
        episode_content = call_llm(prompt, use_cache=(use_cache and self.cur_retry == 0))
        print(f"Generated beginner-friendly episode for {project_name}.")
        return episode_content

    def post(self, shared, prep_res, exec_res):
        shared["beginner_friendly_episode"] = exec_res # Store the Markdown content


class CombineTutorial(Node):
    def prep(self, shared):
        ctx = get_common_context(shared)
        output_base_dir = shared.get("output_dir", "output")  # Default output dir
        output_path = os.path.join(output_base_dir, ctx["project_name"])
        repo_url = shared.get("repo_url")  # Get the repository URL
        nostr_flag = shared.get("publish_to_nostr", False) # Get the Nostr flag

        # Detect repository type and extract documentation context for better categorization
        repo_type = detect_repository_type(ctx["files_data"], shared)
        doc_context = extract_documentation_context(ctx["files_data"])
        
        # Extract README.md, license, and other contextual information
        readme_content = ""
        license_content = ""
        license_info = {}
        project_context = ""
        
        for path, content in ctx["files_data"]:
            filename = path.lower().split('/')[-1]
            if 'readme' in filename:
                readme_content = content
                project_context += f"\n\n=== README.md Content ===\n{content}"
            elif 'license' in filename or filename in ['copying', 'copyright']:
                license_content = content
                license_info = self._extract_license_info(path, content)
                project_context += f"\n\n=== License File ({path}) ===\n{content}"
            elif any(ctx_file in filename for ctx_file in ['doc', 'guide', 'overview', 'architecture']):
                project_context += f"\n\n=== {path} ===\n{content}"
        
        # Collect metadata for index generation
        from datetime import datetime
        generation_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get git information from shared context
        git_info = shared.get("git_info", {})
        
        # Create metadata dictionary with only known values
        metadata = {
            "generation_date": generation_date,
            "repo_url": repo_url,
            "git_info": git_info,
            "license_info": license_info
        }
        
        # Only add git fields if they have actual values
        commit_hash = git_info.get("commit_hash")
        if commit_hash and commit_hash != "unknown":
            metadata["commit_hash"] = commit_hash
            
        commit_short_hash = git_info.get("commit_short_hash")
        if commit_short_hash and commit_short_hash != "unknown":
            metadata["commit_short_hash"] = commit_short_hash

        # Get potentially translated data
        relationships_data = shared[
            "relationships"
        ]  # {"summary": str, "details": [{"from": int, "to": int, "label": str}]} -> summary/label potentially translated
        chapter_order = shared["chapter_order"]  # indices
        abstractions = shared[
            "abstractions"
        ]  # list of dicts -> name/description potentially translated
        chapters_content = shared[
            "chapters"
        ]  # list of strings -> content potentially translated
        beginner_friendly_episode = shared.get("beginner_friendly_episode", "")

        # --- Generate Mermaid Diagram ---
        mermaid_lines = ["flowchart TD"]
        # Add nodes for each abstraction using potentially translated names
        for i, abstr in enumerate(abstractions):
            node_id = f"A{i}"
            # Use potentially translated name, sanitize for Mermaid ID and label
            sanitized_name = abstr["name"].replace('"', "")
            node_label = sanitized_name  # Using sanitized name only
            mermaid_lines.append(
                f'    {node_id}["{node_label}"]'
            )  # Node label uses potentially translated name
        # Add edges for relationships using potentially translated labels
        for rel in relationships_data["details"]:
            from_node_id = f"A{rel['from']}"
            to_node_id = f"A{rel['to']}"
            # Use potentially translated label, sanitize
            edge_label = (
                rel["label"].replace('"', "").replace("\n", " ")
            )  # Basic sanitization
            max_label_len = 30
            if len(edge_label) > max_label_len:
                edge_label = edge_label[: max_label_len - 3] + "..."
            mermaid_lines.append(
                f'    {from_node_id} -- "{edge_label}" --> {to_node_id}'
            )  # Edge label uses potentially translated label

        mermaid_diagram = "\n".join(mermaid_lines)
        # --- End Mermaid ---

        # Prepare chapter information for the comprehensive index
        chapter_files = []
        chapter_links = []
        
        # Generate chapter files and links based on the determined order
        for i, abstraction_index in enumerate(chapter_order):
            # Ensure index is valid and we have content for it
            if 0 <= abstraction_index < len(abstractions) and i < len(chapters_content):
                abstraction_name = abstractions[abstraction_index][
                    "name"
                ]  # Potentially translated name
                # Sanitize potentially translated name for filename
                safe_name = "".join(
                    c if c.isalnum() else "_" for c in abstraction_name
                ).lower()
                filename = f"{i+1:02d}_{safe_name}.md"
                
                # Store chapter link info
                chapter_links.append({
                    "number": i + 1,
                    "title": abstraction_name,
                    "filename": filename,
                    "description": abstractions[abstraction_index]["description"]
                })
                
                # Store filename and corresponding content
                chapter_files.append({"filename": filename, "content": chapters_content[i]})
            else:
                print(
                    f"Warning: Mismatch between chapter order, abstractions, or content at index {i} (abstraction index {abstraction_index}). Skipping file generation for this entry."
                )
        
        # Add the beginner-friendly episode to chapter_links
        # Ensure it always appears as the last item
        bf_episode_number = len(chapter_links) + 1
        chapter_links.append({
            "number": bf_episode_number,
            "title": "Beginner-Friendly Overview",
            "filename": "beginner_friendly_episode.md",
            "description": "A high-level, simplified overview of the project for non-technical readers."
        })

        # --- Generate comprehensive index content using LLM ---
        index_content = self._generate_comprehensive_index(
            ctx["project_name"], relationships_data, abstractions, repo_url, mermaid_diagram, chapter_links, shared, project_context, metadata, repo_type, beginner_friendly_episode
        )

        return {
            "output_path": output_path,
            "index_content": index_content,
            "chapter_files": chapter_files,  # List of {"filename": str, "content": str}
            "beginner_friendly_episode": beginner_friendly_episode, # NEW: Pass the beginner-friendly content
            "publish_to_nostr": nostr_flag, # Pass the Nostr flag
            "repo_url": repo_url,
        }

    def _generate_comprehensive_index(self, project_name, relationships_data, abstractions, repo_url, mermaid_diagram, chapter_links, shared, project_context="", metadata=None, repo_type="mixed", beginner_friendly_episode_content=""):
        """Generate a comprehensive index with project overview, tech stack, architecture, and design insights."""
        
        # Get file information for tech stack analysis
        files_info = shared.get("files", [])
        
        # Prepare context for LLM
        abstractions_context = "\n".join([
            f"- **{abstr['name']}**: {abstr['description']}"
            for abstr in abstractions
        ])
        
        # Create simple directory tree for LLM analysis
        directory_tree = self._create_directory_tree(files_info)
        
        # Analyze file extensions for basic tech stack info
        file_extensions = {}
        config_files = []
        
        for file_info in files_info:
            # files_info is a list of (path, content) tuples
            if isinstance(file_info, tuple) and len(file_info) >= 2:
                path = file_info[0]
            else:
                continue  # Skip malformed entries
                
            if "." in path:
                ext = path.split(".")[-1].lower()
                file_extensions[ext] = file_extensions.get(ext, 0) + 1
            
            # Identify config files
            filename = path.split("/")[-1].lower()
            if any(config_name in filename for config_name in [
                "package.json", "requirements.txt", "cargo.toml", "go.mod",
                "pom.xml", "build.gradle", "composer.json", "gemfile",
                "dockerfile", "docker-compose", "config", "settings", ".env"
            ]):
                config_files.append(path)
        
        tech_stack_context = "\n".join([
            f"- {ext}: {count} files" for ext, count in sorted(file_extensions.items(), key=lambda x: x[1], reverse=True)[:10]
        ])
        
        config_files_context = "\n".join([f"- {cf}" for cf in config_files[:10]])
        
        # Prepare chapter links context
        chapter_links_context = "\n".join([
            f"{ch['number']}. [{ch['title']}]({ch['filename']}) - {ch['description'][:100]}{'...' if len(ch['description']) > 100 else ''}"
            for ch in chapter_links
        ])
        
        language = shared.get("language", "english")
        lang_ctx = get_language_context(language)
        lang_hint = lang_ctx["lang_hint"]
        
        # Handle metadata safely
        if metadata is None:
            from datetime import datetime
            metadata = {
                "generation_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "repo_url": repo_url,
                "git_info": {}
            }
        
        # Build metadata section with all available information
        git_info = metadata.get('git_info', {})
        metadata_lines = []
        
        # Always show generation date
        gen_date = metadata.get('generation_date')
        if gen_date:
            metadata_lines.append(f"**Generated:** {gen_date}")
        
        # Show repository URL if available
        repo_url_display = metadata.get('repo_url', repo_url)
        if repo_url_display and repo_url_display not in ['unknown', 'local', None]:
            metadata_lines.append(f"**Repository:** {repo_url_display}")
        
        # Show commit information - check git_info for all commit details
        commit_hash = git_info.get('commit_hash')
        commit_short = git_info.get('commit_short_hash')
        commit_msg = git_info.get('commit_message')
        commit_author = git_info.get('commit_author')
        commit_date = git_info.get('commit_date')
        
        # Build commit display with available information
        if commit_short and commit_short != 'unknown':
            commit_parts = [commit_short]
            if commit_msg and commit_msg != 'unknown':
                # Truncate long commit messages
                msg_display = commit_msg[:60] + '...' if len(commit_msg) > 60 else commit_msg
                commit_parts.append(msg_display)
            metadata_lines.append(f"**Commit:** {' - '.join(commit_parts)}")
        elif commit_hash and commit_hash != 'unknown':
            # Fallback to full hash if short hash not available
            commit_parts = [commit_hash[:8]]
            if commit_msg and commit_msg != 'unknown':
                msg_display = commit_msg[:60] + '...' if len(commit_msg) > 60 else commit_msg
                commit_parts.append(msg_display)
            metadata_lines.append(f"**Commit:** {' - '.join(commit_parts)}")
        
        # Show commit author if available
        if commit_author and commit_author != 'unknown':
            metadata_lines.append(f"**Author:** {commit_author}")
        
        # Show commit date if available
        if commit_date and commit_date != 'unknown':
            metadata_lines.append(f"**Commit Date:** {commit_date}")
        
        # Show license information if available
        license_info = metadata.get('license_info', {})
        if license_info.get('name'):
            license_display = license_info['name']
            if license_info.get('file_path'):
                license_display += f" (see {license_info['file_path']})"
            metadata_lines.append(f"**License:** {license_display}")
        
        # Create metadata section only if we have metadata to show
        metadata_section = ""
        if metadata_lines:
            metadata_section = "## Generation Metadata\n" + "\n".join(metadata_lines) + "\n\n"
        
        prompt = f"""
You are an expert technical documentation specialist and software architect. Your task is to create a comprehensive index page for a developer wiki about the project `{project_name}`.
 
{metadata_section}
 
## Project Context
**Project Summary:** {relationships_data['summary']}
 
{'## Additional Project Documentation' + project_context if project_context.strip() else ''}
 
## Directory Structure
{directory_tree}
 
**Detected Repository Type:** {repo_type.title()}
 
## Core Abstractions
{abstractions_context}
 
## Technical Context
**File Extensions Found:**
{tech_stack_context}
 
**Configuration Files:**
{config_files_context}
 
## Tutorial Chapters Available
{chapter_links_context}
 
## Architecture Diagram
The following Mermaid diagram shows the relationships between core components:
```mermaid
{mermaid_diagram}
```
 
## Your Task
Create a concise, well-structured index page that serves as the entry point for developers. The index should be informative and provide clear navigation while maintaining proportional emphasis on components based on their actual importance.
 
## Required Sections
1. **Project Title**
2. **📊 Generation Metadata** - Include the generation metadata provided above (generation date, repository, commit info, license, etc.)
3. **🎯 What This Project Does** - Clear value proposition and primary functionality
4. **📁 Repository Structure** - This is a **{repo_type.title()}** repository. Analyze the directory structure focusing on:
   {'- Multiple distinct functional areas and how they are organized across packages/modules - Key services or applications and their separation of concerns - Shared libraries and common utilities' if repo_type == 'monorepo' else '- Public API structure and main entry points - Core library organization and module hierarchy - Distribution and packaging approach' if repo_type == 'library' else '- Application entry points and main execution flow - Business logic organization and feature structure - Configuration and deployment setup' if repo_type == 'application' else '- Extensibility mechanisms and plugin architecture - CLI interfaces and developer tools - Core processing engines and framework components' if repo_type == 'framework' else '- Content organization and documentation structure - Example code and tutorial progression - Publishing and generation workflows' if repo_type == 'documentation' else '- Infrastructure components and deployment configurations - Automation systems and CI/CD pipelines - Environment management and orchestration' if repo_type == 'infrastructure' else '- Primary purpose and main organizational patterns - Key functional areas and their relationships - Overall architecture and design approach'}
   
   Provide key insights about the organization and structure without repeating the type classification.
5. **🏗️ Architecture Overview** - High-level design and key architectural patterns (focus on essential patterns only)
6. **🛠️ Technology Stack** - Primary languages dependencies, frameworks, tools
7. **📋 Core Components** - Brief overview of main abstractions and their roles
8. **🗺️ Component Relationships** - Include the Mermaid diagram with focused explanation
9. **📚 Wiki Articles** - Navigation to detailed component documentation, use markdown links with a human-readable title, include beginner-friendly episode as the last article
 
## Critical Requirements
{STRICT_ACCURACY_REQUIREMENTS}
 
**Additional Guidelines**:
- **Use project documentation**: If README.md or other documentation is provided above, use it to understand the project's main purpose, goals, and key features
- **Prioritize functional importance**: Focus on components that directly serve the project's main purpose rather than supporting utilities
- **Maintain proportional emphasis**: Give more attention to core system components, less to peripheral utilities
- **Avoid redundancy**: Don't repeat information across sections - each section should provide unique value
- **Be concise and focused**: Avoid verbose descriptions that overemphasize component importance
- **Structured, professional tone**: Avoid overly engaging language like "Welcome to the definitive...". Use clear, direct, and structured language
- Use **section emojis** for navigation while maintaining professional tone
- **Do NOT** make assumptions about deployment, hosting, or infrastructure not shown in the files
- **Do NOT** include installation instructions or setup steps unless clearly evident from config files
- Include the repository link prominently for easy access
 
{PROFESSIONAL_TONE_GUIDELINES}
 
{OUTPUT_FORMAT_INSTRUCTIONS}
- Make technical explanations **accessible to developers at all experience levels**
 
## Output Format
Provide the complete Markdown content for the index page{lang_hint}. Start with the main title, then immediately include the Generation Metadata section with all the metadata information provided above, followed by all other required sections. Do NOT wrap the output in code fences.
"""
        
        # Generate the comprehensive index using LLM
        index_content = call_llm(prompt, use_cache=shared.get("use_cache", True))
        
        # Clean up any potential code fence wrapping
        if index_content.startswith("```markdown"):
            index_content = index_content[11:]
        if index_content.startswith("```"):
            index_content = index_content[3:]
        if index_content.endswith("```"):
            index_content = index_content[:-3]
        
        return index_content.strip()

    def _create_directory_tree(self, files_info):
        """Create a simple directory tree representation for LLM analysis."""
        return create_directory_tree(files_info, max_items_per_level=20, max_total_lines=50)

    def _extract_license_info(self, file_path, content):
        """Extract license information from license file content."""
        license_info = {
            "file_path": file_path
        }
        
        if not content or not content.strip():
            return license_info
            
        content_upper = content.upper()
        content_lines = content.strip().split('\n')
        
        # Common license patterns - more flexible matching
        license_patterns = {
            "MIT License": ["MIT LICENSE"],
            "MIT License": ["PERMISSION IS HEREBY GRANTED", "MIT"],
            "Apache License 2.0": ["APACHE LICENSE", "VERSION 2.0"],
            "GNU GPL v3.0": ["GNU GENERAL PUBLIC LICENSE", "VERSION 3"],
            "GNU GPL v2.0": ["GNU GENERAL PUBLIC LICENSE", "VERSION 2"],
            "BSD 3-Clause License": ["BSD", "REDISTRIBUTION AND USE", "3 CLAUSE"],
            "BSD 2-Clause License": ["BSD", "REDISTRIBUTION AND USE", "2 CLAUSE"],
            "ISC License": ["ISC LICENSE"],
            "Mozilla Public License 2.0": ["MOZILLA PUBLIC LICENSE", "VERSION 2.0"],
            "GNU LGPL v3.0": ["GNU LESSER GENERAL PUBLIC LICENSE", "VERSION 3"],
            "GNU LGPL v2.1": ["GNU LESSER GENERAL PUBLIC LICENSE", "VERSION 2.1"],
            "The Unlicense": ["THIS IS FREE AND UNENCUMBERED SOFTWARE"],
            "Creative Commons": ["CREATIVE COMMONS"]
        }
        
        # Check for license patterns
        detected_license = None
        for license_name, patterns in license_patterns.items():
            if all(pattern in content_upper for pattern in patterns):
                detected_license = license_name
                break
        
        # If we detected a specific license, use it
        if detected_license:
            license_info["name"] = detected_license
        else:
            # Try to extract meaningful license information from the content
            # Look for the first substantial line that might indicate the license
            for line in content_lines[:10]:  # Check first 10 lines
                line_clean = line.strip()
                if not line_clean:
                    continue
                    
                # Skip common boilerplate
                if any(skip in line_clean.upper() for skip in [
                    "COPYRIGHT (C)", "ALL RIGHTS RESERVED", "THE SOFTWARE IS PROVIDED",
                    "WITHOUT WARRANTY", "IN NO EVENT SHALL", "LIABILITY"
                ]):
                    continue
                    
                # Look for license-indicating lines
                if any(indicator in line_clean.upper() for indicator in [
                    "LICENSE", "LICENCE", "TERMS", "PERMISSION", "REDISTRIBUTION"
                ]):
                    # Clean up the line and use it if it's reasonable length
                    if 10 <= len(line_clean) <= 80:
                        license_info["name"] = line_clean
                        break
            
            # Final fallback: if we have a license file but couldn't extract info,
            # just indicate that license information is available
            if "name" not in license_info:
                license_info["name"] = "See license file"
        
        return license_info
 
    def exec(self, prep_res):
        output_path = prep_res["output_path"]
        index_content = prep_res["index_content"]
        chapter_files = prep_res["chapter_files"]
        beginner_friendly_episode = prep_res["beginner_friendly_episode"]
        publish_to_nostr = prep_res["publish_to_nostr"] # Get the Nostr flag

        print(f"Combining tutorial into directory: {output_path}")
        # Rely on Node's built-in retry/fallback
        os.makedirs(output_path, exist_ok=True)

        # Watermark text
        watermark = "\n\nWiki generated by: CoDoC"

        # Write index.md
        index_filepath = os.path.join(output_path, "index.md")

        print(f"repo_url in combineTutorial: {prep_res.keys()}, repo_url: {prep_res['repo_url']}")
        if publish_to_nostr:
            asyncio.run(publish_long_form_content_event("index", index_content + watermark, prep_res["repo_url"]))
            print(f"  - Published index.md to Nostr.")

        with open(index_filepath, "w", encoding="utf-8") as f:
            f.write(index_content + watermark)
        print(f"  - Wrote {index_filepath}")

        # Write chapter files
        for chapter_info in chapter_files:
            chapter_filepath = os.path.join(output_path, chapter_info["filename"])
            if publish_to_nostr:
                title = chapter_info["filename"]
                asyncio.run(publish_long_form_content_event(title, chapter_info["content"] + watermark, prep_res["repo_url"]))
                print(f"  - Published {title} to Nostr.")

            with open(chapter_filepath, "w", encoding="utf-8") as f:
                f.write(chapter_info["content"] + watermark)
            print(f"  - Wrote {chapter_filepath}")

        # Write beginner-friendly episode
        if beginner_friendly_episode:
            episode_filepath = os.path.join(output_path, "beginner_friendly_episode.md")
            if publish_to_nostr:
                title = os.path.basename(episode_filepath).replace('.md', '')
                asyncio.run(publish_long_form_content_event(title, beginner_friendly_episode + watermark, prep_res["repo_url"]))
                print(f"  - Published {title} to Nostr.")

            with open(episode_filepath, "w", encoding="utf-8") as f:
                f.write(beginner_friendly_episode + watermark)
            print(f"  - Wrote {episode_filepath}")
                
        return output_path  # Return the final path

    def post(self, shared, prep_res, exec_res):
        shared["final_output_dir"] = exec_res  # Store the output path
        print(f"\nTutorial generation complete! Files are in: {exec_res}")


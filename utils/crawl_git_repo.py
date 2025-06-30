import os
import tempfile
import shutil
import fnmatch
import git
from typing import Union, Set, List, Dict, Tuple, Any
from urllib.parse import urlparse


def crawl_git_repo(
    repo_url: str, 
    token: str = None, 
    max_file_size: int = 1 * 1024 * 1024,  # 1 MB
    use_relative_paths: bool = False,
    include_patterns: Union[str, Set[str]] = None,
    exclude_patterns: Union[str, Set[str]] = None,
    branch: str = None,
    subdirectory: str = None
):
    """
    Crawl files from a Git repository by cloning it locally.
    
    This function works with any Git server (GitHub, GitLab, Bitbucket, etc.)
    and avoids API rate limits by cloning the repository directly.

    Args:
        repo_url (str): URL of the Git repository 
                       (e.g., 'https://github.com/user/repo.git' or 'git@github.com:user/repo.git')
        token (str, optional): Personal access token for private repositories.
                              For HTTPS URLs, will be used for authentication.
        max_file_size (int, optional): Maximum file size in bytes to include (default: 1 MB)
        use_relative_paths (bool, optional): If True, file paths will be relative to subdirectory
        include_patterns (str or set of str, optional): Pattern(s) for files to include (e.g., "*.py", {"*.md", "*.txt"})
        exclude_patterns (str or set of str, optional): Pattern(s) for files to exclude
        branch (str, optional): Specific branch or commit to checkout. If None, uses default branch
        subdirectory (str, optional): Specific subdirectory within the repo to crawl

    Returns:
        dict: Dictionary with files and statistics
              {
                  "files": {filepath: content, ...},
                  "stats": {
                      "downloaded_count": int,
                      "skipped_count": int,
                      "skipped_files": [(path, size), ...],
                      "base_path": str,
                      "include_patterns": set,
                      "exclude_patterns": set,
                      "source": "git_clone"
                  }
              }
    """
    # Convert single pattern to set
    if include_patterns and isinstance(include_patterns, str):
        include_patterns = {include_patterns}
    if exclude_patterns and isinstance(exclude_patterns, str):
        exclude_patterns = {exclude_patterns}

    def should_include_file(file_path: str, file_name: str) -> bool:
        """Determine if a file should be included based on patterns"""
        # If no include patterns are specified, include all files
        if not include_patterns:
            include_file = True
        else:
            # Check if file matches any include pattern
            include_file = any(fnmatch.fnmatch(file_name, pattern) for pattern in include_patterns)

        # If exclude patterns are specified, check if file should be excluded
        if exclude_patterns and include_file:
            # Exclude if file matches any exclude pattern
            exclude_file = any(fnmatch.fnmatch(file_path, pattern) for pattern in exclude_patterns)
            return not exclude_file

        return include_file

    def prepare_repo_url_with_token(repo_url: str, token: str) -> str:
        """Prepare repository URL with authentication token for HTTPS URLs"""
        if not token or repo_url.startswith("git@"):
            return repo_url
            
        parsed = urlparse(repo_url)
        if parsed.scheme in ['http', 'https']:
            # Insert token into HTTPS URL
            netloc_with_token = f"{token}@{parsed.netloc}"
            return f"{parsed.scheme}://{netloc_with_token}{parsed.path}"
        
        return repo_url

    # Prepare repository URL with authentication if needed
    clone_url = prepare_repo_url_with_token(repo_url, token)
    
    files = {}
    skipped_files = []

    # Clone repository to temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            print(f"Cloning repository {repo_url} to temporary directory: {temp_dir}")
            
            # Clone the repository
            repo = git.Repo.clone_from(clone_url, temp_dir, depth=1)
            
            # Checkout specific branch/commit if specified
            if branch:
                try:
                    repo.git.checkout(branch)
                    print(f"Checked out branch/commit: {branch}")
                except git.exc.GitCommandError as e:
                    print(f"Warning: Could not checkout {branch}: {e}")
                    print("Continuing with default branch...")
            
            # Extract commit information
            try:
                current_commit = repo.head.commit
                commit_hash = current_commit.hexsha
                commit_short_hash = current_commit.hexsha[:7]
                commit_message = current_commit.message.strip()
                commit_author = str(current_commit.author)
                commit_date = current_commit.committed_datetime.isoformat()
                print(f"Repository at commit: {commit_short_hash} - {commit_message[:50]}...")
            except Exception as e:
                print(f"Warning: Could not extract commit information: {e}")
                commit_hash = "unknown"
                commit_short_hash = "unknown"
                commit_message = "unknown"
                commit_author = "unknown"
                commit_date = "unknown"

            # Determine the directory to crawl
            crawl_dir = temp_dir
            if subdirectory:
                subdirectory_path = os.path.join(temp_dir, subdirectory)
                if os.path.exists(subdirectory_path):
                    crawl_dir = subdirectory_path
                    print(f"Crawling subdirectory: {subdirectory}")
                else:
                    print(f"Warning: Subdirectory '{subdirectory}' not found, crawling entire repository")

            # Walk through the directory and collect files
            for root, dirs, filenames in os.walk(crawl_dir):
                # Skip .git directory
                if '.git' in dirs:
                    dirs.remove('.git')
                
                for filename in filenames:
                    abs_path = os.path.join(root, filename)
                    
                    # Calculate relative path
                    if use_relative_paths and subdirectory:
                        # Relative to subdirectory
                        rel_path = os.path.relpath(abs_path, crawl_dir)
                    else:
                        # Relative to repository root
                        rel_path = os.path.relpath(abs_path, temp_dir)
                        if subdirectory and rel_path.startswith(subdirectory):
                            # If we're in a subdirectory but not using relative paths,
                            # keep the subdirectory in the path
                            pass

                    # Check file size
                    try:
                        file_size = os.path.getsize(abs_path)
                    except OSError:
                        continue

                    if file_size > max_file_size:
                        skipped_files.append((rel_path, file_size))
                        print(f"Skipping {rel_path}: size {file_size} exceeds limit {max_file_size}")
                        continue

                    # Check include/exclude patterns
                    if not should_include_file(rel_path, filename):
                        continue

                    # Read file content
                    try:
                        with open(abs_path, "r", encoding="utf-8-sig") as f:
                            content = f.read()
                        files[rel_path] = content
                        print(f"Added {rel_path} ({file_size} bytes)")
                    except Exception as e:
                        print(f"Failed to read {rel_path}: {e}")

        except git.exc.GitCommandError as e:
            error_msg = f"Failed to clone repository: {e}"
            print(error_msg)
            return {
                "files": {},
                "stats": {
                    "error": error_msg,
                    "downloaded_count": 0,
                    "skipped_count": 0,
                    "skipped_files": [],
                    "base_path": subdirectory if use_relative_paths else None,
                    "include_patterns": include_patterns,
                    "exclude_patterns": exclude_patterns,
                    "source": "git_clone"
                },
                "git_info": {
                    "commit_hash": "unknown",
                    "commit_short_hash": "unknown",
                    "commit_message": "unknown",
                    "commit_author": "unknown",
                    "commit_date": "unknown",
                    "repository_url": repo_url
                }
            }
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            print(error_msg)
            return {
                "files": {},
                "stats": {
                    "error": error_msg,
                    "downloaded_count": 0,
                    "skipped_count": 0,
                    "skipped_files": [],
                    "base_path": subdirectory if use_relative_paths else None,
                    "include_patterns": include_patterns,
                    "exclude_patterns": exclude_patterns,
                    "source": "git_clone"
                },
                "git_info": {
                    "commit_hash": "unknown",
                    "commit_short_hash": "unknown",
                    "commit_message": "unknown",
                    "commit_author": "unknown",
                    "commit_date": "unknown",
                    "repository_url": repo_url
                }
            }

    return {
        "files": files,
        "stats": {
            "downloaded_count": len(files),
            "skipped_count": len(skipped_files),
            "skipped_files": skipped_files,
            "base_path": subdirectory if use_relative_paths else None,
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
            "source": "git_clone"
        },
        "git_info": {
            "commit_hash": commit_hash,
            "commit_short_hash": commit_short_hash,
            "commit_message": commit_message,
            "commit_author": commit_author,
            "commit_date": commit_date,
            "repository_url": repo_url
        }
    }


def parse_github_url(repo_url: str) -> Tuple[str, str, str]:
    """
    Parse GitHub URL to extract repository URL, branch, and subdirectory.
    
    Args:
        repo_url (str): GitHub URL (e.g., 'https://github.com/user/repo/tree/branch/path')
        
    Returns:
        tuple: (clean_repo_url, branch, subdirectory)
    """
    # Handle GitHub URLs with tree/branch/path structure
    if '/tree/' in repo_url:
        # Split at /tree/ to separate repo from branch/path
        repo_part, tree_part = repo_url.split('/tree/', 1)
        
        # Clean repo URL (add .git if not present)
        clean_repo_url = repo_part
        if not clean_repo_url.endswith('.git'):
            clean_repo_url += '.git'
        
        # Parse tree part to extract branch and path
        tree_parts = tree_part.split('/')
        branch = tree_parts[0]
        subdirectory = '/'.join(tree_parts[1:]) if len(tree_parts) > 1 else None
        
        return clean_repo_url, branch, subdirectory
    else:
        # Simple repository URL
        clean_repo_url = repo_url
        if not clean_repo_url.endswith('.git') and 'github.com' in clean_repo_url:
            clean_repo_url += '.git'
        return clean_repo_url, None, None





# Example usage
if __name__ == "__main__":
    # Get token from environment variable
    github_token = os.environ.get("GITHUB_TOKEN")
    
    # Test with different URL formats
    test_urls = [
        "https://github.com/microsoft/autogen.git",
        "https://github.com/microsoft/autogen/tree/main/python/packages/autogen-core",
        "git@github.com:microsoft/autogen.git"
    ]
    
    for url in test_urls:
        print(f"\n--- Testing URL: {url} ---")
        # Parse GitHub URL to extract components
        clean_repo_url, branch, subdirectory = parse_github_url(url)
        result = crawl_git_repo(
            repo_url=clean_repo_url,
            token=github_token,
            include_patterns={"*.py", "*.md"},
            max_file_size=50000,  # 50KB for testing
            branch=branch,
            subdirectory=subdirectory
        )
        
        print(f"Files found: {result['stats']['downloaded_count']}")
        print(f"Files skipped: {result['stats']['skipped_count']}")
        if result.get('files'):
            print("Sample files:")
            for i, filepath in enumerate(list(result['files'].keys())[:3]):
                print(f"  - {filepath}")

"""Filesystem tree context builder for RAG pipeline with git history integration."""

import subprocess
from pathlib import Path
from typing import Dict, List, Optional
import sqlite3
from collections import defaultdict

from fs_rag.core import get_config, get_logger

logger = get_logger(__name__)


class GitHistoryReader:
    """Reads git history to understand file changes and relationships."""

    def __init__(self, repo_path: Optional[Path] = None):
        self.repo_path = repo_path or Path.cwd()

    def get_file_change_frequency(self, file_pattern: Optional[str] = None) -> Dict[str, int]:
        """Get change frequency for files."""
        try:
            cmd = ["git", "log", "--name-only", "--pretty=format:"]
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.debug(f"Git command failed: {result.stderr}")
                return {}

            file_changes = defaultdict(int)
            for line in result.stdout.strip().split("\n"):
                if line.strip() and not line.startswith("commit"):
                    file_changes[line.strip()] += 1

            if file_pattern:
                return {k: v for k, v in file_changes.items() if file_pattern in k}
            
            return dict(file_changes)
        except Exception as e:
            logger.warning(f"Error reading git history: {e}")
            return {}

    def get_recent_commits(self, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent commit information."""
        try:
            cmd = ["git", "log", "--oneline", "-n", str(limit)]
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return []

            commits = []
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.split(maxsplit=1)
                    if len(parts) == 2:
                        commits.append({"sha": parts[0], "message": parts[1]})
            
            return commits
        except Exception as e:
            logger.warning(f"Error getting recent commits: {e}")
            return []

    def get_files_changed_in_commit(self, commit_sha: str) -> List[str]:
        """Get files changed in a specific commit."""
        try:
            cmd = ["git", "show", "--name-only", "--pretty=format:", commit_sha]
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return []

            return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        except Exception as e:
            logger.warning(f"Error getting files from commit: {e}")
            return []


class FilesystemTreeBuilder:
    """Builds hierarchical filesystem tree from indexed file paths."""

    def __init__(self, index_db_path: Path):
        self.index_db_path = index_db_path
        self.git_reader = GitHistoryReader()

    def _get_indexed_files(self) -> List[str]:
        """Query indexed file paths from the database."""
        try:
            conn = sqlite3.connect(self.index_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT path FROM files WHERE is_indexed = 1 ORDER BY path")
            paths = [row[0] for row in cursor.fetchall()]
            conn.close()
            return paths
        except Exception as e:
            logger.warning(f"Error querying indexed files: {e}")
            return []

    def _build_tree_structure(self, paths: List[str], max_depth: Optional[int] = None) -> Dict:
        """Build a hierarchical tree structure from file paths."""
        tree = {}

        for path in paths:
            parts = Path(path).parts
            
            if max_depth and len(parts) > max_depth:
                parts = parts[:max_depth]

            current = tree
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Add file with metadata
            filename = parts[-1] if parts else path
            current[filename] = {"__file__": True, "__path__": path}

        return tree

    def _tree_to_string(self, tree: Dict, prefix: str = "", is_last: bool = True) -> List[str]:
        """Convert tree structure to ASCII tree string lines."""
        lines = []
        items = sorted(tree.items())

        for i, (key, value) in enumerate(items):
            is_last_item = i == len(items) - 1
            
            connector = "└── " if is_last_item else "├── "
            extension = "    " if is_last_item else "│   "

            if isinstance(value, dict) and "__file__" in value:
                lines.append(f"{prefix}{connector}{key}")
            else:
                lines.append(f"{prefix}{connector}{key}/")
                
                if isinstance(value, dict):
                    sub_lines = self._tree_to_string(
                        value,
                        prefix + extension,
                        is_last_item
                    )
                    lines.extend(sub_lines)

        return lines

    def build_context_tree(
        self,
        max_depth: Optional[int] = None,
        include_git_info: bool = True,
        limit_files: Optional[int] = None
    ) -> str:
        """Build a formatted filesystem tree from indexed files."""
        paths = self._get_indexed_files()

        if not paths:
            return "No indexed files found."

        if limit_files:
            paths = paths[:limit_files]

        tree = self._build_tree_structure(paths, max_depth)

        lines = ["Indexed Filesystem Structure:"]
        lines.extend(self._tree_to_string(tree))

        if include_git_info:
            commits = self.git_reader.get_recent_commits(limit=5)
            if commits:
                lines.append("\n📝 Recent Changes:")
                for commit in commits:
                    lines.append(f"  • {commit['message']} ({commit['sha'][:7]})")

        return "\n".join(lines)

    def get_directory_structure_for_files(self, file_paths: List[str]) -> str:
        """Build a minimal tree containing only specified files."""
        if not file_paths:
            return "No files specified."

        by_dir = defaultdict(list)
        for file_path in file_paths:
            path_obj = Path(file_path)
            by_dir[str(path_obj.parent)].append(path_obj.name)

        lines = ["Estrutura de arquivos relevantes:"]
        for directory in sorted(by_dir.keys()):
            lines.append(f"\n{directory}/")
            for filename in sorted(by_dir[directory]):
                lines.append(f"  ├── {filename}")

        return "\n".join(lines)


def get_filesystem_tree_builder() -> FilesystemTreeBuilder:
    """Get a filesystem tree builder instance."""
    config = get_config()
    index_db_path = config.index_dir / "index.db"
    return FilesystemTreeBuilder(index_db_path)


def format_context_with_tree(
    base_context: str,
    retrieved_files: List[str],
    max_tree_lines: int = 30
) -> str:
    """Enhance base context with a filesystem tree view."""
    try:
        builder = get_filesystem_tree_builder()
        file_tree = builder.get_directory_structure_for_files(retrieved_files)
        
        tree_lines = file_tree.split("\n")
        if len(tree_lines) > max_tree_lines:
            tree_lines = tree_lines[:max_tree_lines]
            tree_lines.append(f"\n... ({len(file_tree.split(chr(10))) - max_tree_lines} more items)")

        enhanced_context = f"{base_context}\n\n{'='*60}\n{chr(10).join(tree_lines)}\n{'='*60}"
        return enhanced_context
    except Exception as e:
        logger.debug(f"Error enhancing context with tree: {e}")
        return base_context

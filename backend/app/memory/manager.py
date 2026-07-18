from typing import Any, Dict, Optional

class MemoryManager:
    """In-memory Working Memory Manager for active agent execution sessions."""
    def __init__(self):
        self._working_memory: Dict[str, Dict[str, Any]] = {}

    def set_working_memory(self, session_id: str, key: str, value: Any) -> None:
        """Store working memory key-value pair for an active session."""
        if session_id not in self._working_memory:
            self._working_memory[session_id] = {}
        self._working_memory[session_id][key] = value

    def get_working_memory(self, session_id: str, key: str) -> Optional[Any]:
        """Fetch working memory key-value pair for an active session."""
        return self._working_memory.get(session_id, {}).get(key)

    def clear_working_memory(self, session_id: str) -> None:
        """Clear working memory for a session upon execution completion."""
        if session_id in self._working_memory:
            del self._working_memory[session_id]


_memory_manager_instance: Optional[MemoryManager] = None

def get_memory_manager() -> MemoryManager:
    """Singleton getter for active working MemoryManager."""
    global _memory_manager_instance
    if _memory_manager_instance is None:
        _memory_manager_instance = MemoryManager()
    return _memory_manager_instance

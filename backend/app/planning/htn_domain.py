from typing import List, Dict, Any, Callable, Optional, Union
from dataclasses import dataclass, field

@dataclass
class Precondition:
    name: str
    predicate: Callable[[Dict[str, Any]], bool]

    def evaluate(self, state: Dict[str, Any]) -> bool:
        try:
            return self.predicate(state)
        except Exception:
            return False

@dataclass
class PrimitiveTask:
    name: str
    operator_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    tool_binding: Optional[str] = None

@dataclass
class CompoundTask:
    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Method:
    name: str
    target_compound_task: str
    preconditions: List[Precondition] = field(default_factory=list)
    subtasks: List[Union[CompoundTask, PrimitiveTask]] = field(default_factory=list)

    def is_applicable(self, state: Dict[str, Any]) -> bool:
        return all(p.evaluate(state) for p in self.preconditions)

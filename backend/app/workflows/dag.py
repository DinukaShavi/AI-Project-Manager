from typing import Any, Dict, List, Set

class WorkflowNode:
    def __init__(
        self,
        node_id: str,
        name: str,
        step_type: str, # 'agent' or 'tool'
        target: str,    # e.g. 'tpm', 'code_analyst', 'slack_post_message'
        input_params: Dict[str, Any] = None,
        depends_on: List[str] = None
    ):
        self.node_id = node_id
        self.name = name
        self.step_type = step_type.lower()
        self.target = target
        self.input_params = input_params or {}
        self.depends_on = depends_on or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "step_type": self.step_type,
            "target": self.target,
            "input_params": self.input_params,
            "depends_on": self.depends_on
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowNode":
        return cls(
            node_id=data["node_id"],
            name=data["name"],
            step_type=data["step_type"],
            target=data["target"],
            input_params=data.get("input_params", {}),
            depends_on=data.get("depends_on", [])
        )


class WorkflowDAG:
    def __init__(self):
        """Directed Acyclic Graph managing workflow nodes and topological execution levels."""
        self.nodes: Dict[str, WorkflowNode] = {}

    def add_node(self, node: WorkflowNode) -> None:
        """Add a step node to the DAG."""
        self.nodes[node.node_id] = node

    def validate_dag(self) -> None:
        """Validate DAG integrity, ensuring all dependency nodes exist and no cycles exist."""
        # 1. Check dependency references
        for node_id, node in self.nodes.items():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    raise ValueError(f"Workflow node '{node_id}' depends on non-existent node '{dep}'.")

        # 2. Detect cycles using DFS
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(curr: str):
            visited.add(curr)
            rec_stack.add(curr)
            
            for dep in self.nodes[curr].depends_on:
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in rec_stack:
                    return True
                    
            rec_stack.remove(curr)
            return False

        for node_id in self.nodes:
            if node_id not in visited:
                if dfs(node_id):
                    raise ValueError("Cycle detected in WorkflowDAG execution graph!")

    def get_execution_levels(self) -> List[List[WorkflowNode]]:
        """Return topologically sorted node levels suitable for parallel step execution."""
        self.validate_dag()
        
        in_degree = {node_id: len(node.depends_on) for node_id, node in self.nodes.items()}
        # Map node_id -> list of child node_ids dependent on it
        children: Dict[str, List[str]] = {node_id: [] for node_id in self.nodes}
        for node_id, node in self.nodes.items():
            for dep in node.depends_on:
                children[dep].append(node_id)

        current_level = [node_id for node_id, deg in in_degree.items() if deg == 0]
        levels: List[List[WorkflowNode]] = []

        while current_level:
            levels.append([self.nodes[nid] for nid in current_level])
            next_level = []
            
            for nid in current_level:
                for child in children[nid]:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        next_level.append(child)
                        
            current_level = next_level

        return levels

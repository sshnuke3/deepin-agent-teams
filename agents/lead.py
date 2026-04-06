"""
agents/lead.py - Lead Agent（主智能体）
"""
from .base import BaseAgent
from typing import List, Dict, Any


class LeadAgent(BaseAgent):
    """
    Lead Agent 负责：
    1. 接收用户需求
    2. 拆解任务
    3. 调用其他 Agent（Researcher/Coder）
    4. 整合结果返回用户
    """

    def __init__(self, researcher: 'ResearcherAgent', coder: 'CoderAgent', verbose: bool = True):
        super().__init__("lead", verbose=verbose)
        self.researcher = researcher
        self.coder = coder

    def decompose_task(self, user_request: str) -> List[Dict[str, Any]]:
        """
        将用户需求拆解为子任务
        
        Returns:
            子任务列表，每项包含 type, description, assignee
        """
        prompt = f"""用户需求：{user_request}

请将上述需求拆解为具体的子任务。
输出格式为 JSON 数组，每个任务包含：
- type: "research" | "code" | "summarize"
- description: 任务描述
- assignee: "researcher" | "coder"

只输出 JSON，不要其他内容。"""

        response = self.chat(prompt)
        
        # 简单解析（实际项目应该用 json.parse）
        import json
        try:
            tasks = json.loads(response)
            return tasks if isinstance(tasks, list) else []
        except:
            return [{"type": "summarize", "description": response, "assignee": "lead"}]

    def handle(self, user_request: str) -> str:
        """处理用户请求的主入口"""
        # Step 1: 拆解任务
        tasks = self.decompose_task(user_request)
        
        if self.verbose:
            print(f"\n[LEAD] 拆解出 {len(tasks)} 个子任务:")
            for i, t in enumerate(tasks, 1):
                print(f"  {i}. [{t.get('assignee', 'unknown')}] {t.get('description', '')[:50]}...")

        # Step 2: 分发任务给 Researcher 和 Coder
        results = {}
        
        for task in tasks:
            assignee = task.get("assignee", "lead")
            description = task.get("description", "")
            
            if assignee == "researcher":
                results["researcher"] = self.researcher.chat(description)
            elif assignee == "coder":
                results["coder"] = self.coder.chat(description)
            else:
                # lead 自己处理
                results["lead"] = self.chat(f"请完成以下任务：{description}")

        # Step 3: 整合结果
        final_prompt = f"""用户原始需求：{user_request}

各 Agent 的执行结果：
{self._format_results(results)}

请整合以上结果，给出完整的最终回答。"""

        final_response = self.chat(final_prompt)
        return final_response

    def _format_results(self, results: Dict[str, str]) -> str:
        formatted = []
        for agent, result in results.items():
            formatted.append(f"=== {agent.upper()} ===\n{result}")
        return "\n\n".join(formatted)

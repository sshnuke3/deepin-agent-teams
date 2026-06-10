用户需求：{user_request}

{tools_section}
请将上述需求分解为具体的子任务。

输出格式为纯 JSON：
{{
  "tasks": [
    {{
      "id": "task-1",
      "description": "详细的任务描述",
      "capabilities_needed": ["cap1", "cap2"],
      "tool_name": "使用的工具名（如有）",
      "params": {{}},
      "type": "任务类型"
    }}
  ],
  "spawn_plan": [
    {{
      "agent_type": "researcher | coder | general",
      "agent_label": "如 researcher-1",
      "tasks": ["task-id-1"]
    }}
  ],
  "summary": "一句话总结"
}}

可用能力：file_reader, dir_scanner, file_writer, code_analyzer, ast_parser,
syntax_checker, dependency_analyzer, shell_executor, git_analyzer,
web_search, web_fetcher, doc_generator, markdown_writer

capability → agent_type 映射：
- web_search/web_fetcher → researcher
- code_analyzer/ast_parser/syntax_checker/dependency_analyzer/git_analyzer → coder
- file_reader/dir_scanner/shell_executor/git_analyzer → general

约束：
1. 每个任务必须有 id、description、capabilities_needed
2. description 要足够详细，让 Worker 能独立执行
3. 不要分解超过 8 个子任务
4. spawn_plan 中的 tasks 引用上面定义的 id
5. 只输出 JSON，不要多余文字

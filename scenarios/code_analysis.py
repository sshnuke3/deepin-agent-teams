"""
scenarios/code_analysis.py - 场景一：项目代码分析 + 文档生成
"""
import os
import glob
from agents import LeadAgent, ResearcherAgent, CoderAgent


class CodeAnalysisScenario:
    """
    场景一：代码分析 + 文档生成

    用户输入一个项目路径，系统自动：
    1. Lead 拆解任务
    2. Researcher 读取文件结构
    3. Coder 分析核心代码
    4. Lead 整合输出文档
    """

    def __init__(self, researcher: ResearcherAgent, coder: CoderAgent, lead: LeadAgent):
        self.researcher = researcher
        self.coder = coder
        self.lead = lead

    def run(self, project_path: str) -> str:
        """执行代码分析场景"""
        if not os.path.exists(project_path):
            return f"❌ 项目路径不存在: {project_path}"

        print(f"\n{'='*50}")
        print(f"🔍 场景一：代码分析 + 文档生成")
        print(f"📁 项目路径: {project_path}")
        print(f"{'='*50}\n")

        # Step 1: Lead 拆解任务
        print("[Step 1/4] Lead Agent 拆解任务...")
        tasks = self.lead.decompose_task(
            f"分析项目 {project_path}，生成完整的项目文档"
        )
        print(f"  → 拆解出 {len(tasks)} 个子任务\n")

        results = {}

        # Step 2: Researcher 读取项目结构
        print("[Step 2/4] Researcher Agent 读取项目结构...")
        tree_result = self._get_project_tree(project_path)
        print(f"  → 获取到 {len(tree_result.split(chr(10)))} 行结构信息\n")
        results["structure"] = tree_result

        # Step 3: Coder 分析核心代码
        print("[Step 3/4] Coder Agent 分析核心代码...")
        core_analysis = self._analyze_core_files(project_path)
        results["analysis"] = core_analysis
        print(f"  → 分析完成\n")

        # Step 4: Lead 整合生成文档
        print("[Step 4/4] Lead Agent 生成项目文档...")
        doc = self.lead.integrate_analysis(
            project_path=project_path,
            structure=tree_result,
            code_analysis=core_analysis
        )

        print(f"\n{'='*50}")
        print("✅ 场景一执行完成")
        print(f"{'='*50}\n")
        return doc

    def _get_project_tree(self, project_path: str) -> str:
        """获取项目文件树"""
        tree_lines = []
        for root, dirs, files in os.walk(project_path):
            # 过滤隐藏目录和 __pycache__
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            level = root.replace(project_path, '').count(os.sep)
            indent = '  ' * level
            tree_lines.append(f"{indent}{os.path.basename(root)}/")
            
            sub_indent = '  ' * (level + 1)
            for file in sorted(files):
                if not file.startswith('.') and not file.endswith('.pyc'):
                    tree_lines.append(f"{sub_indent}{file}")
        
        tree_str = '\n'.join(tree_lines[:100])  # 限制 100 行
        
        # 让 Researcher 分析这个结构
        analysis_prompt = f"""请分析以下项目结构，识别：
1. 项目类型（Web/CLI/库/游戏等）
2. 主要模块和它们的职责
3. 入口文件
4. 依赖管理方式

项目结构：
{tree_str}"""
        
        return self.researcher.chat(analysis_prompt)

    def _analyze_core_files(self, project_path: str) -> str:
        """分析核心代码文件"""
        # 找出所有 Python 文件，按大小排序，取最大的 5 个
        py_files = []
        for root, _, files in os.walk(project_path):
            if '__pycache__' in root:
                continue
            for f in files:
                if f.endswith('.py') and not f.startswith('.'):
                    fp = os.path.join(root, f)
                    try:
                        size = os.path.getsize(fp)
                        py_files.append((fp, size))
                    except:
                        pass
        
        py_files.sort(key=lambda x: x[1], reverse=True)
        top_files = py_files[:5]
        
        analyses = []
        for fp, size in top_files:
            rel_path = os.path.relpath(fp, project_path)
            print(f"  分析: {rel_path} ({size/1024:.1f} KB)")
            
            content = ""
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    content = f.read(8000)  # 限制 8K 字符
            except:
                content = "(无法读取)"
            
            prompt = f"""分析以下代码文件，输出简明摘要：
文件：{rel_path}

代码：
{content}

输出格式：
- 文件功能：
- 主要函数/类：
- 依赖模块："""
            
            result = self.coder.chat(prompt)
            analyses.append(f"## {rel_path}\n{result}\n")
        
        return '\n'.join(analyses)

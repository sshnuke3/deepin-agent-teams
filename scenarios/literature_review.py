"""
scenarios/literature_review.py - 场景二：文献综述助手
"""
import os
from agents import LeadAgent, ResearcherAgent, CoderAgent


class LiteratureReviewScenario:
    """
    场景二：文献综述助手

    用户提供多个 PDF/文本文件路径 + 研究问题，系统自动：
    1. Lead 拆解任务
    2. Researcher 并行读取各文献
    3. Lead 综合分析，生成综述报告
    """

    def __init__(self, researcher: ResearcherAgent, coder: CoderAgent, lead: LeadAgent):
        self.researcher = researcher
        self.coder = coder
        self.lead = lead

    def run(self, file_paths: list, research_question: str) -> str:
        """执行文献综述场景"""
        if not file_paths:
            return "❌ 未提供文件路径"

        print(f"\n{'='*50}")
        print(f"📚 场景二：文献综述助手")
        print(f"❓ 研究问题: {research_question}")
        print(f"📄 文件数量: {len(file_paths)}")
        print(f"{'='*50}\n")

        results = {}

        # Step 1: Researcher 并行读取各文献
        print(f"[Step 1/3] Researcher Agent 读取 {len(file_paths)} 个文献...")
        for i, fp in enumerate(file_paths, 1):
            print(f"  [{i}/{len(file_paths)}] 读取: {os.path.basename(fp)}")
            
            if not os.path.exists(fp):
                results[fp] = f"文件不存在: {fp}"
                continue
            
            # 读取文件内容
            try:
                if fp.endswith('.pdf'):
                    results[fp] = self._extract_pdf(fp)
                else:
                    with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(50000)
                    results[fp] = content
            except Exception as e:
                results[fp] = f"读取失败: {e}"

        print(f"  → 完成读取\n")

        # Step 2: 各文献提取摘要
        print("[Step 2/3] Researcher Agent 提取各文献关键信息...")
        summaries = {}
        for fp, content in results.items():
            key_info = self._extract_key_info(fp, content, research_question)
            summaries[os.path.basename(fp)] = key_info
            print(f"  ✓ {os.path.basename(fp)}")

        # Step 3: Lead Agent 生成综述
        print("[Step 3/3] Lead Agent 生成综述报告...")
        report = self.lead.integrate_literature(
            question=research_question,
            summaries=summaries
        )

        print(f"\n{'='*50}")
        print("✅ 场景二执行完成")
        print(f"{'='*50}\n")
        return report

    def _extract_pdf(self, pdf_path: str) -> str:
        """提取 PDF 文本（简单方式，依赖 pdfminer 或纯文本）"""
        # 优先尝试用 pdftotext
        import subprocess
        try:
            result = subprocess.run(
                ['pdftotext', pdf_path, '-'],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return result.stdout[:50000]
        except:
            pass
        return "(PDF 文件，需用 PDF 工具提取)"

    def _extract_key_info(self, fp: str, content: str, question: str) -> str:
        """从文献中提取与研究问题相关的信息"""
        prompt = f"""研究问题：{question}

文件：{os.path.basename(fp)}

内容：
{content[:30000]}

请提取：
1. 文献的主要论点/发现
2. 与研究问题相关的内容
3. 支持或反驳研究问题的证据

输出格式：结构化摘要，300字以内"""
        return self.researcher.chat(prompt)

    def integrate_literature(self, question: str, summaries: dict) -> str:
        """整合多篇文献，生成综述"""
        summary_text = '\n'.join([
            f"## {title}\n{summary}"
            for title, summary in summaries.items()
        ])
        
        prompt = f"""研究问题：{question}

文献综述：

{summary_text}

请生成结构化的文献综述报告，包含：
1. 研究背景
2. 各文献的核心发现（对比表）
3. 文献间的观点异同
4. 综合结论
5. 研究空白和建议

格式：Markdown"""
        return self.lead.chat(prompt)

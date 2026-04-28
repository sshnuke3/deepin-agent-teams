"""
屏幕 OCR 模块
使用 PaddleOCR/PaddleOCR-VL 进行屏幕内容识别
"""
import os
import sys
from typing import Dict, List, Optional, Tuple

# 懒加载 paddleocr，避免启动慢
_paddle_ocr_cache = None


def get_ocr_engine(lang: str = "ch", use_angle_cls: bool = True):
    """获取或创建 OCR 引擎（带缓存）"""
    global _paddle_ocr_cache

    if _paddle_ocr_cache is None:
        try:
            from paddleocr import PaddleOCR
            _paddle_ocr_cache = PaddleOCR(
                lang=lang,
                use_angle_cls=use_angle_cls,
                show_log=False,
                use_gpu=False,  # 根据环境自动选择
            )
        except ImportError:
            return None

    return _paddle_ocr_cache


def ocr_image(image_path: str, lang: str = "ch") -> Dict:
    """
    对图片进行 OCR 识别

    Args:
        image_path: 图片路径
        lang: 语言 (ch/en/chinese_cht)

    Returns:
        识别结果字典
    """
    result = {
        "image_path": image_path,
        "success": False,
        "texts": [],
        "full_text": "",
        "boxes": [],
        "regions": [],
    }

    ocr = get_ocr_engine(lang)
    if ocr is None:
        result["error"] = "PaddleOCR 未安装，请运行: pip install paddlepaddle paddleocr"
        return result

    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(lang=lang, show_log=False, use_gpu=False)
        ocr_result = ocr.ocr(image_path, cls=True)

        if ocr_result and ocr_result[0]:
            lines = []
            boxes = []
            for line in ocr_result[0]:
                box = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                text = line[1][0]  # 识别出的文字
                confidence = line[1][1]  # 置信度

                result["texts"].append(text)
                result["boxes"].append(box)
                lines.append(text)
                boxes.append({
                    "text": text,
                    "confidence": confidence,
                    "box": box,
                })

            result["regions"] = boxes
            result["full_text"] = "\n".join(lines)
            result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


def ocr_screen(region: Tuple[int, int, int, int] = None, lang: str = "ch") -> Dict:
    """
    截取屏幕并 OCR 识别

    Args:
        region: 截取区域 (x, y, width, height)，None 为全屏
        lang: 语言

    Returns:
        OCR 结果
    """
    from perception.screen_capture import capture_screen

    # 截取屏幕
    image_path = capture_screen(region=region)
    if not image_path:
        return {"success": False, "error": "截图失败"}

    # OCR 识别
    result = ocr_image(image_path, lang=lang)
    result["image_path"] = image_path

    # 清理截图
    try:
        os.remove(image_path)
    except:
        pass

    return result


def extract_text_regions(result: Dict, min_confidence: float = 0.5) -> List[Dict]:
    """提取文本区域，用于理解屏幕内容"""
    regions = []

    for item in result.get("regions", []):
        if item["confidence"] >= min_confidence:
            # 计算区域中心
            box = item["box"]
            center_x = sum(p[0] for p in box) / 4
            center_y = sum(p[1] for p in box) / 4

            regions.append({
                "text": item["text"],
                "confidence": item["confidence"],
                "position": (center_x, center_y),
                "box": box,
            })

    return regions


def understand_screen_context(result: Dict) -> str:
    """
    根据 OCR 结果理解屏幕上下文

    Args:
        result: OCR 结果

    Returns:
        屏幕内容描述
    """
    if not result.get("success"):
        return f"OCR 失败: {result.get('error', '未知错误')}"

    texts = result.get("texts", [])
    if not texts:
        return "屏幕内容为空"

    # 取前 20 行
    preview = "\n".join(texts[:20])

    # 分析内容类型
    content_type = "unknown"
    keywords = {
        "browser": ["搜索", "google", "baidu", "github", "http", "www"],
        "editor": ["def ", "class ", "import ", "function", "{", "}"],
        "mail": ["发件人", "收件人", "主题", "邮箱", "mail"],
        "document": ["标题", "正文", "文档", "第", "章"],
        "terminal": ["$", "#", "ls", "cd", "git", "pip"],
        "error": ["error", "exception", "failed", "错误", "异常"],
    }

    joined = " ".join(texts).lower()
    for ctype, kws in keywords.items():
        if any(kw.lower() in joined for kw in kws):
            content_type = ctype
            break

    return f"""屏幕类型: {content_type}
内容预览:
{preview}
{'[...]' if len(texts) > 20 else ''}
"""


def detect_interactive_elements(result: Dict) -> List[Dict]:
    """
    检测可交互元素（按钮、输入框等）

    Returns:
        可交互元素列表
    """
    elements = []

    # 基于关键词检测
    for text in result.get("texts", []):
        text_lower = text.lower().strip()

        # 按钮关键词
        button_keywords = ["确定", "取消", "提交", "发送", "保存", "关闭", "删除",
                          "ok", "cancel", "submit", "save", "close", "delete",
                          "click", "button"]

        if any(kw in text_lower for kw in button_keywords):
            elements.append({
                "type": "button",
                "text": text,
                "actionable": True
            })

        # 输入框关键词（通常是单独的短词）
        if len(text) < 20 and len(text) > 1:
            # 可能是标签或placeholder
            elements.append({
                "type": "field",
                "text": text,
                "actionable": False
            })

    return elements


def test():
    """测试 OCR 功能"""
    print("=== PaddleOCR 测试 ===\n")

    # 检查是否安装
    try:
        import paddle
        print(f"✅ PaddlePaddle: {paddle.__version__}")
    except ImportError:
        print("❌ PaddlePaddle 未安装")
        print("   安装命令: pip install paddlepaddle paddleocr")
        return

    try:
        from paddleocr import PaddleOCR
        print("✅ PaddleOCR 已导入")
    except ImportError as e:
        print(f"❌ PaddleOCR 导入失败: {e}")
        return

    # 测试图片 OCR
    print("\n测试图片 OCR...")

    # 创建一个测试图片
    import subprocess
    try:
        # 创建测试文字图片
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new('RGB', (400, 100), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 30), "Hello World\n测试中文 OCR", fill='black')

        test_image = "/tmp/test_ocr.png"
        img.save(test_image)
        print(f"✅ 测试图片已创建: {test_image}")

        # OCR 识别
        print("\n执行 OCR 识别...")
        result = ocr_image(test_image, lang="en")

        if result["success"]:
            print(f"✅ OCR 成功!")
            print(f"识别文字: {result['full_text']}")
        else:
            print(f"❌ OCR 失败: {result.get('error')}")

        # 清理
        os.remove(test_image)

    except ImportError:
        print("⚠️ PIL 未安装，跳过图片测试")

    # 测试屏幕 OCR
    print("\n测试屏幕 OCR（截取全屏）...")
    try:
        screen_result = ocr_screen()
        if screen_result["success"]:
            print(f"✅ 屏幕 OCR 成功!")
            print(f"识别行数: {len(screen_result['texts'])}")
            print(f"内容预览: {screen_result['full_text'][:200]}...")
        else:
            print(f"⚠️ 屏幕 OCR 失败: {screen_result.get('error')}")
    except Exception as e:
        print(f"⚠️ 屏幕 OCR 出错: {e}")


if __name__ == "__main__":
    test()

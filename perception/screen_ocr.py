"""
屏幕 OCR 模块
使用 PaddleOCR/PaddleOCR-VL 进行屏幕内容识别
支持轻量降级：无 GPU/低内存时使用备用方案
"""
import logging
import os
import subprocess
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# 懒加载
_paddle_ocr_cache = None
_use_ocr = True  # 是否启用 OCR


def is_ocr_available() -> bool:
    """检查 OCR 是否可用"""
    global _use_ocr
    if not _use_ocr:
        return False

    try:
        import paddle
        from paddleocr import PaddleOCR
        return True
    except ImportError:
        _use_ocr = False
        return False


def get_ocr_engine(lang: str = "ch"):
    """获取或创建 OCR 引擎"""
    global _paddle_ocr_cache

    if _paddle_ocr_cache is not None:
        return _paddle_ocr_cache

    if not is_ocr_available():
        return None

    try:
        from paddleocr import PaddleOCR
        # 新版本参数不同
        params = {"lang": lang}
        ocr = PaddleOCR(**params)
        _paddle_ocr_cache = ocr
        return ocr
    except Exception as e:
        print(f"⚠️ PaddleOCR 初始化失败: {e}")
        _use_ocr = False
        return None


def ocr_image(image_path: str, lang: str = "ch") -> Dict:
    """
    对图片进行 OCR 识别

    Args:
        image_path: 图片路径
        lang: 语言

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
        "method": "none",
    }

    if not is_ocr_available():
        result["error"] = "PaddleOCR 未安装，跳过 OCR"
        return result

    ocr = get_ocr_engine(lang)
    if ocr is None:
        result["error"] = "OCR 引擎初始化失败"
        return result

    try:
        ocr_result = ocr.ocr(image_path, cls=False)

        if ocr_result and ocr_result[0]:
            lines = []
            boxes = []
            for line in ocr_result[0]:
                box = line[0]
                text = line[1][0]
                confidence = line[1][1]

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
            result["method"] = "paddleocr"

    except Exception as e:
        result["error"] = str(e)
        result["method"] = "error"

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
    except Exception as e:
        logger.warning("Failed to remove temp screenshot %s: %s", image_path, e)

    return result


def extract_text_regions(result: Dict, min_confidence: float = 0.5) -> List[Dict]:
    """提取文本区域"""
    regions = []

    for item in result.get("regions", []):
        if item["confidence"] >= min_confidence:
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
    """根据 OCR 结果理解屏幕上下文"""
    if not result.get("success"):
        return f"OCR 跳过: {result.get('error', '未知')}"

    texts = result.get("texts", [])
    if not texts:
        return "屏幕内容为空"

    preview = "\n".join(texts[:20])

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
    """检测可交互元素"""
    elements = []

    for text in result.get("texts", []):
        text_lower = text.lower().strip()

        button_keywords = [
            "确定", "取消", "提交", "发送", "保存", "关闭", "删除",
            "ok", "cancel", "submit", "save", "close", "delete", "click"
        ]

        if any(kw in text_lower for kw in button_keywords):
            elements.append({
                "type": "button",
                "text": text,
                "actionable": True
            })

        if len(text) < 20 and len(text) > 1:
            elements.append({
                "type": "field",
                "text": text,
                "actionable": False
            })

    return elements


def test():
    """测试 OCR 功能"""
    print("=== PaddleOCR 测试 ===\n")

    # 检查安装
    print(f"PaddleOCR 可用: {is_ocr_available()}")

    # 检查内存
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    mb = int(line.split()[1]) / 1024
                    print(f"可用内存: {mb:.0f} MB")
                    if mb < 1500:
                        print("⚠️ 内存不足，OCR 可能不稳定")
                    break
    except Exception as e:
        logger.warning("Failed to read /proc/meminfo: %s", e)

    # 测试图片 OCR
    print("\n测试图片 OCR...")

    try:
        from PIL import Image, ImageDraw, ImageFont

        # 创建测试图片
        img = Image.new('RGB', (400, 100), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 30), "Hello World", fill='black')

        test_image = "/tmp/test_ocr.png"
        img.save(test_image)
        print(f"测试图片: {test_image}")

        result = ocr_image(test_image)
        if result["success"]:
            print(f"✅ OCR 成功: {result['full_text']}")
        else:
            print(f"⚠️ OCR 失败: {result.get('error')}")

        os.remove(test_image)

    except ImportError:
        print("⚠️ PIL 未安装，跳过图片测试")
    except Exception as e:
        print(f"⚠️ 测试出错: {e}")


if __name__ == "__main__":
    test()

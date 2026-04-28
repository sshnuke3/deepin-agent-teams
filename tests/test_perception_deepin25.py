#!/usr/bin/env python3
"""
deepin 25 环境感知层测试脚本
============================================================
在 deepin 25 实体机上运行，测试 perception/ 模块是否正常工作。
测试结果会写入 test_results_TIMESTAMP.json 文件。

使用方法：
  1. 拷贝到 deepin 25 实体机
  2. 确保已安装依赖：pip install -r requirements.txt
  3. 运行：python3 tests/test_perception_deepin25.py
  4. 把生成的 test_results_*.json 拷回本机给我分析
============================================================
"""
import os
import sys
import json
import datetime
import traceback

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

RESULTS_FILE = None  # 全局结果文件路径


def write_result(category: str, test_name: str, passed: bool, message: str = "", details: dict = None):
    """向结果文件写入一条测试结果"""
    global RESULTS_FILE
    result_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "category": category,
        "test": test_name,
        "passed": passed,
        "message": message,
        "details": details or {}
    }
    with open(RESULTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(result_entry, ensure_ascii=False) + "\n")
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}: {test_name} — {message}")


def test_screen_capture():
    """测试屏幕截图功能"""
    print("\n=== 屏幕截图测试 ===")
    try:
        from perception.screen_capture import capture_screen, get_screen_info, is_wayland, is_x11

        # 检测会话类型
        session_type = "unknown"
        if is_wayland():
            session_type = "wayland"
        elif is_x11():
            session_type = "x11"

        write_result("screen", "session_type_detection", True,
                     f"会话类型: {session_type}", {"session_type": session_type})

        # 获取屏幕信息
        try:
            info = get_screen_info()
            write_result("screen", "get_screen_info", True,
                         f"屏幕信息获取成功", {"screen_info": info})
        except Exception as e:
            write_result("screen", "get_screen_info", False, str(e))

        # 执行截图
        try:
            output_path = capture_screen()
            if output_path and os.path.exists(output_path):
                size = os.path.getsize(output_path)
                write_result("screen", "capture_screen", True,
                             f"截图成功: {output_path} ({size} bytes)",
                             {"output_path": output_path, "size": size})
                # 保留截图文件供后续检查
                return output_path
            else:
                write_result("screen", "capture_screen", False,
                             "截图文件未生成")
        except FileNotFoundError as e:
            # 工具未安装
            write_result("screen", "capture_screen", False,
                         f"截图工具未安装: {e}",
                         {"error": "tool_not_found", "tool": str(e).split("'")[1] if "'" in str(e) else "unknown"})
        except Exception as e:
            write_result("screen", "capture_screen", False, str(e))

    except ImportError as e:
        write_result("screen", "import", False, f"模块导入失败: {e}")
    except Exception as e:
        write_result("screen", "unknown", False, str(e), {"trace": traceback.format_exc()})


def test_clipboard_monitor():
    """测试剪贴板监控"""
    print("\n=== 剪贴板监控测试 ===")
    try:
        from perception.clipboard_monitor import get_clipboard_text, ClipboardMonitor

        # 获取当前剪贴板文本
        try:
            text = get_clipboard_text()
            has_content = len(text) > 0
            write_result("clipboard", "get_clipboard_text", True,
                         f"剪贴板文本: {'(空)' if not text else text[:50]}",
                         {"has_content": has_content, "text_preview": text[:100] if text else ""})
        except Exception as e:
            write_result("clipboard", "get_clipboard_text", False, str(e))

        # 初始化监控器
        try:
            monitor = ClipboardMonitor()
            write_result("clipboard", "ClipboardMonitor_init", True, "监控器初始化成功")
        except Exception as e:
            write_result("clipboard", "ClipboardMonitor_init", False, str(e))

    except ImportError as e:
        write_result("clipboard", "import", False, f"模块导入失败: {e}")


def test_window_manager():
    """测试窗口管理器"""
    print("\n=== 窗口管理器测试 ===")
    try:
        from perception.window_manager import get_active_window, list_windows

        # 获取活动窗口
        try:
            window = get_active_window()
            write_result("window", "get_active_window", True,
                         f"活动窗口: {window.get('title', '(无标题)')}",
                         {"window": window})
        except FileNotFoundError:
            write_result("window", "get_active_window", False,
                         "工具未安装 (wmctrl/xdotool)",
                         {"error": "tool_not_found"})
        except Exception as e:
            write_result("window", "get_active_window", False, str(e))

        # 列出所有窗口
        try:
            windows = list_windows()
            write_result("window", "list_windows", True,
                         f"共 {len(windows)} 个窗口",
                         {"count": len(windows), "windows": windows[:10]})
        except FileNotFoundError:
            write_result("window", "list_windows", False,
                         "工具未安装", {"error": "tool_not_found"})
        except Exception as e:
            write_result("window", "list_windows", False, str(e))

    except ImportError as e:
        write_result("window", "import", False, f"模块导入失败: {e}")


def test_system_monitor():
    """测试系统监控"""
    print("\n=== 系统监控测试 ===")
    try:
        from perception.system_monitor import (
            check_service, diagnose_audio, diagnose_printer,
            diagnose_network, get_service_details
        )

        # 检查常用服务状态
        services_to_check = [
            ("NetworkManager", "network"),
            ("pulseaudio", "audio"),
            ("cups", "printer"),
        ]

        for svc_name, svc_type in services_to_check:
            try:
                status = check_service(svc_name)
                write_result("system", f"check_service_{svc_type}", status.state != "unknown",
                             f"{svc_name}: {status.state}",
                             {"service": svc_name, "state": status.state,
                              "active": status.active, "loaded": status.loaded})
            except Exception as e:
                write_result("system", f"check_service_{svc_type}", False, str(e))

        # 诊断音频
        try:
            audio_result = diagnose_audio()
            write_result("system", "diagnose_audio", True,
                         f"音频诊断完成", {"result": audio_result})
        except Exception as e:
            write_result("system", "diagnose_audio", False, str(e))

        # 诊断网络
        try:
            net_result = diagnose_network()
            write_result("system", "diagnose_network", True,
                         f"网络诊断完成", {"result": net_result})
        except Exception as e:
            write_result("system", "diagnose_network", False, str(e))

        # 诊断打印机
        try:
            printer_result = diagnose_printer()
            write_result("system", "diagnose_printer", True,
                         f"打印机诊断完成", {"result": printer_result})
        except Exception as e:
            write_result("system", "diagnose_printer", False, str(e))

    except ImportError as e:
        write_result("system", "import", False, f"模块导入失败: {e}")


def test_deepin_dbus():
    """测试 deepin D-Bus 接口"""
    print("\n=== deepin D-Bus 测试 ===")
    try:
        from perception.deepin_dbus import (
            is_deepin, get_deepin_info, get_audio_volume,
            get_brightness, list_dbus_services
        )

        # 检测是否是 deepin 系统
        try:
            deepin_detected = is_deepin()
            write_result("dbus", "is_deepin", True,
                         f"deepin系统检测: {deepin_detected}",
                         {"is_deepin": deepin_detected})
        except Exception as e:
            write_result("dbus", "is_deepin", False, str(e))

        # 获取 deepin 系统信息
        try:
            info = get_deepin_info()
            write_result("dbus", "get_deepin_info", True,
                         f"系统信息获取成功", {"info": info})
        except Exception as e:
            write_result("dbus", "get_deepin_info", False, str(e))

        # 获取音量
        try:
            volume = get_audio_volume()
            write_result("dbus", "get_audio_volume", True,
                         f"当前音量: {volume}%",
                         {"volume": volume})
        except Exception as e:
            write_result("dbus", "get_audio_volume", False, str(e))

        # 获取亮度
        try:
            brightness = get_brightness()
            write_result("dbus", "get_brightness", True,
                         f"当前亮度: {brightness}%",
                         {"brightness": brightness})
        except Exception as e:
            write_result("dbus", "get_brightness", False, str(e))

        # 列出DBus服务
        try:
            services = list_dbus_services()
            write_result("dbus", "list_dbus_services", True,
                         f"共 {len(services)} 个DBus服务",
                         {"count": len(services), "services": services[:20]})
        except Exception as e:
            write_result("dbus", "list_dbus_services", False, str(e))

    except ImportError as e:
        write_result("dbus", "import", False, f"模块导入失败: {e}")


def test_screen_ocr():
    """测试OCR功能"""
    print("\n=== 屏幕OCR测试 ===")
    try:
        from perception.screen_ocr import (
            is_ocr_available, ocr_image, ocr_screen,
            understand_screen_context
        )

        # 检查OCR是否可用
        try:
            available = is_ocr_available()
            write_result("ocr", "is_ocr_available", True,
                         f"OCR可用性: {available}",
                         {"available": available})
        except Exception as e:
            write_result("ocr", "is_ocr_available", False, str(e))

        # 对截图进行OCR
        screenshot = test_screen_capture()
        if screenshot and os.path.exists(screenshot):
            try:
                result = ocr_image(screenshot)
                text_blocks = len(result.get("text_blocks", []))
                write_result("ocr", "ocr_image", True,
                             f"OCR识别完成，检测到 {text_blocks} 个文本块",
                             {"result": result})
            except Exception as e:
                write_result("ocr", "ocr_image", False, str(e))

        # 全屏OCR（需要实际屏幕内容）
        try:
            ocr_result = ocr_screen()
            write_result("ocr", "ocr_screen", True,
                         f"屏幕OCR完成",
                         {"result": ocr_result})
        except Exception as e:
            write_result("ocr", "ocr_screen", False, str(e))

    except ImportError as e:
        write_result("ocr", "import", False, f"模块导入失败: {e}")


def test_context_engine():
    """测试上下文引擎"""
    print("\n=== 上下文引擎测试 ===")
    try:
        from perception.context_engine import ContextEngine, UserContext

        try:
            engine = ContextEngine()
            write_result("context", "ContextEngine_init", True, "上下文引擎初始化成功")
        except Exception as e:
            write_result("context", "ContextEngine_init", False, str(e))
            return

        # 模拟用户输入，测试意图识别
        test_inputs = [
            ("给张三发邮件说项目进度", "email"),
            ("打印机连不上了", "system"),
            ("帮我查一下网络", "network"),
        ]

        for user_input, expected_intent in test_inputs:
            try:
                intent_result = engine.classify_intent(user_input)
                write_result("context", f"classify_intent", True,
                             f"输入: {user_input[:20]}... → 识别为: {intent_result.intent_type}",
                             {"input": user_input, "result": {
                                 "intent_type": intent_result.intent_type,
                                 "confidence": intent_result.confidence,
                                 "entities": intent_result.entities
                             }})
            except AttributeError:
                # classify_intent 方法不存在，尝试 detect_intent
                try:
                    result = engine.detect_intent(user_input)
                    write_result("context", "detect_intent", True,
                                 f"输入: {user_input[:20]}...",
                                 {"input": user_input, "result": result})
                except Exception as e2:
                    write_result("context", "detect_intent", False, str(e2))
            except Exception as e:
                write_result("context", "classify_intent", False, str(e))

    except ImportError as e:
        write_result("context", "import", False, f"模块导入失败: {e}")


def test_agents():
    """测试 agents 模块"""
    print("\n=== Agents模块测试 ===")
    try:
        from agents.system_operator import SystemOperator
        from agents.information_collector import InformationCollector
        from agents.content_creator import ContentCreator

        agents = [
            ("SystemOperator", SystemOperator),
            ("InformationCollector", InformationCollector),
            ("ContentCreator", ContentCreator),
        ]

        for name, cls in agents:
            try:
                agent = cls()
                capabilities = getattr(agent, "capabilities", [])
                write_result("agents", f"{name}_init", True,
                             f"初始化成功，能力: {capabilities}",
                             {"capabilities": capabilities})
            except Exception as e:
                write_result("agents", f"{name}_init", False, str(e))

    except ImportError as e:
        write_result("agents", "import", False, f"模块导入失败: {e}")


def test_scenarios():
    """测试场景模块"""
    print("\n=== 场景模块测试 ===")
    try:
        from scenarios.email_assistant import EmailAssistant
        from scenarios.system_doctor import SystemDoctor

        # 测试EmailAssistant
        try:
            ea = EmailAssistant()
            write_result("scenarios", "EmailAssistant_init", True,
                         "邮件助手初始化成功")
        except Exception as e:
            write_result("scenarios", "EmailAssistant_init", False, str(e))

        # 测试SystemDoctor
        try:
            sd = SystemDoctor()
            write_result("scenarios", "SystemDoctor_init", True,
                         "系统医生初始化成功")
        except Exception as e:
            write_result("scenarios", "SystemDoctor_init", False, str(e))

    except ImportError as e:
        write_result("scenarios", "import", False, f"模块导入失败: {e}")


def test_sessions_orchestrator():
    """测试编排器"""
    print("\n=== 编排器测试 ===")
    try:
        from agents.sessions_orchestrator_prod import ProductionExecutor

        try:
            executor = ProductionExecutor()
            write_result("orchestrator", "ProductionExecutor_init", True,
                         "编排器初始化成功")
        except Exception as e:
            write_result("orchestrator", "ProductionExecutor_init", False, str(e))

    except ImportError as e:
        write_result("orchestrator", "import", False, f"模块导入失败: {e}")


def run_all_tests():
    """运行所有测试"""
    global RESULTS_FILE

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    RESULTS_FILE = os.path.join(PROJECT_ROOT, "tests", f"test_results_{timestamp}.json")

    # 清空结果文件（写入头部）
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        f.write(f"# deepin-agent-teams 测试结果\n")
        f.write(f"# 生成时间: {datetime.datetime.now().isoformat()}\n")
        f.write(f"# 项目路径: {PROJECT_ROOT}\n")
        f.write("#-" * 40 + "\n")

    print("=" * 60)
    print("deepin-agent-teams 环境感知层测试")
    print("=" * 60)
    print(f"\n📝 结果文件: {RESULTS_FILE}\n")

    test_categories = [
        ("感知层 - 屏幕", test_screen_capture),
        ("感知层 - 剪贴板", test_clipboard_monitor),
        ("感知层 - 窗口", test_window_manager),
        ("感知层 - 系统监控", test_system_monitor),
        ("感知层 - D-Bus", test_deepin_dbus),
        ("感知层 - OCR", test_screen_ocr),
        ("感知层 - 上下文引擎", test_context_engine),
        ("Agents模块", test_agents),
        ("场景模块", test_scenarios),
        ("编排器", test_sessions_orchestrator),
    ]

    passed = 0
    failed = 0

    for name, test_func in test_categories:
        try:
            test_func()
        except Exception as e:
            print(f"  ❌ 测试崩溃 {name}: {e}")
            write_result("crash", name, False, str(e), {"trace": traceback.format_exc()})

    # 读取统计结果
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        lines = [l for l in f if l.startswith("{")]
        results = [json.loads(l) for l in lines]
        passed = sum(1 for r in results if r["passed"])
        failed = sum(1 for r in results if not r["passed"])

    print("\n" + "=" * 60)
    print(f"测试完成: ✅ {passed} 通过 / ❌ {failed} 失败")
    print(f"📝 结果文件: {RESULTS_FILE}")
    print("=" * 60)

    # 生成汇总
    summary_file = RESULTS_FILE.replace(".json", "_summary.txt")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"deepin-agent-teams 测试汇总\n")
        f.write(f"生成时间: {datetime.datetime.now().isoformat()}\n")
        f.write(f"总计: ✅ {passed} / ❌ {failed}\n\n")
        f.write("按类别统计:\n")
        by_category = {}
        for r in results:
            cat = r["category"]
            if cat not in by_category:
                by_category[cat] = {"pass": 0, "fail": 0}
            if r["passed"]:
                by_category[cat]["pass"] += 1
            else:
                by_category[cat]["fail"] += 1
        for cat, stat in by_category.items():
            f.write(f"  {cat}: ✅ {stat['pass']} / ❌ {stat['fail']}\n")
        f.write("\n所有测试结果详情见同一目录下的 test_results_TIMESTAMP.json\n")
    print(f"📊 汇总文件: {summary_file}")

    return passed, failed


if __name__ == "__main__":
    run_all_tests()

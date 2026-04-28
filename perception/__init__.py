"""
deepin-agent-teams 环境感知模块
提供屏幕、剪贴板、窗口、系统状态等感知能力
"""

from .screen_capture import (
    capture_screen,
    capture_active_window,
    get_screen_info,
)

from .clipboard_monitor import (
    ClipboardMonitor,
    get_clipboard_text,
)

from .window_manager import (
    WindowInfo,
    get_active_window,
    get_window_list,
    get_active_app_context,
    get_window_classification,
    focus_window,
)

from .system_monitor import (
    ServiceStatus,
    check_service,
    diagnose_printer,
    diagnose_audio,
    diagnose_network,
    diagnose_bluetooth,
    diagnose_issue,
    install_package,
    get_system_summary,
)

from .context_engine import (
    UserContext,
    IntentResult,
    ContextEngine,
)

from .screen_ocr import (
    ocr_image,
    ocr_screen,
    extract_text_regions,
    understand_screen_context,
    detect_interactive_elements,
)

__all__ = [
    # screen
    "capture_screen",
    "capture_active_window",
    "get_screen_info",
    # clipboard
    "ClipboardMonitor",
    "get_clipboard_text",
    # window
    "WindowInfo",
    "get_active_window",
    "get_window_list",
    "get_active_app_context",
    "get_window_classification",
    "focus_window",
    # system
    "ServiceStatus",
    "check_service",
    "diagnose_printer",
    "diagnose_audio",
    "diagnose_network",
    "diagnose_bluetooth",
    "diagnose_issue",
    "install_package",
    "get_system_summary",
    # deepin
    "is_deepin",
    "get_audio_volume",
    "set_audio_volume",
    "toggle_mute",
    "get_brightness",
    "set_brightness",
    "open_control_center",
    "get_deepin_info",
    # context
    "UserContext",
    "IntentResult",
    "ContextEngine",
    # OCR
    "ocr_image",
    "ocr_screen",
    "extract_text_regions",
    "understand_screen_context",
    "detect_interactive_elements",
]

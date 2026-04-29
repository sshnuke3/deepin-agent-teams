"""
scenarios/__init__.py - 演示场景
"""
from .code_analysis import CodeAnalysisAssistant
from .literature_review import LiteratureAssistant
from .email_assistant import EmailAssistant
from .system_doctor import SystemDoctor

__all__ = [
    "CodeAnalysisAssistant",
    "LiteratureAssistant",
    "EmailAssistant",
    "SystemDoctor",
]

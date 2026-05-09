"""
隐私保护机制
敏感数据检测、脱敏处理、操作审计日志
"""
import os
import re
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class SensitiveMatch:
    """敏感数据匹配结果"""
    type: str        # phone, id_card, bank_card, email, password, ip
    value: str       # 原始值
    masked: str      # 脱敏后的值
    position: int    # 在文本中的位置


@dataclass
class AuditRecord:
    """审计记录"""
    timestamp: str
    operation: str     # screenshot, clipboard_read, file_search, window_monitor
    agent: str         # 执行的 Agent
    detail: str        # 操作详情
    sensitive: bool    # 是否涉及敏感数据
    approved: bool     # 是否已获用户授权


class PrivacyGuard:
    """
    隐私保护器

    功能：
    1. 敏感数据检测（手机号、身份证、银行卡、邮箱、密码、IP）
    2. 自动脱敏
    3. 操作审计日志
    4. 用户授权管理
    """

    # 敏感数据正则模式
    PATTERNS = {
        "phone": re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'),
        "id_card": re.compile(r'(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)'),
        "bank_card": re.compile(r'(?<!\d)[1-9]\d{15,18}(?!\d)'),
        "email": re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'),
        "password_kw": re.compile(r'(?:密码|password|passwd|pwd|口令|令牌|token)\s*[:=：]\s*\S+', re.IGNORECASE),
        "ip_addr": re.compile(r'(?<!\d)(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)(?!\d)'),
    }

    def __init__(self, log_path: str = None):
        self._audit_log: List[AuditRecord] = []
        self._log_path = log_path or os.path.expanduser(
            "~/.deepin-agent-teams/privacy_audit.json"
        )
        self._authorized_ops: set = set()  # 已授权的操作集合
        self._load_audit_log()

    def scan_sensitive(self, text: str) -> List[SensitiveMatch]:
        """
        扫描文本中的敏感数据

        Returns:
            敏感数据匹配列表
        """
        if not text:
            return []

        matches = []
        for stype, pattern in self.PATTERNS.items():
            for m in pattern.finditer(text):
                value = m.group()
                masked = self._mask_value(stype, value)
                matches.append(SensitiveMatch(
                    type=stype,
                    value=value,
                    masked=masked,
                    position=m.start(),
                ))
        return matches

    def has_sensitive(self, text: str) -> bool:
        """快速检查文本是否包含敏感数据"""
        if not text:
            return False
        for pattern in self.PATTERNS.values():
            if pattern.search(text):
                return True
        return False

    def mask_text(self, text: str) -> str:
        """
        对文本中的敏感数据进行脱敏

        Returns:
            脱敏后的文本
        """
        if not text:
            return text

        result = text
        # 按位置从后往前替换（避免偏移）
        for stype, pattern in self.PATTERNS.items():
            matches = list(pattern.finditer(result))
            for m in reversed(matches):
                masked = self._mask_value(stype, m.group())
                result = result[:m.start()] + masked + result[m.end():]
        return result

    def _mask_value(self, stype: str, value: str) -> str:
        """脱敏单个值"""
        if stype == "phone":
            return value[:3] + "****" + value[-4:]
        elif stype == "id_card":
            return value[:6] + "********" + value[-4:]
        elif stype == "bank_card":
            return value[:4] + " **** **** " + value[-4:]
        elif stype == "email":
            parts = value.split("@")
            name = parts[0]
            if len(name) > 2:
                masked_name = name[0] + "***" + name[-1]
            else:
                masked_name = name[0] + "***"
            return masked_name + "@" + parts[1]
        elif stype == "password_kw":
            # 保留关键字，脱敏值
            for kw in ["密码", "password", "passwd", "pwd", "口令", "令牌", "token"]:
                if kw.lower() in value.lower():
                    idx = value.lower().find(kw.lower())
                    prefix_end = idx + len(kw)
                    # 找到值的开始
                    rest = value[prefix_end:]
                    sep_match = re.match(r'\s*[:=：]\s*', rest)
                    if sep_match:
                        val_start = prefix_end + sep_match.end()
                        return value[:val_start] + "******"
            return "******"
        elif stype == "ip_addr":
            parts = value.split(".")
            return parts[0] + "." + parts[1] + ".*.*"
        return "******"

    # === 审计日志 ===

    def log_operation(self, operation: str, agent: str, detail: str,
                      sensitive: bool = False, approved: bool = False):
        """记录一次感知操作"""
        record = AuditRecord(
            timestamp=datetime.now().isoformat(),
            operation=operation,
            agent=agent,
            detail=detail[:200],
            sensitive=sensitive,
            approved=approved,
        )
        self._audit_log.append(record)

        # 限制内存中的记录数
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-500:]

        # 持久化
        self._save_audit_log()

    def check_authorization(self, operation: str) -> bool:
        """检查操作是否已获授权"""
        return operation in self._authorized_ops

    def authorize(self, operation: str):
        """用户授权某类操作"""
        self._authorized_ops.add(operation)
        self.log_operation("authorize", "user", f"授权操作: {operation}", approved=True)

    def get_audit_log(self, limit: int = 50) -> List[Dict]:
        """获取审计日志"""
        recent = self._audit_log[-limit:]
        return [asdict(r) for r in recent]

    def get_sensitive_stats(self, text: str) -> Dict:
        """获取敏感数据统计"""
        matches = self.scan_sensitive(text)
        stats = {}
        for m in matches:
            stats[m.type] = stats.get(m.type, 0) + 1
        return {
            "total": len(matches),
            "by_type": stats,
            "has_sensitive": len(matches) > 0,
        }

    def _save_audit_log(self):
        """保存审计日志"""
        try:
            os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
            data = [asdict(r) for r in self._audit_log[-200:]]
            with open(self._log_path, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_audit_log(self):
        """加载审计日志"""
        if not os.path.exists(self._log_path):
            return
        try:
            with open(self._log_path) as f:
                data = json.load(f)
            self._audit_log = [AuditRecord(**r) for r in data]
        except Exception:
            pass


# 全局单例
_guard: Optional[PrivacyGuard] = None


def get_privacy_guard() -> PrivacyGuard:
    global _guard
    if _guard is None:
        _guard = PrivacyGuard()
    return _guard

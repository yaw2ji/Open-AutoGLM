"""
风险管控 SDK
===========
在意图理解之后、动作执行之前，对任务进行风险分级和管控。

子模块：
- classifier: 风险分级器
- config:     用户自定义策略配置
- audit:      审计记录管理

快速使用示例：
    from risk_sdk import RiskSDK

    sdk = RiskSDK()
    result = sdk.check(task="转账500给张三", action=action, thinking=thinking)
    if not result.allowed:
        print(f"操作被拦截，风险等级：{result.risk_level}")
"""

from risk_sdk.sdk import RiskSDK, RiskCheckResult
from risk_sdk.config.user_config import UserConfig
from risk_sdk.classifier.rule_classifier import RuleClassifier
from risk_sdk.audit.manager import AuditManager

__version__ = "0.1.0"
__all__ = [
    "RiskSDK",
    "RiskCheckResult",
    "UserConfig",
    "RuleClassifier",
    "AuditManager",
]

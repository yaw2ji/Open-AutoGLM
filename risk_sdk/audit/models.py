"""审计记录数据模型。"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

# 执行结果类型：放行 / 询问后执行 / 拦截
ExecutionOutcome = Literal["approved", "asked", "rejected"]


@dataclass
class AuditRecord:
    """
    单次风险检查的审计记录。

    每次调用 RiskSDK.check() 都会生成一条记录，
    包含完整的输入、分级结果和最终处置信息。

    Attributes:
        record_id:        唯一标识符（UUID）
        timestamp:        记录时间
        task:             用户原始任务文本
        action_type:      动作类型（Tap / Type / Launch 等）
        action_raw:       完整的 action 字典（JSON 序列化存储）
        thinking_snippet: 模型推理文本的前 200 字（避免记录过长）
        risk_level:       风险等级 1-10
        matched_rules:    命中的规则名称列表
        outcome:          最终处置结果（approved / asked / rejected）
        user_decision:    询问时用户的决策（True=确认, False=拒绝, None=未询问）
        step_count:       执行步骤编号
    """

    record_id: str
    timestamp: datetime
    task: str
    action_type: str
    action_raw: dict[str, Any]
    thinking_snippet: str
    risk_level: int
    matched_rules: list[str]
    outcome: ExecutionOutcome
    user_decision: bool | None
    step_count: int

    @classmethod
    def create(
        cls,
        task: str,
        action: dict[str, Any],
        thinking: str,
        risk_level: int,
        matched_rules: list[str],
        outcome: ExecutionOutcome,
        step_count: int,
        user_decision: bool | None = None,
    ) -> "AuditRecord":
        """工厂方法：自动生成 record_id 和 timestamp。"""
        return cls(
            record_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            task=task,
            action_type=action.get("action", "unknown"),
            action_raw=action,
            thinking_snippet=thinking[:200] if thinking else "",
            risk_level=risk_level,
            matched_rules=matched_rules,
            outcome=outcome,
            user_decision=user_decision,
            step_count=step_count,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为可直接写入 CSV 的平铺字典。"""
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "task": self.task,
            "action_type": self.action_type,
            "action_raw": json.dumps(self.action_raw, ensure_ascii=False),
            "thinking_snippet": self.thinking_snippet,
            "risk_level": self.risk_level,
            "matched_rules": "|".join(self.matched_rules),
            "outcome": self.outcome,
            "user_decision": (
                "" if self.user_decision is None
                else ("Y" if self.user_decision else "N")
            ),
            "step_count": self.step_count,
        }

    # CSV 文件的列顺序
    CSV_FIELDS = [
        "record_id",
        "timestamp",
        "task",
        "action_type",
        "action_raw",
        "thinking_snippet",
        "risk_level",
        "matched_rules",
        "outcome",
        "user_decision",
        "step_count",
    ]

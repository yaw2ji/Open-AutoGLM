"""分级器的输入输出数据模型。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClassifyRequest:
    """
    分级器的输入数据包。

    由 agent._execute_step() 在意图理解完成后构造，
    包含分级所需的全部上下文信息。

    Attributes:
        task:       用户原始任务文本，如"帮我转账500给张三"
        action:     parse_action() 返回的动作字典，如 {"action":"Tap","element":[x,y]}
        thinking:   模型推理过程文本（<think> 块内容）
        step_count: 当前执行步骤编号（agent._step_count）
        extra:      预留扩展字段，用于后续算法传递附加信息
    """

    task: str
    action: dict[str, Any]
    thinking: str
    step_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassifyResult:
    """
    分级器的输出结果。

    Attributes:
        risk_level:    风险等级，1（最低）到 10（最高）
        reason:        触发原因的人类可读描述，用于向用户展示和审计记录
        matched_rules: 命中的规则名称列表，便于调试和审计溯源
        metadata:      预留扩展字段，供后续算法输出附加信息（如置信度、特征向量等）
    """

    risk_level: int
    reason: str
    matched_rules: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not (1 <= self.risk_level <= 10):
            raise ValueError(
                f"risk_level 必须在 1-10 范围内，当前值: {self.risk_level}"
            )

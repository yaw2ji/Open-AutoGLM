"""
风险管控 SDK 门面类。

将 Classifier / UserConfig / AuditManager 三个子模块串联为单一接口。
agent.py 只需导入并实例化 RiskSDK，调用 check() 方法即可完成完整的风险管控流程。
"""

from dataclasses import dataclass
from typing import Any, Callable

from risk_sdk.audit.manager import AuditManager
from risk_sdk.classifier.base import BaseClassifier
from risk_sdk.classifier.models import ClassifyRequest
from risk_sdk.classifier.rule_classifier import RuleClassifier
from risk_sdk.config.user_config import DecisionType, UserConfig
from risk_sdk.exceptions import RiskRejectedError


@dataclass
class RiskCheckResult:
    """
    单次风险检查的完整结果。

    由 RiskSDK.check() 返回，agent.py 根据 allowed 字段决定是否执行动作。

    Attributes:
        allowed:       True = 允许执行；False = 拦截，不执行
        decision:      处置决策（approve / ask / reject）
        risk_level:    风险等级 1-10
        reason:        风险原因描述（用于展示给用户）
        user_decision: 询问区间时用户的决策（True=确认, False=拒绝, None=未询问）
    """

    allowed: bool
    decision: DecisionType
    risk_level: int
    reason: str
    user_decision: bool | None = None


class RiskSDK:
    """
    风险管控 SDK 门面类。

    在 agent._execute_step() 的意图理解完成后、动作执行前，
    对每一步操作执行：分级 → 决策 → 审计 三步流程。

    完整流程：
        1. Classifier.classify()   → 输出 risk_level（1-10）
        2. UserConfig.get_decision() → 输出 approve / ask / reject
        3. [若 ask] confirm_callback() → 获取用户决策
        4. AuditManager.record()   → 写入审计日志
        5. 返回 RiskCheckResult

    Usage:
        # 最简使用（全部默认）
        sdk = RiskSDK()
        result = sdk.check(task, action, thinking, step_count)
        if not result.allowed:
            return  # 拦截，跳过执行

        # 自定义配置
        sdk = RiskSDK(
            config_path="./my_config.json",
            log_dir="./logs/risk",
            confirm_callback=my_gui_confirm,
        )

        # 替换分级器（接入真实算法）
        sdk = RiskSDK(classifier=MLClassifier())

        # 查询审计记录
        records = sdk.audit.query(min_risk_level=7, outcome="rejected")
        sdk.audit.export_csv("./report.csv", records)
    """

    def __init__(
        self,
        classifier: BaseClassifier | None = None,
        user_config: UserConfig | None = None,
        audit_manager: AuditManager | None = None,
        confirm_callback: Callable[[str, int], bool] | None = None,
        config_path: str | None = None,
        log_dir: str = "./risk_audit_logs",
    ):
        """
        Args:
            classifier:       分级器实例，None 时使用内置 RuleClassifier
            user_config:      用户配置实例，None 时使用默认配置（1-3放行,4-6询问,7+拒绝）
            audit_manager:    审计管理器实例，None 时自动创建
            confirm_callback: 询问区间的确认回调，签名 (reason: str, risk_level: int) -> bool
                              None 时使用内置控制台确认
            config_path:      用户配置文件路径（JSON），优先于默认值
            log_dir:          审计日志目录路径
        """
        self.classifier: BaseClassifier = classifier or RuleClassifier()
        self.user_config: UserConfig = user_config or UserConfig(config_path)
        self.audit: AuditManager = audit_manager or AuditManager(log_dir)
        self._confirm_callback = confirm_callback or self._default_confirm

    # ──────────────────────────────
    # 核心方法
    # ──────────────────────────────

    def check(
        self,
        task: str,
        action: dict[str, Any],
        thinking: str,
        step_count: int = 0,
        raise_on_reject: bool = False,
    ) -> RiskCheckResult:
        """
        执行完整的风险检查流程。

        这是 agent.py 调用的唯一方法。

        Args:
            task:           用户原始任务文本（agent._current_task）
            action:         parse_action() 返回的动作字典
            thinking:       模型推理文本（response.thinking）
            step_count:     当前步骤编号（agent._step_count）
            raise_on_reject: True 时拦截会抛出 RiskRejectedError 而非返回 allowed=False

        Returns:
            RiskCheckResult，agent.py 根据 .allowed 字段决定是否执行动作

        Raises:
            RiskRejectedError: 当 raise_on_reject=True 且操作被拦截时
        """
        # ── Step 1：分级 ──────────────────────────
        request = ClassifyRequest(
            task=task,
            action=action,
            thinking=thinking,
            step_count=step_count,
        )
        classify_result = self.classifier.classify(request)

        # ── Step 2：决策 ──────────────────────────
        decision = self.user_config.get_decision(classify_result.risk_level)

        # ── Step 3：询问（仅 ask 区间）────────────
        user_decision: bool | None = None
        if decision == "ask":
            user_decision = self._confirm_callback(
                classify_result.reason,
                classify_result.risk_level,
            )
            # 用户拒绝 → 升级为 reject
            if not user_decision:
                decision = "reject"

        # ── Step 4：审计写入 ──────────────────────
        outcome_map = {
            "approve": "approved",
            "ask":     "asked",
            "reject":  "rejected",
        }
        self.audit.record(
            task=task,
            action=action,
            thinking=thinking,
            risk_level=classify_result.risk_level,
            matched_rules=classify_result.matched_rules,
            outcome=outcome_map[decision],  # type: ignore
            step_count=step_count,
            user_decision=user_decision,
        )

        # ── Step 5：构造结果 ──────────────────────
        allowed = decision in ("approve", "ask") and (
            decision != "ask" or user_decision is True
        )

        result = RiskCheckResult(
            allowed=allowed,
            decision=decision,   # type: ignore
            risk_level=classify_result.risk_level,
            reason=classify_result.reason,
            user_decision=user_decision,
        )

        if not allowed and raise_on_reject:
            raise RiskRejectedError(
                risk_level=classify_result.risk_level,
                reason=classify_result.reason,
            )

        return result

    # ──────────────────────────────
    # 快捷接口
    # ──────────────────────────────

    def update_config(
        self,
        auto_approve_max: int | None = None,
        ask_confirm_max: int | None = None,
    ) -> None:
        """
        运行时修改风险策略阈值的快捷方法。

        等价于 sdk.user_config.update(...)

        Example:
            # 切换为宽松策略（1-7放行，8-9询问，10拒绝）
            sdk.update_config(auto_approve_max=7, ask_confirm_max=9)
        """
        self.user_config.update(auto_approve_max, ask_confirm_max)

    def print_config(self) -> None:
        """打印当前风险策略配置到控制台。"""
        s = self.user_config.summary
        print("\n[风险管控 SDK] 当前策略配置：")
        print(f"  [放行] 自动放行：风险等级 {s['approve_zone']}")
        print(f"  [询问] 询问确认：风险等级 {s['ask_zone']}")
        print(f"  [拒绝] 自动拦截：风险等级 {s['reject_zone']}\n")

    def print_stats(self) -> None:
        """打印审计统计摘要到控制台。"""
        self.audit.print_stats()

    # ──────────────────────────────
    # 默认确认回调
    # ──────────────────────────────

    @staticmethod
    def _default_confirm(reason: str, risk_level: int) -> bool:
        """
        内置的控制台确认回调（与 ActionHandler._default_confirmation 风格一致）。

        在集成 GUI 或审批系统时，通过 confirm_callback 参数替换此方法。
        """
        print(f"\n{'='*50}")
        print(f"[风险管控] 检测到风险操作，需要确认")
        print(f"   风险等级：{risk_level} / 10")
        print(f"   风险原因：{reason}")
        print(f"{'='*50}")
        response = input("是否继续执行此操作？(Y/N): ")
        return response.strip().upper() == "Y"

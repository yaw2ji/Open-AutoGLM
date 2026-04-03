"""风险管控 SDK 自定义异常类。"""


class RiskSDKError(Exception):
    """SDK 基础异常，所有 SDK 异常的父类。"""


class RiskRejectedError(RiskSDKError):
    """
    动作被风险策略拒绝时抛出。

    注意：RiskSDK.check() 默认不抛出此异常，而是通过返回 allowed=False 来表示拒绝。
    此异常用于调用方希望以异常方式处理拦截的场景（raise_on_reject=True 时触发）。

    Example:
        try:
            sdk.check(task, action, thinking, raise_on_reject=True)
        except RiskRejectedError as e:
            print(f"拦截原因：{e.reason}，风险等级：{e.risk_level}")
    """

    def __init__(self, risk_level: int, reason: str):
        self.risk_level = risk_level
        self.reason = reason
        super().__init__(
            f"[风险拦截] 等级 {risk_level}/10：{reason}"
        )


class ConfigValidationError(RiskSDKError):
    """
    配置校验失败时抛出。

    例如：auto_approve_max >= ask_confirm_max 时触发。
    """


class ClassifierError(RiskSDKError):
    """分级器内部错误。"""

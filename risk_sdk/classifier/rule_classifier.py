"""
基于规则列表的风险分级器。

当前阶段：规则函数体为占位符实现（关键词匹配 + 随机扰动）。
后续替换真实算法时，只需修改规则函数体或注册新规则，框架代码不变。

规则设计原则：
- 每条规则是一个独立函数，接收 ClassifyRequest，返回 (命中, 等级, 原因)
- 遍历所有规则，取所有命中规则中的最高风险等级（最高分优先策略）
- 规则支持运行时动态注册/注销
"""

import random
from typing import Callable

from risk_sdk.classifier.base import BaseClassifier
from risk_sdk.classifier.models import ClassifyRequest, ClassifyResult
from risk_sdk.exceptions import ClassifierError

# 规则函数类型别名：(ClassifyRequest) -> (是否命中, 风险等级, 原因描述)
RuleFunc = Callable[[ClassifyRequest], tuple[bool, int, str]]


# ─────────────────────────────────────────────
# 内置规则函数（当前为占位符实现）
# 后续替换真实算法时：只修改这些函数的函数体
# ─────────────────────────────────────────────

def _rule_payment(req: ClassifyRequest) -> tuple[bool, int, str]:
    """
    【占位符】支付 / 转账 / 充值类操作检测。
    风险等级：9
    后续替换为：金融行为识别模型 / 支付 API 调用检测
    """
    keywords = [
        "支付", "付款", "转账", "充值", "打款", "汇款",
        "pay", "payment", "transfer", "recharge",
    ]
    combined = (req.task + " " + req.thinking).lower()
    if any(k in combined for k in keywords):
        return True, 9, "检测到支付/转账相关操作"
    return False, 0, ""


def _rule_delete_sensitive(req: ClassifyRequest) -> tuple[bool, int, str]:
    """
    【占位符】删除 / 清空 / 注销类操作检测。
    风险等级：8
    后续替换为：破坏性操作语义识别模型
    """
    keywords = [
        "删除", "清空", "清除", "注销", "卸载", "格式化",
        "delete", "remove", "clear", "uninstall", "wipe",
    ]
    combined = (req.task + " " + req.thinking).lower()
    if any(k in combined for k in keywords):
        return True, 8, "检测到删除/清空/注销类操作"
    return False, 0, ""


def _rule_privacy(req: ClassifyRequest) -> tuple[bool, int, str]:
    """
    【占位符】隐私信息访问检测（通讯录、位置、相册等）。
    风险等级：7
    后续替换为：隐私权限访问行为分类器
    """
    keywords = [
        "通讯录", "联系人", "位置", "定位", "相册", "照片",
        "密码", "身份证", "银行卡", "私信",
        "contact", "location", "photo", "password", "id card",
    ]
    combined = (req.task + " " + req.thinking).lower()
    if any(k in combined for k in keywords):
        return True, 7, "检测到隐私信息访问操作"
    return False, 0, ""


def _rule_social_send(req: ClassifyRequest) -> tuple[bool, int, str]:
    """
    【占位符】社交发送类操作检测（发消息、发帖、评论等）。
    风险等级：5
    后续替换为：社交行为意图分类器
    """
    keywords = [
        "发送", "发消息", "发帖", "评论", "回复", "转发", "分享",
        "send", "post", "comment", "reply", "share",
    ]
    combined = (req.task + " " + req.thinking).lower()
    if any(k in combined for k in keywords):
        return True, 5, "检测到社交发送类操作"
    return False, 0, ""


def _rule_system_settings(req: ClassifyRequest) -> tuple[bool, int, str]:
    """
    【占位符】系统设置类操作检测（权限、网络、账号等）。
    风险等级：6
    后续替换为：系统操作权限映射表
    """
    keywords = [
        "设置", "权限", "网络", "蓝牙", "账号", "登录", "授权",
        "setting", "permission", "network", "bluetooth", "account",
    ]
    # 仅在 action 为系统级操作时才判断
    action_name = req.action.get("action", "")
    combined = (req.task + " " + req.thinking).lower()
    if action_name in ("Launch",) and any(k in combined for k in keywords):
        return True, 6, "检测到系统设置类操作"
    return False, 0, ""


def _rule_info_query(req: ClassifyRequest) -> tuple[bool, int, str]:
    """
    【占位符】信息查询类操作检测（搜索、查看、浏览等）。
    风险等级：2
    后续替换为：信息访问意图分类器
    """
    keywords = [
        "搜索", "查询", "查看", "浏览", "打开", "看看",
        "search", "query", "browse", "open", "check",
    ]
    combined = (req.task + " " + req.thinking).lower()
    if any(k in combined for k in keywords):
        return True, 2, "信息查询类操作"
    return False, 0, ""


def _rule_sensitive_tap(req: ClassifyRequest) -> tuple[bool, int, str]:
    """
    检测 action handler 已标记为敏感的 Tap 操作（含 message 字段）。
    风险等级：8
    这是对原有 confirmation_callback 机制的补充检测。
    """
    if req.action.get("action") == "Tap" and "message" in req.action:
        msg = req.action.get("message", "")
        return True, 8, f"模型标记的敏感点击操作：{msg}"
    return False, 0, ""


def _rule_random(req: ClassifyRequest) -> tuple[bool, int, str]:
    """
    随机风险扰动规则：在规则库算法完善之前，为每次操作叠加随机风险值。
    随机范围：1-10，模拟真实场景中的不确定性。
    后续接入真实算法后，此规则可通过 unregister_rule("random") 移除。
    """
    level = random.randint(1, 10)
    return True, level, f"随机风险评估（等级 {level}）"


def _rule_default(req: ClassifyRequest) -> tuple[bool, int, str]:
    """
    兜底规则：所有未被其他规则命中的操作默认为基础风险等级 2。
    始终命中，必须放在规则列表最后。
    """
    return True, 2, "普通操作，基础风险等级"


# ─────────────────────────────────────────────
# 分级器主体
# ─────────────────────────────────────────────

class RuleClassifier(BaseClassifier):
    """
    基于规则列表的风险分级器。

    策略：最高分优先
    遍历所有注册规则，取所有命中规则中风险等级最高的那条作为最终结果。

    Usage:
        classifier = RuleClassifier()

        # 查看当前注册的规则
        print(classifier.list_rules())

        # 动态注册自定义规则（后续接入真实算法时使用）
        classifier.register_rule("my_rule", my_rule_func)

        # 执行分级
        result = classifier.classify(request)
    """

    def __init__(self):
        # 规则列表：[(规则名, 规则函数), ...]，按注册顺序执行
        self._rules: list[tuple[str, RuleFunc]] = []
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """注册内置规则集（按风险等级从高到低排列，便于阅读）。"""
        self._rules = [
            ("sensitive_tap",    _rule_sensitive_tap),       # 等级 8：已标记敏感点击
            ("payment",          _rule_payment),             # 等级 9：支付/转账
            ("delete_sensitive", _rule_delete_sensitive),    # 等级 8：删除/清空
            ("privacy",          _rule_privacy),             # 等级 7：隐私访问
            ("system_settings",  _rule_system_settings),     # 等级 6：系统设置
            ("social_send",      _rule_social_send),         # 等级 5：社交发送
            ("info_query",       _rule_info_query),          # 等级 2：信息查询
            ("random",           _rule_random),              # 随机扰动：1-10
            ("default",          _rule_default),             # 等级 2：兜底
        ]

    def register_rule(self, name: str, rule_func: RuleFunc, index: int = -1) -> None:
        """
        动态注册一条新规则。

        Args:
            name:      规则唯一名称，重复注册会覆盖原有规则
            rule_func: 规则函数，签名为 (ClassifyRequest) -> (bool, int, str)
            index:     插入位置，-1 表示插入到 default 规则之前（推荐），
                       0 表示最高优先级
        """
        # 如果已存在同名规则，先移除
        self._rules = [(n, f) for n, f in self._rules if n != name]

        # 插入到 default 规则之前（保证 default 始终兜底）
        if index == -1:
            default_idx = next(
                (i for i, (n, _) in enumerate(self._rules) if n == "default"),
                len(self._rules),
            )
            self._rules.insert(default_idx, (name, rule_func))
        else:
            self._rules.insert(index, (name, rule_func))

    def unregister_rule(self, name: str) -> bool:
        """
        按名称移除规则。

        Args:
            name: 规则名称

        Returns:
            True 表示成功移除，False 表示未找到该规则
        """
        before = len(self._rules)
        self._rules = [(n, f) for n, f in self._rules if n != name]
        return len(self._rules) < before

    def list_rules(self) -> list[str]:
        """返回当前已注册的规则名称列表（按执行顺序）。"""
        return [name for name, _ in self._rules]

    def classify(self, request: ClassifyRequest) -> ClassifyResult:
        """
        执行分级：遍历所有规则，取最高命中等级。

        若 random 规则已注册，则直接以随机等级为最终结果，
        忽略其他规则（用于算法完善前的测试阶段）。

        Args:
            request: 分级请求

        Returns:
            ClassifyResult，risk_level 为 1-10

        Raises:
            ClassifierError: 所有规则执行均异常时抛出
        """
        errors: list[str] = []

        # 若注册了 random 规则，直接以随机结果为最终输出，跳过其他规则
        random_rule = next((f for n, f in self._rules if n == "random"), None)
        if random_rule is not None:
            try:
                _, level, reason = random_rule(request)
                final_level = max(1, min(10, level))
                return ClassifyResult(
                    risk_level=final_level,
                    reason=reason,
                    matched_rules=["random"],
                )
            except Exception as e:
                errors.append(f"random: {e}")

        # 正常模式：遍历所有规则，取最高命中等级
        highest_level = 0
        best_reason = "未命中任何规则"
        matched_rules: list[str] = []

        for rule_name, rule_func in self._rules:
            try:
                hit, level, reason = rule_func(request)
                if hit and level > highest_level:
                    highest_level = level
                    best_reason = reason
                if hit:
                    matched_rules.append(rule_name)
            except Exception as e:
                errors.append(f"{rule_name}: {e}")

        if highest_level == 0 and errors:
            raise ClassifierError(f"所有规则执行失败：{'; '.join(errors)}")

        final_level = max(1, min(10, highest_level))
        return ClassifyResult(
            risk_level=final_level,
            reason=best_reason,
            matched_rules=matched_rules,
            metadata={"errors": errors} if errors else {},
        )

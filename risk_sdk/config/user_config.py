"""
用户自定义风险策略配置模块。

允许用户自定义放行 / 询问 / 拦截三个区间的边界，
满足不同用户对风险容忍度的差异化需求。

默认策略：
  风险 1-3  → auto_approve（直接放行）
  风险 4-6  → ask_confirm（询问用户）
  风险 7-10 → auto_reject（直接拦截）

用户可自定义为任意合法的区间划分，例如：
  1-7 放行 / 8-9 询问 / 10 拒绝（宽松策略）
  1-1 放行 / 2-5 询问 / 6+ 拒绝（严格策略）
"""

import json
from pathlib import Path
from typing import Literal

from risk_sdk.exceptions import ConfigValidationError

# 三种处置决策类型
DecisionType = Literal["approve", "ask", "reject"]


class UserConfig:
    """
    用户风险策略配置。

    管理放行 / 询问 / 拒绝三个区间的阈值，支持：
    - 使用内置默认值初始化
    - 从 JSON 文件加载配置
    - 运行时动态修改阈值
    - 将当前配置保存为 JSON 文件

    区间规则（设 A = auto_approve_max，B = ask_confirm_max）：
      风险等级 1 ~ A       → approve（放行）
      风险等级 A+1 ~ B     → ask（询问）
      风险等级 B+1 ~ 10    → reject（拦截）

    约束条件：0 < A < B <= 10

    Usage:
        # 使用默认配置
        config = UserConfig()

        # 从文件加载
        config = UserConfig(config_path="my_config.json")

        # 运行时修改（宽松策略：1-7放行，8-9询问，10拒绝）
        config.update(auto_approve_max=7, ask_confirm_max=9)

        # 查询决策
        decision = config.get_decision(risk_level=8)  # → "ask"
    """

    # 默认值
    _DEFAULT_AUTO_APPROVE_MAX = 3
    _DEFAULT_ASK_CONFIRM_MAX = 6

    def __init__(self, config_path: str | None = None):
        """
        初始化用户配置。

        Args:
            config_path: 可选的 JSON 配置文件路径。
                         为 None 时使用内置默认值（1-3放行，4-6询问，7+拒绝）。
        """
        self._auto_approve_max = self._DEFAULT_AUTO_APPROVE_MAX
        self._ask_confirm_max = self._DEFAULT_ASK_CONFIRM_MAX

        if config_path:
            self.load_from_file(config_path)

    # ──────────────────────────────
    # 核心方法
    # ──────────────────────────────

    def get_decision(self, risk_level: int) -> DecisionType:
        """
        根据风险等级返回处置决策。

        Args:
            risk_level: 1-10 的风险等级

        Returns:
            "approve" / "ask" / "reject"
        """
        if risk_level <= self._auto_approve_max:
            return "approve"
        elif risk_level <= self._ask_confirm_max:
            return "ask"
        else:
            return "reject"

    def update(
        self,
        auto_approve_max: int | None = None,
        ask_confirm_max: int | None = None,
    ) -> None:
        """
        运行时动态修改阈值。

        Args:
            auto_approve_max: 放行区间上限（含），修改后立即生效
            ask_confirm_max:  询问区间上限（含），修改后立即生效

        Raises:
            ConfigValidationError: 参数不合法时抛出

        Example:
            # 宽松策略：1-7放行，8-9询问，10拒绝
            config.update(auto_approve_max=7, ask_confirm_max=9)

            # 严格策略：仅1级放行，2-4询问，5+拒绝
            config.update(auto_approve_max=1, ask_confirm_max=4)
        """
        new_approve = auto_approve_max if auto_approve_max is not None else self._auto_approve_max
        new_ask = ask_confirm_max if ask_confirm_max is not None else self._ask_confirm_max
        self._validate(new_approve, new_ask)
        self._auto_approve_max = new_approve
        self._ask_confirm_max = new_ask

    # ──────────────────────────────
    # 文件读写
    # ──────────────────────────────

    def load_from_file(self, path: str) -> None:
        """
        从 JSON 文件加载配置，加载后立即生效。

        JSON 格式示例：
            {
              "thresholds": {
                "auto_approve_max": 5,
                "ask_confirm_max": 8
              }
            }

        Args:
            path: JSON 文件路径

        Raises:
            FileNotFoundError:   文件不存在
            ConfigValidationError: 配置值不合法
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"配置文件不存在：{path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        thresholds = data.get("thresholds", {})
        new_approve = thresholds.get("auto_approve_max", self._auto_approve_max)
        new_ask = thresholds.get("ask_confirm_max", self._ask_confirm_max)

        self._validate(new_approve, new_ask)
        self._auto_approve_max = new_approve
        self._ask_confirm_max = new_ask

    def save_to_file(self, path: str) -> None:
        """
        将当前配置保存为 JSON 文件。

        Args:
            path: 输出文件路径（不存在会自动创建）
        """
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0",
            "thresholds": {
                "auto_approve_max": self._auto_approve_max,
                "ask_confirm_max": self._ask_confirm_max,
            },
            "zone_description": {
                "approve_zone": f"风险等级 1-{self._auto_approve_max}：自动放行",
                "ask_zone": (
                    f"风险等级 {self._auto_approve_max + 1}-{self._ask_confirm_max}：询问用户"
                ),
                "reject_zone": (
                    f"风险等级 {self._ask_confirm_max + 1}-10：自动拦截"
                ),
            },
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ──────────────────────────────
    # 属性和辅助
    # ──────────────────────────────

    @property
    def auto_approve_max(self) -> int:
        """放行区间上限（只读，通过 update() 修改）。"""
        return self._auto_approve_max

    @property
    def ask_confirm_max(self) -> int:
        """询问区间上限（只读，通过 update() 修改）。"""
        return self._ask_confirm_max

    @property
    def summary(self) -> dict:
        """返回当前配置的人类可读摘要字典。"""
        return {
            "approve_zone": f"1 ~ {self._auto_approve_max}",
            "ask_zone": f"{self._auto_approve_max + 1} ~ {self._ask_confirm_max}",
            "reject_zone": f"{self._ask_confirm_max + 1} ~ 10",
        }

    def __repr__(self) -> str:
        s = self.summary
        return (
            f"UserConfig("
            f"放行: {s['approve_zone']}, "
            f"询问: {s['ask_zone']}, "
            f"拒绝: {s['reject_zone']})"
        )

    def _validate(self, auto_approve_max: int, ask_confirm_max: int) -> None:
        """
        校验阈值合法性。

        规则：0 < auto_approve_max < ask_confirm_max <= 10

        Raises:
            ConfigValidationError: 不满足约束时抛出，附带明确的错误描述
        """
        if not isinstance(auto_approve_max, int) or not isinstance(ask_confirm_max, int):
            raise ConfigValidationError("阈值必须为整数类型")
        if auto_approve_max < 1:
            raise ConfigValidationError(
                f"auto_approve_max 不能小于 1，当前值: {auto_approve_max}"
            )
        if ask_confirm_max > 10:
            raise ConfigValidationError(
                f"ask_confirm_max 不能大于 10，当前值: {ask_confirm_max}"
            )
        if auto_approve_max >= ask_confirm_max:
            raise ConfigValidationError(
                f"auto_approve_max({auto_approve_max}) 必须小于 "
                f"ask_confirm_max({ask_confirm_max})"
            )

"""分级器抽象基类。"""

from abc import ABC, abstractmethod

from risk_sdk.classifier.models import ClassifyRequest, ClassifyResult


class BaseClassifier(ABC):
    """
    风险分级器抽象基类。

    所有分级器实现都必须继承此类并实现 classify() 方法。
    这是后续替换分级算法（规则引擎 → 机器学习模型）的扩展接口。

    扩展示例：
        class MLClassifier(BaseClassifier):
            def classify(self, request: ClassifyRequest) -> ClassifyResult:
                score = self.model.predict(...)
                return ClassifyResult(risk_level=score, reason="ML模型预测")

        sdk = RiskSDK(classifier=MLClassifier())
    """

    @abstractmethod
    def classify(self, request: ClassifyRequest) -> ClassifyResult:
        """
        对一次动作执行风险分级。

        Args:
            request: 包含 task / action / thinking / step_count 的分级请求

        Returns:
            ClassifyResult，包含 risk_level（1-10）、reason 和 matched_rules
        """
        ...

    def can_classify(self, request: ClassifyRequest) -> bool:
        """
        前置检查：判断该分级器是否处理此请求。

        预留接口，用于未来实现多分级器责任链（Chain of Responsibility）。
        默认返回 True，即处理所有请求。

        Args:
            request: 分级请求

        Returns:
            True 表示该分级器负责处理，False 表示跳过交给下一个分级器
        """
        return True

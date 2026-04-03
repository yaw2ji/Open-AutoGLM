"""
审计记录管理器。

设计原则：
- 内存 + CSV 文件双写：兼顾查询性能和持久化
- 追加写模式（append-only）：不修改历史记录，符合审计要求
- 按日期自动切换日志文件：risk_audit_YYYY-MM-DD.csv
- 提供多条件组合筛选和统计摘要
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from risk_sdk.audit.models import AuditRecord, ExecutionOutcome


class AuditManager:
    """
    审计记录管理器。

    每次调用 RiskSDK.check() 后自动调用 record() 写入一条记录。
    支持按时间范围、风险等级、处置结果、任务关键词进行组合筛选，
    并可将筛选结果或全量记录导出为 CSV 文件。

    Usage:
        manager = AuditManager(log_dir="./risk_audit_logs")

        # 写入记录（由 RiskSDK 自动调用）
        manager.record(task=..., action=..., ...)

        # 查询高风险拦截记录
        records = manager.query(min_risk_level=7, outcome="rejected")

        # 导出 CSV
        manager.export_csv("./report.csv", records)

        # 查看统计摘要
        print(manager.get_stats())
    """

    def __init__(
        self,
        log_dir: str = "./risk_audit_logs",
        max_memory_records: int = 1000,
    ):
        """
        Args:
            log_dir:            审计日志目录，不存在时自动创建
            max_memory_records: 内存缓存的最大记录数，超出后丢弃最早的记录
        """
        self._records: list[AuditRecord] = []
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._max_memory_records = max_memory_records

    # ──────────────────────────────
    # 写入
    # ──────────────────────────────

    def record(
        self,
        task: str,
        action: dict[str, Any],
        thinking: str,
        risk_level: int,
        matched_rules: list[str],
        outcome: ExecutionOutcome,
        step_count: int,
        user_decision: bool | None = None,
    ) -> AuditRecord:
        """
        写入一条审计记录。

        同时写入内存缓存和 CSV 文件。
        内存缓存超出 max_memory_records 时，丢弃最早的记录（FIFO）。

        Args:
            task:          用户原始任务文本
            action:        动作字典
            thinking:      模型推理文本
            risk_level:    风险等级 1-10
            matched_rules: 命中的规则名称列表
            outcome:       处置结果（approved / asked / rejected）
            step_count:    执行步骤编号
            user_decision: 询问时用户的决策（None 表示未询问）

        Returns:
            创建的 AuditRecord 对象
        """
        audit_record = AuditRecord.create(
            task=task,
            action=action,
            thinking=thinking,
            risk_level=risk_level,
            matched_rules=matched_rules,
            outcome=outcome,
            step_count=step_count,
            user_decision=user_decision,
        )

        # 写入内存缓存
        self._records.append(audit_record)
        if len(self._records) > self._max_memory_records:
            self._records.pop(0)

        # 追加写入 CSV 文件
        self._write_to_file(audit_record)

        return audit_record

    # ──────────────────────────────
    # 查询
    # ──────────────────────────────

    def query(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        min_risk_level: int | None = None,
        max_risk_level: int | None = None,
        outcome: ExecutionOutcome | None = None,
        task_keyword: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        """
        从内存缓存中按条件筛选审计记录。

        所有条件均为可选，多个条件取交集（AND 关系）。

        Args:
            start_time:     时间范围起点（含），None 表示不限
            end_time:       时间范围终点（含），None 表示不限
            min_risk_level: 风险等级下限（含），None 表示不限
            max_risk_level: 风险等级上限（含），None 表示不限
            outcome:        处置结果过滤（approved / asked / rejected），None 表示不限
            task_keyword:   任务文本关键词（模糊匹配），None 表示不限
            limit:          最多返回记录数，按时间倒序截取

        Returns:
            符合条件的 AuditRecord 列表（时间倒序）

        Example:
            # 查询今天所有被拦截的高风险操作
            records = manager.query(
                start_time=datetime.now().replace(hour=0, minute=0, second=0),
                min_risk_level=7,
                outcome="rejected",
            )
        """
        results = list(self._records)  # 复制一份，不修改原数据

        if start_time:
            results = [r for r in results if r.timestamp >= start_time]
        if end_time:
            results = [r for r in results if r.timestamp <= end_time]
        if min_risk_level is not None:
            results = [r for r in results if r.risk_level >= min_risk_level]
        if max_risk_level is not None:
            results = [r for r in results if r.risk_level <= max_risk_level]
        if outcome:
            results = [r for r in results if r.outcome == outcome]
        if task_keyword:
            kw = task_keyword.lower()
            results = [r for r in results if kw in r.task.lower()]

        # 按时间倒序，取最近的 limit 条
        results.sort(key=lambda r: r.timestamp, reverse=True)
        return results[:limit]

    # ──────────────────────────────
    # 导出
    # ──────────────────────────────

    def export_csv(
        self,
        output_path: str,
        records: list[AuditRecord] | None = None,
    ) -> str:
        """
        将审计记录导出为 CSV 文件。

        Args:
            output_path: 输出文件路径，父目录不存在时自动创建
            records:     要导出的记录列表；为 None 时导出全部内存记录

        Returns:
            实际写入的文件路径（绝对路径字符串）

        Example:
            # 导出所有记录
            path = manager.export_csv("./full_report.csv")

            # 导出筛选结果
            high_risk = manager.query(min_risk_level=7)
            path = manager.export_csv("./high_risk.csv", high_risk)
        """
        if records is None:
            records = self._records

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=AuditRecord.CSV_FIELDS)
            writer.writeheader()
            for record in records:
                writer.writerow(record.to_dict())

        return str(out_path.resolve())

    def load_from_file(self, log_file: str | None = None) -> int:
        """
        从 CSV 文件加载历史记录到内存缓存。

        Args:
            log_file: CSV 文件路径；为 None 时加载当天的日志文件

        Returns:
            成功加载的记录数量
        """
        if log_file is None:
            log_file = str(self._get_log_filepath())

        file_path = Path(log_file)
        if not file_path.exists():
            return 0

        loaded = 0
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    record = self._row_to_record(row)
                    self._records.append(record)
                    loaded += 1
                except Exception:
                    continue  # 跳过格式错误的行

        return loaded

    # ──────────────────────────────
    # 统计
    # ──────────────────────────────

    def get_stats(self, records: list[AuditRecord] | None = None) -> dict:
        """
        返回统计摘要。

        Args:
            records: 统计来源；为 None 时统计全部内存记录

        Returns:
            包含以下字段的字典：
            - total:              总记录数
            - outcome_counts:     各处置结果的数量 {approved/asked/rejected: int}
            - outcome_rates:      各处置结果的占比 {approved/asked/rejected: float}
            - level_distribution: 各风险等级的数量 {1: int, 2: int, ...}
            - avg_risk_level:     平均风险等级
            - high_risk_count:    高风险（>= 7）记录数
        """
        if records is None:
            records = self._records

        total = len(records)
        if total == 0:
            return {
                "total": 0,
                "outcome_counts": {"approved": 0, "asked": 0, "rejected": 0},
                "outcome_rates": {"approved": 0.0, "asked": 0.0, "rejected": 0.0},
                "level_distribution": {},
                "avg_risk_level": 0.0,
                "high_risk_count": 0,
            }

        # 处置结果统计
        outcome_counts: dict[str, int] = {"approved": 0, "asked": 0, "rejected": 0}
        for r in records:
            if r.outcome in outcome_counts:
                outcome_counts[r.outcome] += 1

        outcome_rates = {k: round(v / total, 4) for k, v in outcome_counts.items()}

        # 风险等级分布
        level_dist: dict[int, int] = {}
        for r in records:
            level_dist[r.risk_level] = level_dist.get(r.risk_level, 0) + 1

        avg_level = sum(r.risk_level for r in records) / total
        high_risk = sum(1 for r in records if r.risk_level >= 7)

        return {
            "total": total,
            "outcome_counts": outcome_counts,
            "outcome_rates": outcome_rates,
            "level_distribution": dict(sorted(level_dist.items())),
            "avg_risk_level": round(avg_level, 2),
            "high_risk_count": high_risk,
        }

    def print_stats(self, records: list[AuditRecord] | None = None) -> None:
        """打印统计摘要到控制台。"""
        stats = self.get_stats(records)
        print("\n" + "=" * 50)
        print("[风险审计统计摘要]")
        print("=" * 50)
        print(f"总记录数：{stats['total']}")
        print(f"平均风险等级：{stats['avg_risk_level']}")
        print(f"高风险记录（>=7级）：{stats['high_risk_count']} 条")
        print("-" * 30)
        print("处置结果分布：")
        for outcome, count in stats["outcome_counts"].items():
            label = {"approved": "[放行]", "asked": "[询问]", "rejected": "[拦截]"}[outcome]
            rate = stats["outcome_rates"][outcome] * 100
            print(f"  {label}: {count} 条 ({rate:.1f}%)")
        print("-" * 30)
        print("风险等级分布：")
        for level, count in stats["level_distribution"].items():
            bar = "|" * count
            print(f"  等级 {level:2d}: {bar} ({count})")
        print("=" * 50 + "\n")

    # ──────────────────────────────
    # 内部辅助
    # ──────────────────────────────

    def _get_log_filepath(self) -> Path:
        """按当天日期生成日志文件路径，如 risk_audit_2026-04-02.csv。"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self._log_dir / f"risk_audit_{date_str}.csv"

    def _write_to_file(self, record: AuditRecord) -> None:
        """追加写入一条记录到当天的 CSV 文件（含表头自动检测）。"""
        log_path = self._get_log_filepath()
        file_exists = log_path.exists() and log_path.stat().st_size > 0

        with open(log_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=AuditRecord.CSV_FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(record.to_dict())

    def _row_to_record(self, row: dict) -> AuditRecord:
        """将 CSV 行字典反序列化为 AuditRecord 对象。"""
        import json as _json

        # 解析 user_decision
        ud_raw = row.get("user_decision", "")
        if ud_raw == "Y":
            user_decision = True
        elif ud_raw == "N":
            user_decision = False
        else:
            user_decision = None

        return AuditRecord(
            record_id=row["record_id"],
            timestamp=datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S"),
            task=row["task"],
            action_type=row["action_type"],
            action_raw=_json.loads(row["action_raw"]) if row["action_raw"] else {},
            thinking_snippet=row.get("thinking_snippet", ""),
            risk_level=int(row["risk_level"]),
            matched_rules=row["matched_rules"].split("|") if row["matched_rules"] else [],
            outcome=row["outcome"],  # type: ignore
            user_decision=user_decision,
            step_count=int(row.get("step_count", 0)),
        )

    @property
    def record_count(self) -> int:
        """当前内存缓存中的记录数。"""
        return len(self._records)

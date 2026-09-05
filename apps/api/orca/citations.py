"""引用校验与收尾(计划书 §3.3 v1.2/v1.3)。

- 报告中的 [n] 由确定性 citation_map 映射到 evidence_id, n 只在展示层有意义
- 校验失败的处理是修订、删除或**降级**对应断言(降级 = 改写为
  "据来源标题, 未经正文核实"并标注), 不能只删脚注留下无证据结论
- 修订的 LLM 调用同样入账(§3.6 计账范围含引用修订)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .evidence import CandidateEvidence

_CITE_RE = re.compile(r"\[(\d{1,3})\]")   # [0]-[999];[x] 非数字不算引用
DEGRADE_NOTE = "(据来源标题,未经正文核实)"


@dataclass
class CitationIssue:
    n: str    # 报告中的无效引用编号
    kind: str  # "out_of_range" | "zero"


@dataclass
class CheckResult:
    report_md: str
    evidences: list[CandidateEvidence]
    citation_map: dict[str, str] = field(default_factory=dict)
    issues: list[CitationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.issues


def check_report(
    report_md: str, evidences: list[CandidateEvidence]
) -> CheckResult:
    """扫描 [n] 引用, 构建 citation_map 并标记无效引用。"""
    id_by_n = {str(i + 1): e.evidence_id
               for i, e in enumerate(evidences) if e.evidence_id}
    issues: list[CitationIssue] = []
    cited: dict[str, str] = {}
    for m in _CITE_RE.finditer(report_md):
        n = m.group(1)
        if n == "0":
            issues.append(CitationIssue(n=n, kind="zero"))
            continue
        if n in id_by_n:
            cited[n] = id_by_n[n]
        else:
            issues.append(CitationIssue(n=n, kind="out_of_range"))
    return CheckResult(report_md=report_md, evidences=evidences,
                       citation_map=cited, issues=issues)


def degrade_citations(
    report_md: str, evidences: list[CandidateEvidence]
) -> str:
    """程序化兜底:无效 [n] 移除并在句尾加"未经正文核实"标注。

    断言保留但明确降级, 不留下无证据结论(§3.3)。
    """
    valid_ns = {str(i + 1) for i in range(len(evidences))}
    invalid = {m.group(1) for m in _CITE_RE.finditer(report_md)
               if m.group(1) not in valid_ns or m.group(1) == "0"}
    if not invalid:
        return report_md

    out_lines: list[str] = []
    for line in report_md.split("\n"):
        if not any(f"[{n}]" in line for n in invalid):
            out_lines.append(line)
            continue
        for n in sorted(invalid, key=len, reverse=True):
            line = line.replace(f"[{n}]", "")
        if not line.rstrip().endswith(DEGRADE_NOTE):
            line = line.rstrip() + DEGRADE_NOTE
        out_lines.append(line)
    return "\n".join(out_lines)


def revise_report(
    report_md: str,
    evidences: list[CandidateEvidence],
    chat,  # LLMClient.chat 同签名: (messages, *, max_tokens, tier) -> LLMResult
    *,
    max_tokens: int = 8192,
) -> tuple[str, dict]:
    """一次 LLM 修订(§3.3);仍失败 → 程序化降级兜底。返回 (报告, usage)。"""
    check = check_report(report_md, evidences)
    if check.valid:
        return report_md, {}

    bad_ns = ", ".join(sorted({i.n for i in check.issues}))
    allowed = "\n".join(
        f"[{i + 1}] = {e.evidence_id}(来源: {e.title})"
        for i, e in enumerate(evidences) if e.evidence_id)
    prompt = (
        "以下研究报告含有无效引用标记,必须修正。\n"
        f"无效引用: [{bad_ns}]\n"
        "只允许引用下列有效证据编号,禁止编造其他编号,禁止添加 Markdown 链接:\n"
        f"{allowed}\n\n"
        "无效引用所在断言若无法改用有效证据支持,请直接删除该断言或改写为不引用"
        "任何来源的通用表述。\n\n报告全文:\n"
        f"{report_md}"
    )
    result = chat([{"role": "user", "content": prompt}], max_tokens=max_tokens,
                  tier="daily")
    fixed = result.content or report_md
    recheck = check_report(fixed, evidences)
    if recheck.valid:
        return fixed, result.usage
    return degrade_citations(fixed, evidences), result.usage

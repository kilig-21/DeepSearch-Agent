const stopReasons: Record<string, string> = {
  evidence_sufficient: "证据已充分",
  no_new_evidence: "未发现新证据",
  max_rounds: "达到轮次上限",
  total_budget_exhausted: "总预算已用完",
  budget_exhausted: "研究预算已用完",
  page_budget_exhausted: "达到页数上限",
  timeout: "达到时间上限",
  single_pass: "单轮研究完成",
  execution_error: "执行出错",
  cancelled: "手动停止",
  interrupted: "任务中断",
  cancelled_by_user: "手动停止",
  duplicate_queries: "没有新的搜索方向",
};

export function stopReasonLabel(value: string) {
  return stopReasons[value] ?? value;
}

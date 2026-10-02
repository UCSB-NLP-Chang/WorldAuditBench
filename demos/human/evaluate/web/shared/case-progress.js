/* Pure case-level projection; permissions remain supplied by the API. */
export function caseStatus(item) {
  if ([item.completed_explorers,item.submitted_answers,item.received_answers,item.reviewed_answers].some(v=>v==null)) return '统计暂不可用';
  if (!item.completed_explorers && !item.active_explorers && !item.received_answers) return '未开始';
  if (item.received_answers < item.submitted_answers) return '答案同步中';
  if (item.reviewed_answers < item.received_answers) return item.active_reviews > 0 ? '复核中' : '待复核';
  return item.received_answers > 0 ? '当前答案已复核' : '探索中';
}
export function groupCases(group, records) {
  const grouped = new Map();
  for (const item of group?.cases || []) grouped.set(item.id,{...item,status:caseStatus(item),records:[]});
  for (const record of records) {
    const id=record.case_progress?.id || record.task_id;
    if(grouped.has(id)) grouped.get(id).records.push(record);
  }
  return [...grouped.values()];
}

"""Binary review options shared with the evaluation client."""
JUDGMENT_OPTIONS = {
    'correct': {'category_mismatch': '类别选错（不影响 bug 判定）'},
    'incorrect': {
        'off_target': '未命中目标 bug（报告的是另一种异常）',
        'normal_behavior': '把正常现象当作 bug',
        'wrong_object': '异常对象识别错误',
        'wrong_location': '异常位置或场景识别错误',
        'contradictory_description': '关键异常现象描述错误（与目标异常矛盾）',
        'wrong_conditions': '关键触发条件错误（导致异常结论不成立）',
        'wrong_impact': '关键影响描述错误（例如将视觉异常误报为功能失效）',
        'unclear_description': '只笼统说有问题，未说明具体异常',
        'inconsistent_description': '描述自相矛盾，无法确定报告的异常',
        'missed_bug': '漏检（报告未发现 bug）',
        'other': '其他（后续复查 bug 实现）',
    },
}


def reason_options(outcome):
    if outcome == 'none':
        return {'correct': {}, 'incorrect': {k: JUDGMENT_OPTIONS['incorrect'][k] for k in ('missed_bug', 'other')}}
    return {'correct': JUDGMENT_OPTIONS['correct'], 'incorrect': {k: v for k, v in JUDGMENT_OPTIONS['incorrect'].items() if k != 'missed_bug'}}

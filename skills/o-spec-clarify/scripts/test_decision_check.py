#!/usr/bin/env python3
"""decision_check.py 的自测：形状校验、答复解析、推荐兜底、推迟、轮次、跨轮编号稳定。

用法：python3 skills/o-spec-clarify/scripts/test_decision_check.py
退出码 0 = 全过；1 = 有失败用例。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / 'decision_check.py'
FAILURES = []


def check(name, cond, detail=''):
    if cond:
        print('  ok   ' + name)
    else:
        print('  FAIL ' + name + (' :: ' + detail if detail else ''))
        FAILURES.append(name)


def run_script(ctx, expect_code=0):
    with tempfile.TemporaryDirectory() as td:
        ctx = with_ddir(ctx, td)
        cpath = Path(td) / 'context.json'
        cpath.write_text(json.dumps(ctx, ensure_ascii=False), encoding='utf-8')
        p = subprocess.run([sys.executable, str(SCRIPT), '--context', str(cpath)],
                           capture_output=True, text=True)
        out = {}
        op = Path(td) / 'decision_output.json'
        if op.is_file():
            out = json.loads(op.read_text(encoding='utf-8'))
        return p, out, Path(td)


# 用例自建的 decisions_dir 目录（仓外，生命周期由用例自己管）
_DDIRS = []


def ddir():
    """建一个仓外的 decisions_dir，返回其路径。

    decisions_dir 是**节点工作目录**下的目录，不是仓内的 spec_dir——
    脚本刻意不回退，所以每个用例都得给一个仓外的路径。用例常常要在
    脚本跑完后还读这个目录，所以不能用 run_script 的临时目录（会被删）。"""
    import tempfile as _tf
    d = Path(_tf.mkdtemp(prefix='node_decisions_'))
    _DDIRS.append(d)
    return d


def with_ddir(ctx, td):
    """给 ctx 补上仓外的 decisions_dir（除非调用方已显式给了）。

    目录挂在 spec_dir 的**兄弟**位置上（仍在仓外），这样同一用例内多次调用
    run_script 会落到同一个目录——跨轮状态才能延续。"""
    if 'decisions_dir' not in ctx:
        ctx = dict(ctx)
        spec = Path(ctx.get('spec_dir', td))
        d = spec.parent / (spec.name + '_node_decisions')
        d.mkdir(exist_ok=True)
        ctx['decisions_dir'] = str(d)
    return ctx


def item(key='enum-values', q='订单状态展示哪些取值？', impact='high',
         opts=None, rec='A', reason='后端只返回 4 个对外值',
         evidence=None):
    return {
        'key': key,
        'question': q,
        'impact': impact,
        'options': opts or [
            {'key': 'A', 'label': '只展示 4 个对外状态', 'impact': '验收标准可写死'},
            {'key': 'B', 'label': '展示全部 6 个，未确认的置灰', 'impact': '需补置灰态验收'},
        ],
        'recommendation_key': rec,
        'recommendation_reason': reason,
        'evidence': ([{'claim': 'orderStatus 只有 4 个对外值',
                       'verified': True, 'ref': 'src/api/order.ts:42'}]
                     if evidence is None else evidence),
    }


def main():
    print('case 1: 首轮无答复 → 全部取推荐，round=1')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'spec'
        spec.mkdir()
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': [item()]})
        check('exit 0', p.returncode == 0, p.stderr)
        check('round == 1', out.get('round') == 1, str(out.get('round')))
        check('pending == 1', out.get('pending_count') == 1, str(out.get('pending_count')))
        check('answered == 0', out.get('answered_count') == 0)
        check('deferred == 0', out.get('deferred_count') == 0)
        check('chosen == A', out['items'][0]['chosen_key'] == 'A')
        check('decided_by == recommended', out['items'][0]['decided_by'] == 'recommended')
        sheet = (Path(out['decisions_dir']) / 'decisions.md').read_text(encoding='utf-8')
        check('sheet 有推荐星标 ⭐', '⭐' in sheet)
        check('sheet 标第 1 轮', '第 1 轮' in sheet)
        check('sheet 写明未答按推荐', '自动按推荐' in sheet)
        state = json.loads((Path(out['decisions_dir']) / 'decisions.json').read_text(encoding='utf-8'))
        check('state 落盘', len(state['items']) == 1)

    print('case 2: 答复解析 —— 选项 / 自定 / 待查')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'spec'
        spec.mkdir()
        ds = [item(key='d1'), item(key='d2'), item(key='d3')]
        p, out, _ = run_script({
            'spec_dir': str(spec), 'decisions': ds,
            'approval_feedback': 'D1=B, D2=自定:走 D 方案，先兼容旧接口, 再切新接口。D3=暂缓'})
        check('exit 0', p.returncode == 0, p.stderr)
        by = {it['id']: it for it in out['items']}
        check('D1 选 B', by['D1']['chosen_key'] == 'B', str(by['D1']['chosen_key']))
        check('D1 人答', by['D1']['decided_by'] == 'human')
        check('D2 自定义', by['D2']['chosen_key'] == 'custom')
        check('D2 文本保留逗号', '兼容旧接口' in by['D2']['custom_text'])
        check('D3 推迟', by['D3']['chosen_key'] == 'defer')
        check('answered == 2', out['answered_count'] == 2, str(out['answered_count']))
        check('deferred == 1', out['deferred_count'] == 1, str(out['deferred_count']))
        check('pending == 0', out['pending_count'] == 0, str(out['pending_count']))

    print('case 3: 未提到的项仍取推荐')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'spec'
        spec.mkdir()
        ds = [item(key='d1'), item(key='d2'), item(key='d3')]
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': ds,
                                'approval_feedback': 'D2=B'})
        by = {it['id']: it for it in out['items']}
        check('D1 仍取推荐', by['D1']['chosen_key'] == 'A' and by['D1']['decided_by'] == 'recommended')
        check('D3 仍取推荐', by['D3']['chosen_key'] == 'A' and by['D3']['decided_by'] == 'recommended')
        check('pending == 2', out['pending_count'] == 2, str(out['pending_count']))

    print('case 4: 形状非法 → exit 1 且不写任何文件')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'spec'
        spec.mkdir()
        bad = [
            item(key='x', opts=[{'key': 'A', 'label': '只有一个', 'impact': 'x'}]),   # options < 2
            item(key='y', rec='Z'),                                                  # rec 不在 options
            item(key='z', evidence=[]),                                              # evidence 空
            item(key='w', rec=None),                                                 # 缺 recommendation_key
            item(key='v', impact='critical'),                                        # impact 非三档
        ]
        for i, b in enumerate(bad):
            p, out, _ = run_script({'spec_dir': str(spec), 'decisions': [b]})
            check('非法形状 {} exit 1'.format(i), p.returncode == 1, p.stdout + p.stderr)
            check('非法形状 {} 未落盘'.format(i),
                  not out.get('items'))
        check('非法形状后无清单', not out.get('decision_sheet_path'))

    print('case 5: 跨轮 —— 同 key 不改号、新 key 续号、round=2')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'spec'
        spec.mkdir()
        p, out1, _ = run_script({'spec_dir': str(spec), 'decisions': [item(key='d1'), item(key='d2')]})
        check('首轮两个项 D1/D2',
              [it['id'] for it in out1['items']] == ['D1', 'D2'],
              str([it['id'] for it in out1['items']]))
        p, out2, _ = run_script({
            'spec_dir': str(spec),
            'decisions': [item(key='d1'), item(key='d3')],   # d1 重复 + d3 新增
            'approval_feedback': 'D1=B'})
        check('第二轮 round == 2', out2['round'] == 2, str(out2['round']))
        ids = [it['id'] for it in out2['items']]
        check('编号稳定且续号', ids == ['D1', 'D2', 'D3'], str(ids))
        by = {it['id']: it for it in out2['items']}
        check('D1 沿用旧号并采用新答复', by['D1']['chosen_key'] == 'B', str(by['D1']['chosen_key']))
        check('D2 沿用旧选择（无答复取推荐）', by['D2']['chosen_key'] == 'A')
        check('D3 新项取推荐', by['D3']['chosen_key'] == 'A')

    print('case 6: 上限 —— 超过 max_decisions 不再硬失败（全列，按影响排序）')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'spec'
        spec.mkdir()
        ds = [item(key='k%d' % i) for i in range(5)]
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': ds, 'max_decisions': 3})
        check('超上限仍 exit 0（全列，不截断）', p.returncode == 0, p.stdout + p.stderr)
        check('5 项全在清单里', len(out.get('items', [])) == 5, str(len(out.get('items', []))))
        check('清单已生成', bool(out.get('decision_sheet_path')))
        # 真正非法的形状仍然 exit 1
        p, out, _ = run_script({'spec_dir': str(spec),
                                'decisions': [item(key='bad', opts=[{'key': 'A', 'label': 'x', 'impact': 'y'}])]})
        check('非法形状仍 exit 1', p.returncode == 1, p.stdout + p.stderr)

    print('case 7: 无法解析的答复片段不猜')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'spec'
        spec.mkdir()
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': [item(key='d1')],
                                'approval_feedback': 'D1=Q, D9=不存在'})
        by = {it['id']: it for it in out['items']}
        check('D1 非法选项保留推荐', by['D1']['chosen_key'] == 'A', str(by['D1']['chosen_key']))
        check('D1 有 note', bool(by['D1']['note']), str(by['D1']['note']))
        check('无法归属片段被记录', len(out['feedback_unparsed']) == 1,
              str(out['feedback_unparsed']))

    print('case 8: spec_dir 缺失 → exit 2（fail-closed）')
    p, out, _ = run_script({'decisions': []})
    check('exit 2', p.returncode == 2, str(p.returncode) + p.stdout + p.stderr)

    print('case 9: 轮次闸 —— 第三轮被拒（平台不限制 amend 次数，靠脚本兜底）')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'spec'
        spec.mkdir()
        run_script({'spec_dir': str(spec), 'decisions': [item(key='d1')]})          # round 1
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': [item(key='d1')],
                                'approval_feedback': 'D1=B'})                       # round 2
        check('第二轮成功', p.returncode == 0, p.stderr)
        check('round == 2', out.get('round') == 2, str(out.get('round')))
        check('round_exhausted == True', out.get('round_exhausted') is True,
              str(out.get('round_exhausted')))
        # 同一份答复重跑 → 不进位；无反馈重跑（平台 retry / 无 reason 的 reject）→ 不进位
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': [item(key='d1')],
                                'approval_feedback': 'D1=B'})
        check('同答复重跑不进位', p.returncode == 0 and out.get('round') == 2,
              p.stdout + p.stderr)
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': [item(key='d1')]})
        check('无反馈重跑不进位且保留人答复',
              p.returncode == 0 and out.get('round') == 2
              and out['items'][0]['chosen_key'] == 'B', p.stdout + p.stderr)
        state_path = Path(out['decisions_dir']) / 'decisions.json'
        state_before = state_path.read_text(encoding='utf-8')
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': [item(key='d1')],
                                'approval_feedback': 'D1=A'})                       # round 3 → 拒
        check('第三轮 exit 1', p.returncode == 1, p.stdout + p.stderr)
        check('第三轮提示轮次耗尽', '轮次已耗尽' in p.stderr, p.stderr)
        check('第三轮未改状态文件',
              state_path.read_text(encoding='utf-8') == state_before)

    print('case 10: 第一轮 round_exhausted == False；max_rounds 可调')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'spec'
        spec.mkdir()
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': [item(key='d1')]})
        check('第一轮未耗尽', out.get('round_exhausted') is False, str(out.get('round_exhausted')))
        spec2 = Path(td) / 'spec2'
        spec2.mkdir()
        p, out, _ = run_script({'spec_dir': str(spec2), 'decisions': [item(key='d1')],
                                'max_rounds': 1})
        check('max_rounds=1 时首轮即耗尽', out.get('round_exhausted') is True,
              str(out.get('round_exhausted')))
        p, out, _ = run_script({'spec_dir': str(spec2), 'decisions': [item(key='d2')]})
        check('无反馈重跑不进位（仍第 1 轮）',
              p.returncode == 0 and out.get('round') == 1, p.stdout + p.stderr)
        p, out, _ = run_script({'spec_dir': str(spec2), 'decisions': [item(key='d2')],
                                'approval_feedback': 'D1=A'})
        check('max_rounds=1 时新答复进位被拒', p.returncode == 1, p.stdout + p.stderr)

    print('case 11: output 自足 —— sheet_markdown 进 report')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'spec'
        spec.mkdir()
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': [item(key='d1')]})
        check('report 含 sheet_markdown', isinstance(out.get('sheet_markdown'), str))
        check('sheet_markdown 含问题原文', '订单状态展示哪些取值' in out.get('sheet_markdown', ''))
        check('sheet_markdown 含选项 key', '| A |' in out.get('sheet_markdown', ''))
        check('sheet_markdown 含推荐标记', '⭐' in out.get('sheet_markdown', ''))

    print('case 12: 「待查」不是 defer 关键字（它常被用作选项 label）')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'spec'
        spec.mkdir()
        # 选项里有一项 label 叫「待查：先导出数据再定」——人答 D1=待查 是"选那个选项"
        opts = [
            {'key': 'A', 'label': '按推荐口径实现', 'impact': '可直接开工'},
            {'key': 'B', 'label': '待查：先导出目标环境数据再定', 'impact': '决策延期'},
        ]
        d = item(key='d1', opts=opts, rec='A')
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': [d],
                                'approval_feedback': 'D1=待查'})
        by = {it['id']: it for it in out['items']}
        check('D1=待查 不被解析成 defer', by['D1']['chosen_key'] != 'defer',
              str(by['D1']['chosen_key']))
        check('D1=待查 保留推荐并记 note',
              by['D1']['chosen_key'] == 'A' and bool(by['D1']['note']),
              str(by['D1']))
        check('deferred_count == 0', out['deferred_count'] == 0, str(out['deferred_count']))
        # 显式用「暂缓」才是 defer
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions': [d],
                                'approval_feedback': 'D1=暂缓'})
        by = {it['id']: it for it in out['items']}
        check('D1=暂缓 才是 defer', by['D1']['chosen_key'] == 'defer',
              str(by['D1']['chosen_key']))

    print('case 13: decisions_dir 与 spec_dir 分离 —— 状态不落仓')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 'openspec' / '20260101-000000-x'
        spec.mkdir(parents=True)
        node = Path(td) / 'node'
        node.mkdir()
        ddir = node / 'decisions'
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                                'decisions': [item(key='d1')]})
        check('exit 0', p.returncode == 0, p.stderr)
        check('状态文件在 decisions_dir', (ddir / 'decisions.json').is_file())
        check('清单在 decisions_dir', (ddir / 'decisions.md').is_file())
        check('仓内 spec_dir 无 decisions.json', not (spec / 'decisions.json').exists())
        check('仓内 spec_dir 无 decisions.md', not (spec / 'decisions.md').exists())
        check('report.decisions_dir 指向节点目录',
              out.get('decisions_dir') == str(ddir.resolve()),
              str(out.get('decisions_dir')))
        check('report.spec_dir 指向仓内', out.get('spec_dir') == str(spec.resolve()),
              str(out.get('spec_dir')))
        # 第二轮：状态在节点目录，轮次闸仍然生效
        p, out2, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                                 'decisions': [item(key='d1')],
                                 'approval_feedback': 'D1=B'})
        check('第二轮 round == 2', out2.get('round') == 2, str(out2.get('round')))
        p, out3, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                                 'decisions': [item(key='d1')]})
        check('无反馈重跑不进位（仍第 2 轮）',
              p.returncode == 0 and out3.get('round') == 2, p.stdout + p.stderr)
        p, out4, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                                 'decisions': [item(key='d1')],
                                 'approval_feedback': 'D1=A'})
        check('新答复第三轮被拒', p.returncode == 1, p.stdout + p.stderr)

    print('case 14: decisions_dir 缺失 → 报错，**不回退到 spec_dir**（防状态落仓）')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 's'
        spec.mkdir()
        # 直接调脚本，绕过 with_ddir 的自动补全——这里要的就是"缺失"这个场景
        cpath = Path(td) / 'ctx.json'
        cpath.write_text(json.dumps({'spec_dir': str(spec),
                                     'decisions': [item(key='d1')]}, ensure_ascii=False),
                         encoding='utf-8')
        p = subprocess.run([sys.executable, str(SCRIPT), '--context', str(cpath)],
                           capture_output=True, text=True)
        out = {}
        check('exit 2（fail-closed）', p.returncode == 2, str(p.returncode) + p.stdout)
        check('提示缺 decisions_dir', 'decisions_dir' in p.stderr, p.stderr)
        check('仓内无 decisions.json', not (spec / 'decisions.json').exists())
        check('仓内无 decisions.md', not (spec / 'decisions.md').exists())

    print('case 15: 选项 key 优先于 defer 关键字')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 's'
        spec.mkdir()
        ddir = Path(td) / 'd'
        d = item(key='d1')
        d['options'] = [{'key': '暂缓', 'label': '先查数据再定', 'impact': '延期'},
                        {'key': 'B', 'label': '立即实现', 'impact': '开工'}]
        d['recommendation_key'] = 'B'
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                                'decisions': [d], 'approval_feedback': 'D1=暂缓'})
        by = {it['id']: it for it in out['items']}
        check('选了同名选项而非 defer', by['D1']['chosen_key'] == '暂缓',
              str(by['D1']['chosen_key']))
        check('decided_by == human', by['D1']['decided_by'] == 'human')
        check('deferred_count == 0', out['deferred_count'] == 0, str(out['deferred_count']))

    print('case 16: 答复格式健壮性（前导零 / 全称「自定义」）')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 's'
        spec.mkdir()
        ddir = Path(td) / 'd'
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                                'decisions': [item(key='d1')], 'approval_feedback': 'D01=B'})
        check('D01=B 等价 D1=B', out['items'][0]['chosen_key'] == 'B',
              str(out['items'][0]['chosen_key']))
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 's'
        spec.mkdir()
        ddir = Path(td) / 'd'
        p, out, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                                'decisions': [item(key='d1')],
                                'approval_feedback': 'D1=自定义:走 D 方案'})
        check('全称「自定义：」被识别',
              out['items'][0]['chosen_key'] == 'custom' and '走 D 方案' in out['items'][0]['custom_text'],
              str(out['items'][0].get('custom_text')))

    print('case 17: 编号跨轮稳定（按影响排序只改展示顺序）')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 's'
        spec.mkdir()
        ddir = Path(td) / 'd'
        p, out1, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                                 'decisions': [item(key='low1', impact='low'),
                                               item(key='high1', impact='high')]})
        ids1 = {it['key']: it['id'] for it in out1['items']}
        p, out2, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                                 'decisions': [item(key='low1', impact='low'),
                                               item(key='high1', impact='high'),
                                               item(key='high2', impact='high')],
                                 'approval_feedback': 'D1=B'})
        ids2 = {it['key']: it['id'] for it in out2['items']}
        check('已有项编号不变', all(ids1[k] == ids2[k] for k in ids1),
              str(ids1) + ' vs ' + str(ids2))
        by = {it['id']: it for it in out2['items']}
        check('D1 仍是 low1', by['D1']['key'] == 'low1', str(by['D1']['key']))
        check('答复落在正确项上', by['D1']['chosen_key'] == 'B', str(by['D1']['chosen_key']))
        sheet = (ddir / 'decisions.md').read_text(encoding='utf-8')
        order = [ln.split('　')[0].replace('## ', '') for ln in sheet.split('\n') if ln.startswith('## D')]
        check('清单按影响降序展示', order == ['D2', 'D3', 'D1'], str(order))

    print('case 19: 推荐项必填 / impact 三档 / 全列不截断')
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 's'
        spec.mkdir()
        ddir = Path(td) / 'd'
        d = item(key='d1')
        del d['recommendation_key']
        p, o, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                              'decisions': [d]})
        check('缺 recommendation_key → exit 1', p.returncode == 1, p.stdout + p.stderr)
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 's'
        spec.mkdir()
        ddir = Path(td) / 'd'
        p, o, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                              'decisions': [item(key='d1', impact='banana')]})
        check('impact 非法 → exit 1', p.returncode == 1, p.stdout + p.stderr)
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / 's'
        spec.mkdir()
        ddir = Path(td) / 'd'
        ds = [item(key='k%d' % i) for i in range(30)]
        p, o, _ = run_script({'spec_dir': str(spec), 'decisions_dir': str(ddir),
                              'decisions': ds})
        check('30 项仍全列出', p.returncode == 0 and len(o.get('items', [])) == 30,
              str(len(o.get('items', []))))
        check('decisions_count 正确', o.get('decisions_count') == 30, str(o.get('decisions_count')))
        check('top_n 存在', 'top_n' in o, str(list(o.keys())))

    print()
    if FAILURES:
        print('FAILED: %d' % len(FAILURES))
        for f in FAILURES:
            print('  - ' + f)
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())

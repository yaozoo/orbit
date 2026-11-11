#!/usr/bin/env python3
"""decision_check.py：澄清决策闸门的确定性部分（编号 / 答复解析 / 默认取推荐 / 落盘 / 计数）。

设计原则照抄 prd-repo-decision-gate-v3 的 scripts/decision_check.py（MIT 同源思路，
本次重写为单仓语义）：机械部分归脚本，LLM 只做语义判断（挑出哪些是"人必须拍板的决策项"）。
理由与该插件一致——pending_count / rerun_count 驱动回环与闸门行为，算错即无谓重跑
或"未落实的决策被放行"。

用法：decision_check.py --context <ctx.json>
  ctx = {
    "spec_dir": "/abs/path/openspec/20260101-000000-slug",  # 仓内三件套目录（只用于定位）
    "decisions_dir": "/abs/path/节点工作目录/decisions",     # 清单与轮次状态落这里（不落仓）
    "decisions": [ {id?, key, question, options, recommendation_key,
                    recommendation_reason, evidence, impact} ],   # LLM 挑刺产出，可空
    "approval_feedback": "D1=A, D2=自定:xxx, D3=暂缓",          # 可空（上下文 _approval_feedback）
    "max_rounds": 2                                              # 可选，澄清轮次硬上限（1..5，默认 2）
  }
  → 落 <decisions_dir>/{decisions.json, decisions.md}，
    并在 ctx 同目录写 decision_output.json（decision_sheet_path / decisions_dir /
    items / top_n / pending_count / answered_count / deferred_count / round /
    round_exhausted / sheet_markdown / feedback_unparsed），LLM 原样取用。

编号：D<n> 绑定问题、跨轮终身不变（人第 1 轮作答的 D3，第 2 轮还是同一个问题）。
影响（high/medium/low）只决定**展示顺序**：清单按影响降序渲染，编号不动。
所有决策项都必须有 recommendation_key——人没答的项按推荐执行，缺推荐=必须报错。

答复语法（人在 amend feedback 里写）：
  D1=A            选 A 选项
  D2=自定:文字     自定义答案（文字可含逗号/分号/换行，不截断）
  D3=暂缓          显式推迟（deferred：不阻塞、不触发下一轮）
                  （刻意不叫「待查」——「待查」常被用作一个选项 label，
                    与"这项我不答"语义冲突）
  未提到的项        自动取 recommended option（decided_by=recommended）

轮次闸：平台不限制"人反复 reject/amend"的次数（审批循环不消耗 max_attempts
且没有上限），所以"最多两轮"必须由本脚本兜底。轮次按**新答复**计数：feedback
非空且与上一轮不同才进位；同一份答复重跑、或无反馈的重跑（平台 retry、无
reason 的 reject）不消耗预算。超限（第 max_rounds+1 轮）exit 1 且不写任何文件。

退出码：0=完成；1=decisions 形状非法或轮次已耗尽（未写任何文件，修正后重跑）；
2=脚本故障（fail-closed）。
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

DEFER_TEXT = '暂缓：未定论，下游按推荐实现并保留风险登记'
# defer 的答复关键字。刻意不用「待查」——真实使用中「待查」常被用作一个**选项**
# （人答 "D1=待查" 时意思是"我选那个待查选项"），与"这项我不答"语义冲突。
# 这里用「暂缓」，与选项 label 无歧义。
DEFER_KEYWORD = '暂缓'
MAX_ROUNDS = 2
# impact 三档；清单按此降序**展示**（编号跨轮稳定，不受排序影响）。
IMPACT_LEVELS = ('high', 'medium', 'low')
IMPACT_ORDER = {'high': 0, 'medium': 1, 'low': 2}
OUT_KEYS = ('id', 'key', 'question', 'options', 'recommendation_key',
            'recommendation_reason', 'evidence', 'impact', 'chosen_key',
            'custom_text', 'decided_by', 'note')
ANS = re.compile(r'(?<![A-Za-z0-9])D(\d+)\s*[=＝]', re.I)
SEPS = ' \t\r\n,;，；'


def load_state(path):
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    items = data.get('items') if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError('decisions.json 结构非法（缺 items 数组）')
    return items


def validate(decisions):
    errs = []
    seen = set()
    for i, d in enumerate(decisions or []):
        p = 'decisions[{}]'.format(i)
        if not isinstance(d, dict):
            errs.append('{} 必须是对象'.format(p))
            continue
        key = d.get('key')
        if not isinstance(key, str) or not key.strip():
            errs.append('{} key 不得为空'.format(p))
        elif key in seen:
            errs.append('{} key 重复：{}'.format(p, key))
        else:
            seen.add(key)
        if not isinstance(d.get('question'), str) or not d['question'].strip():
            errs.append('{} question 不得为空'.format(p))
        opts = d.get('options')
        okeys = []
        if not isinstance(opts, list) or len(opts) < 2:
            errs.append('{} options 至少 2 项'.format(p))
        else:
            for j, o in enumerate(opts):
                if not isinstance(o, dict) or any(
                        not isinstance(o.get(k), str) or not o[k].strip()
                        for k in ('key', 'label', 'impact')):
                    errs.append('{} options[{}] 须含非空 key/label/impact'.format(p, j))
                else:
                    okeys.append(o['key'])
            if len(okeys) != len(set(okeys)):
                errs.append('{} options key 重复'.format(p))
        rk = d.get('recommendation_key')
        if rk is not None and rk not in okeys:
            errs.append('{} recommendation_key={} 不在 options 内'.format(p, rk))
        elif rk is None:
            # 推荐项是硬要求：没有推荐项的项，人不答时会静默变成"暂缓"，
            # 而暂缓是"人不答"的意思，不是"没有推荐"。宁缺毋滥也要标出来。
            errs.append('{} 缺 recommendation_key —— 每个决策项都必须有推荐项'
                        '（人没答时按推荐执行）'.format(p))
        ev = d.get('evidence')
        if not isinstance(ev, list) or not ev:
            errs.append('{} evidence 不得为空（每项 {{claim,verified,ref}}）'.format(p))
        else:
            for j, e in enumerate(ev):
                if not isinstance(e, dict) or not isinstance(e.get('claim'), str) \
                        or not isinstance(e.get('verified'), bool) \
                        or not isinstance(e.get('ref'), str):
                    errs.append('{} evidence[{}] 须为 {{claim:str, verified:bool, ref:str}}'.format(p, j))
                elif e['verified'] and not e['ref'].strip():
                    errs.append('{} evidence[{}] verified=true 必须给 ref'.format(p, j))
        im = d.get('impact')
        if im not in IMPACT_LEVELS:
            errs.append('{} impact 必须是 {} 之一'.format(p, '/'.join(IMPACT_LEVELS)))
    return errs


def parse_feedback(text):
    """返回 ([(id, 原始片段)], [无法归属的片段])。片段 = 两个 Dn= 之间的原文，
    因此"自定:"后的文字可含逗号/分号/换行。"""
    text = text or ''
    ms = list(ANS.finditer(text))
    answers, stray = [], []
    pre = text[:ms[0].start()] if ms else text
    if pre.strip(SEPS):
        stray.append(pre.strip(SEPS))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        answers.append(('D' + m.group(1), text[m.end():end].strip().rstrip(SEPS).strip()))
    return answers, stray


def apply_answers(items, answers):
    by_id = {it['id']: it for it in items}
    stray = []
    for iid, val in answers:
        it = by_id.get(iid)
        if it is None:
            stray.append('{}={}：无此编号'.format(iid, val))
            continue
        m = re.match(r'^自定\s*[:：]\s*(.+)$', val, re.S)
        if m and m.group(1).strip():
            it['chosen_key'], it['custom_text'], it['decided_by'] = 'custom', m.group(1).strip(), 'human'
        elif val == DEFER_KEYWORD:
            it['chosen_key'], it['decided_by'] = 'defer', 'human'
        else:
            keymap = {o['key'].lower(): o['key'] for o in it['options']}
            if val.lower() in keymap:
                it['chosen_key'], it['decided_by'] = keymap[val.lower()], 'human'
            else:
                it['note'] = '无法解析的答复片段：{}（保持原选择）'.format(val)
    return stray


def settle_defaults(it):
    if it.get('decided_by') == 'human':
        return
    rk = it.get('recommendation_key')
    if rk:
        it['chosen_key'], it['decided_by'] = rk, 'recommended'
    else:
        it['chosen_key'], it['decided_by'] = 'defer', 'recommended'


def binding(it):
    ck = it['chosen_key']
    if ck == 'custom':
        return '自定义', it.get('custom_text') or ''
    if ck == 'defer':
        return '暂缓', DEFER_TEXT
    for o in it['options']:
        if o['key'] == ck:
            return o['label'], '{}（{}）'.format(o['label'], o['impact'])
    return ck, ck


def cell(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')


def render_md(items, stray, round_no):
    out = ['# 待你决策清单（第 {} 轮）'.format(round_no), '',
           '怎样回复：点 **amend**，feedback 写 `D1=A, D2=自定:..., D3=暂缓`。',
           '没提到的项**自动按推荐**执行；`暂缓` 表示这项先不定（不阻塞下游，留待后续）。',
           '选项里的 ⭐ 是本轮推荐。证据标 ⚠️未核实 的，表示推断而非亲自读到的原文。',
           '清单按影响从高到低排列；编号 D<n> 跨轮稳定（同一个 D<n> 永远是同一个问题）。', '']
    if stray:
        out += ['**未能解析的答复片段（未生效）**：'] + ['- ' + s for s in stray] + ['']
    if not items:
        out.append('本轮无待决项——全部歧义已由证据自解（见 assumptions）。')
        return '\n'.join(out) + '\n'
    # 按影响降序**展示**（编号不变——编号跨轮必须稳定，否则人的答复会错位）。
    ordered = sorted(items, key=lambda it: IMPACT_ORDER.get(
        str(it.get('impact') or 'low').lower(), 3))
    n_high = sum(1 for it in ordered if str(it.get('impact') or '').lower() == 'high')
    if n_high:
        out += ['> 共 {} 项，其中 **{} 项为 high 影响**，建议优先处理这 {} 项；'
                '其余项已全列在下面，可一并答复，也可放着按推荐执行。'.format(
                    len(ordered), n_high, n_high), '']
    for it in ordered:
        title = it['question'].strip().splitlines()[0][:40] if it['question'].strip() else it['id']
        impact = str(it.get('impact') or '').lower()
        badge = {'high': '🔴 high', 'medium': '🟡 medium', 'low': '⚪ low'}.get(impact, impact)
        out += ['## {}　{}　〔{}〕'.format(it['id'], title, badge),
                '**问题**　' + it['question'],
                '**影响**　' + (it.get('impact') or '（未填写）'),
                '**证据**　' + (' / '.join(
                    ('✅已核实：{}（{}）'.format(e['claim'], e['ref']) if e.get('verified')
                     else '⚠️未核实：{}'.format(e['claim'])) for e in it['evidence']) or '无'),
                '**选项**　', '| key | 做法 | 影响 | 推荐 |', '|---|---|---|---|']
        rec = it.get('recommendation_key')
        for o in it['options']:
            star = '⭐' if o['key'] == rec else ''
            out.append('| {} | {} | {} | {} |'.format(
                cell(o['key']), cell(o['label']), cell(o['impact']), star))
        label, detail = binding(it)
        out += ['**推荐理由**　{}'.format(it['recommendation_reason'])
                if it.get('recommendation_reason') else '**推荐理由**　无',
                '**当前采用**　{}（{}）{}'.format(
                    label, '人已答复' if it['decided_by'] == 'human' else '暂按推荐',
                    '　— ' + detail if detail and detail != label else ''), '']
        if it.get('note'):
            out += ['**备注**　' + it['note'], '']
    return '\n'.join(out) + '\n'


def atomic_write(path, text):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


def run(ctx):
    spec_dir = ctx.get('spec_dir')
    if not isinstance(spec_dir, str) or not spec_dir:
        raise ValueError('context 缺 spec_dir')
    # 决策清单与轮次计数是**本次 run 的状态**，不是仓库内容——落在节点自己的工作目录，
    # 不落在 spec_dir（仓内）。spec_dir 只用于回填三件套时的定位。
    decisions_dir = ctx.get('decisions_dir')
    if decisions_dir is None:
        decisions_dir = spec_dir          # 兼容旧调用；新调用必须显式给节点目录
    if not isinstance(decisions_dir, str) or not decisions_dir:
        raise ValueError('context 缺 decisions_dir')
    ddir = Path(decisions_dir).resolve()
    state_path = ddir / 'decisions.json'
    items = load_state(state_path)
    by_key = {it.get('key'): it for it in items}

    mr = ctx.get('max_rounds')
    mr = mr if isinstance(mr, int) and not isinstance(mr, bool) and 1 <= mr <= 5 else None
    # 轮次闸：状态文件已记到第 N 轮 → 本次是第 N+1 轮；超过 max_rounds 就拒。
    # 平台不限制"人反复 amend"的次数（审批循环不消耗 max_attempts 且无上限），
    # 所以这个闸是"最多两轮"的唯一强制点。
    prev_round = 0
    prev_max = None
    prev_fingerprint = None
    if state_path.is_file():
        try:
            st = json.loads(state_path.read_text(encoding='utf-8'))
            prev_round = int(st.get('round') or 0)
            prev_max = st.get('max_rounds')
            prev_fingerprint = st.get('feedback_fingerprint')
            if not isinstance(prev_max, int) or isinstance(prev_max, bool):
                prev_max = None
        except Exception:
            prev_round, prev_max, prev_fingerprint = 0, None, None
    # 轮次预算一经设定即随状态文件继承：后续轮次不传 max_rounds 时沿用上一轮的值，
    # 传入时只能收紧不能放宽——否则第二轮漏传参数就会绕过预算。
    if mr is None:
        mr = prev_max if prev_max is not None else MAX_ROUNDS
    elif prev_max is not None:
        mr = min(mr, prev_max)

    # 轮次按**人的新答复**计数，不按脚本执行次数计数。
    # 进位条件：feedback 非空，且与上一轮记录的指纹不同。同一份答复重跑
    # （agent 修形状后重试）、无反馈的重跑（平台 retry、无 reason 的 reject）
    # 都不消耗预算——否则人第一次 amend 就撞上限。首轮（无状态）恒为第 1 轮。
    feedback = ctx.get('approval_feedback') or ''
    fingerprint = hashlib.sha256(feedback.strip().encode('utf-8')).hexdigest()
    if prev_round == 0:
        round_no = 1
    elif feedback.strip() and (prev_fingerprint is None or fingerprint != prev_fingerprint):
        round_no = prev_round + 1        # 新答复 → 进位
    else:
        round_no = prev_round            # 同一份/空答复 → 不进位
    if round_no > mr:
        return None, ['澄清轮次已耗尽：本次是第 {} 轮，上限 {} 轮。'
                      '不再开新问题、不再接受新答复——请人工决定继续还是终止 run。'
                      .format(round_no, mr)]

    errs = validate(ctx.get('decisions'))
    if errs:
        return None, errs

    maxn = max([int(m.group(1)) for it in items
                for m in [re.match(r'^D(\d+)$', str(it.get('id')))] if m] or [0])
    for d in ctx.get('decisions') or []:
        if d['key'] in by_key:
            continue                       # 已有 key 不改号，沿用旧选择
        maxn += 1
        d.update({'id': 'D{}'.format(maxn), 'chosen_key': None, 'custom_text': '',
                  'decided_by': None, 'note': ''})
        items.append(d)
        by_key[d['key']] = d

    # ⚠️ 编号**跨轮稳定**：D<n> 终身绑定同一个问题。人第 1 轮看到 D3 并作答，
    # 第 2 轮 D3 仍必须是同一个问题——重排会让答复错位到别的问题上。
    # "按影响排序"只体现在**展示顺序**（render_md 排序），不动编号。
    for it in items:
        it['note'] = ''
        it.setdefault('custom_text', '')
    answers, stray = parse_feedback(ctx.get('approval_feedback'))
    for it in items:                       # 先给默认，再让人的答复覆盖
        settle_defaults(it)
    stray += apply_answers(items, answers)

    answered = sum(1 for it in items if it['decided_by'] == 'human' and it['chosen_key'] != 'defer')
    deferred = sum(1 for it in items if it['chosen_key'] == 'defer')
    pending = sum(1 for it in items if it['decided_by'] == 'recommended')
    # top_n = 建议人优先处理的项数（影响为 high 的项）。
    # 超出 top_n 的项照样全列、照样可答，只是排在后面并标注优先级。
    top_n = sum(1 for it in items if str(it.get('impact') or '').lower() == 'high')

    ddir.mkdir(parents=True, exist_ok=True)
    # 不进位的重跑沿用上一轮记录的指纹——若被空反馈覆盖，人再发同一份答复
    # 会被误判成"新答复"而多计一轮。
    stored_fp = fingerprint if (round_no > prev_round or prev_fingerprint is None) \
        else prev_fingerprint
    atomic_write(state_path, json.dumps({'items': items, 'round': round_no,
                                         'max_rounds': mr,
                                         'feedback_fingerprint': stored_fp},
                                        ensure_ascii=False, indent=2))
    sheet = ddir / 'decisions.md'
    atomic_write(sheet, render_md(items, stray, round_no))
    report = {'decision_sheet_path': str(sheet),
              'spec_dir': str(Path(spec_dir).resolve()),
              'decisions_dir': str(ddir),
              'items': [{k: it.get(k) for k in OUT_KEYS} for it in items],
              'decisions_count': len(items),
              'top_n': top_n,
              'pending_count': pending, 'answered_count': answered,
              'deferred_count': deferred, 'round': round_no,
              'max_rounds': mr, 'round_exhausted': round_no >= mr,
              # 人只能在审批面板里看到节点 output，看不到文件——所以 output 必须自足。
              # sheet_markdown 是给人读的完整清单原文，直接进 output。
              'sheet_markdown': render_md(items, stray, round_no),
              'feedback_unparsed': stray}
    return report, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--context', required=True)
    args = ap.parse_args()
    ctx_path = Path(args.context)
    report, errs = run(json.loads(ctx_path.read_text(encoding='utf-8')))
    if errs:
        print('decision_check.py 拒绝执行（未写任何文件）：', file=sys.stderr)
        for e in errs:
            print('  - ' + e, file=sys.stderr)
        return 1
    (ctx_path.parent / 'decision_output.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('items={} pending={} answered={} deferred={} round={}/{}'.format(
        len(report['items']), report['pending_count'], report['answered_count'],
        report['deferred_count'], report['round'], report['max_rounds']))
    for s in report['feedback_unparsed']:
        print('  未能解析的答复片段：' + s)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print('decision_check.py: 脚本故障（fail-closed，exit 2）: {!r}'.format(exc), file=sys.stderr)
        sys.exit(2)

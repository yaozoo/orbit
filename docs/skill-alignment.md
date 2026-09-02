# 技能对齐：o-spec / o-build / o-review 与 OpenSpec、superpowers

本文件把三个 self-contained 阶段与 [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec)（环境里的 `openspec-*` 组）和 [obra/superpowers](https://github.com/obra/superpowers)（环境里的 `superpowers-*` 组）的技能做对齐。

> 概念参照，**非运行时调用**。当前 self-contained 设计下，三个 SKILL.md 的 body 把相关方法论内联进去了，并不实际 invoke 这些 sub-skill。

## 按阶段对齐

### o-spec（需求分析 → OpenSpec trio）

| 我们做的事 | 对齐的技能 | 对齐度 |
|---|---|---|
| 读需求文档、判类型、显式化 assumptions/confidence | `superpowers:brainstorming`（探索 intent/需求/设计） | 紧 |
| 扫代码库、把每条需求映射到具体文件（design.md req→file map） | `openspec:explore`（载入现有 specs/代码上下文）、`openspec:context-loading` | 中（我们更重"落点"） |
| 写 proposal.md + design.md + tasks.md | `openspec:propose` / `openspec:new-change` / `openspec:proposal-creation` | 紧（输出形态同源） |
| coverage 自检（回读原文档逐条核对落点） | — 无直接对应 | 我们自己的硬约束 |

### o-build（实现 → per-task 验证+实现+回滚）

| 我们做的事 | 对齐的技能 | 对齐度 |
|---|---|---|
| 按 tasks.md 逐任务执行 | `superpowers:executing-plans` | 紧 |
| 有测试框架时写测试→实现（TDD） | `superpowers:tdd` | 紧（但仅限有 harness） |
| 任务失败→回滚→换思路重试 | `superpowers:debugging` | 中（我们多一层 git 回滚） |
| 每任务验证 | `superpowers:verification` | 紧 |
| 无 harness 时用 bash 断言替代 | — 无对应 | 我们自己的降级 |
| 把 spec delta 落到代码 | `openspec:apply-change` / `openspec:implementation` | 紧（OpenSpec 的实现步） |
| 中断后续跑 | `openspec:continue-change` | 中 |

### o-review（审计 → 自动修 → verdict）

| 我们做的事 | 对齐的技能 | 对齐度 |
|---|---|---|
| code↔spec 一致性审计 | `openspec:verify-change` | 紧（OpenSpec 的 verify 步） |
| 代码质量审计 | `superpowers:code-review` | 紧 |
| 跑测试/断言确认 | `superpowers:verification` | 紧 |
| 自动修 minor 问题 | — 无对应（code-review 只报告不修） | 我们自己的扩展 |
| 归档 change（我们当前省略） | `openspec:archive-change` / `openspec:archiving` | 缺——若要真接 OpenSpec，这步该补回 o-review 末尾 |

## 工作流整体对应

两条生态的 lifecycle 几乎同构，都落在 o-spec → o-build → o-review 三段上：

```
superpowers:  brainstorming → writing-plans → executing-plans(+tdd/debug) → code-review(+verification)
openspec:     propose/new   → apply/impl    → verify                         → archive
我们的:        o-spec        → o-build       → o-review
```

## 四个不对齐点（我们的原创 / 缺口）

1. **o-spec 的 coverage 自检** —— 两个生态都没有"写完 spec 后回读原文档逐条核对覆盖率"这一步。我们为压偏差专门加的。
2. **o-build 的 no-harness bash 断言** —— `superpowers:tdd` 假设有测试框架；静态产物（HTML/config）无框架时没有对应技能可调，是自创降级。
3. **o-review 的 auto-fix** —— `superpowers:code-review` 是只读报告；我们的"自动修 minor"超出了它，更接近再跑一次 build。
4. **o-review 缺 archive** —— OpenSpec workflow 的终点是 `openspec:archive-change`，我们当前省了。如果以后要真接 OpenSpec，这一步补在 o-review 的 commit+push 之前最自然。

## 若以后从"参照"走向"真集成"

最高价值的真接 hook（每个都可选、都带优雅降级——`command -v openspec && … || <内联 fallback>`，绝不要旧版那套 Skill-Resolution-Order 探测）：

- `o-review` 的 spec 一致性校验 → 跑 `openspec verify-change`，用机器硬契约替代 LLM 判一致性。
- `o-review` 的终步 → `openspec archive-change`，闭合 change。
- `o-spec` 的合成 → `openspec propose` / `new-change`，拿到真 spec delta（`specs/`）而非手写 proposal.md。

其余（brainstorming、executing-plans、tdd、code-review、verification）保持内联——调这些 superpowers sub-skill 增加解析依赖，对"每条 feature 跑一次"的自动流水线收益不大。

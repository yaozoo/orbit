# Stage Transitions — 阶段转换拦截规则表

## 合法子 Workflow/Skill 映射

> **跨工具说明**：以下 "子 Skill" 在不同 AI 工具中的实现方式不同。在 Codex 中可直接加载 skill 文件；在其他工具中，参照 SKILL.md "Tool Compatibility" 部分的 inline fallback 指令执行。

每个 Stage 允许加载的子 skill 列表：

| Stage | 合法子 Workflow/Skill |
|-------|-------------|
| 0 | 无（纯 Orbit 逻辑） |
| 1 | `brainstorming` |
| 2 | 无（Orbit 内部逻辑：条件触发方案分析 → 写制品 → 审阅 Gate。仅用 `openspec status` CLI 校验。详见 SKILL.md Stage 2 Step 3） |
| 3 | `writing-plans` |
| 4 | `subagent-driven-development`, `test-driven-development`, `systematic-debugging` |
| 5 | `verification-before-completion`, `openspec-verify-change`, `openspec-archive-change`, `finishing-a-development-branch` |

## 终端跳转拦截表

子 skill 的默认终端跳转 vs Orbit 的拦截后动作：

| 子 Workflow/Skill | 默认终端跳转 | Orbit 拦截后 |
|----------|-------------|-------------|
| `brainstorming` | → `writing-plans` | Stage 2（生成 OpenSpec 制品） |
| `writing-plans` | → `subagent-driven-development` | Stage 3→4 桥接（tasks.md）→ Stage 4 |
| `subagent-driven-development` | → `finishing-a-development-branch` | Stage 5（verify → archive → finishing） |

## 自检门禁表

Pre-Action Guard 在加载以下 skill 前执行：

| 即将加载的 Skill | 期望 `.orbit-state.stage` | 不匹配时动作 |
|-----------------|--------------------------|-------------|
| `writing-plans` | 3 | 输出 `[ORBIT_SELF_CHECK_FAILED]`，跳转到正确阶段 |
| `subagent-driven-development` | 4 | 输出 `[ORBIT_SELF_CHECK_FAILED]`，跳转到正确阶段 |
| `finishing-a-development-branch` | 5 | 输出 `[ORBIT_SELF_CHECK_FAILED]`，跳转到正确阶段 |

## 变更类型 → 阶段路由

| change_type | 阶段路由 | 跳过 |
|-------------|---------|------|
| `feature` | 0 → 1 → 2 → 3 → 4 → 5 | 无 |
| `bugfix` | 0 → 2 → 3 → 4 → 5 | Stage 1 |
| `docs` | 0 → 2 → 5 | Stage 1, 3, 4（config 类变更归入 docs 路径）|

## 阶段内状态变更

| 变更 | 触发条件 | 操作 |
|------|---------|------|
| `commit_mode: review → auto` | Stage 4 用户输入 `4` | 更新 `.orbit-state.commit_mode`，当前及剩余 Task 自动提交，不再询问 |
| `substage: bridging → approach_analysis` | Stage 2 Step 3 自评估触发 | 写入 `.orbit-state.substage`，展示方案选项，等待用户选择 |
| `substage: approach_analysis → bridging` | Stage 2 Step 3 用户选定方案 | 写入 `.orbit-state.selected_approach`，继续写制品 |

## 异常回退

| 场景 | 触发条件 | 目标阶段 | 状态清理 |
|------|---------|---------|---------|
| Spec Gap | Stage 4 发现 spec 缺陷 | Stage 2 (`substage: spec_gap`) | 清空 current_task, total_tasks, task_history, hotfix_queue, plan_doc |
| 用户覆盖 | 用户要求跳过/重跑某阶段 | 用户指定的阶段 | 按需清理对应阶段的状态字段 |
| 重新讨论方案 | Stage 2 Gate 用户输入 `3` | Stage 2 (`substage: approach_analysis`) | 删除已生成的制品，保留 `.orbit-state.selected_approach` 供参考 |

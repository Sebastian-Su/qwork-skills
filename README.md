# qwork-skills

QWork 项目级 Skill 的独立私有仓库。

## 包含的 Skill

- `qwork-test-e2e`：QWork Electron 客户端 E2E 执行与证据报告。
- `qwork-work-report`：基于 QWork 及关联项目证据生成日报或周报。

## 本地接入

当前 QWork 工作区通过相对软连接接入：

```text
qwork/qwork/.agents/skills/<skill-name>
  -> ../../../../Skills/qwork-skills/<skill-name>
```

`.codex/skills` 与 `.claude/skills` 再分别链接到 `.agents/skills`，因此三个 Agent 入口共用同一份 Skill 实体。

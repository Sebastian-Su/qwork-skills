# QWork 私有 Dataset 存储契约

- 唯一实体根：私人仓库 `qwork-skills/qwork-test-dataset/`；`skill://qwork-test-dataset/` 是稳定逻辑地址。
- QWork 团队仓库只允许保留未追踪、被忽略的相对软链接 `.agents/skills/qwork-test-dataset -> ../../../../Skills/qwork-skills/qwork-test-dataset`；`.codex/skills` 与 `.claude/skills` 再相对链接到 `.agents/skills`。禁止在团队仓库保存实体副本或把任一入口加入 Git 历史。
- 私人仓库管理 Skill 的 `SKILL.md`、`agents/`、`references/`、`scripts/`，以及 `data/` 下由 Skill 自身 `.gitignore` 显式放行的版本化测试资产（当前为 `data/{benchmarks,datasets,e2e,evidence,reference-runs,sources}`）；PNG/trace 等二进制走 Git LFS。`data/` 下未被放行的子树（运行产物、构建目录、缓存、未晋升报告）必须保持被忽略且未追踪，并写到仓库外的 `QWORK-E2E-TEMPORARY-DATA-DO-NOT-COMMIT/<run-id>/`。禁止在团队仓库保存实体副本或把任一入口加入 Git 历史。
- 外部来源先进入 `data/sources/<source>/<snapshot-id>/`，派生资产只能引用快照。
- 禁止保存密码、Token、Cookie、授权头、Keychain 数据或未脱敏身份信息。
- `~/.workbuddy/` 只读扫描；凭据、缓存正文和用户会话内容默认仅保存 schema、文件元数据与内容哈希。
- WorkBuddy UI 截图与几何测量进入 `data/benchmarks/ui-visual/`，当前 QWork 截图只能进入 `data/evidence/`，不得反向批准为基线。
- 所有写入前后运行 `scripts/validate_private_storage.py`：团队仓库入口必须是被忽略、未追踪、状态干净的相对软链接；私人仓库 `data/` 的每个子树必须与 Skill `.gitignore` 的分类一致——被忽略的子树必须未追踪，未被忽略的子树必须已追踪且不含 `runs/build/app/out/node_modules/.cache/__pycache__` 等执行产物；且全部 `data/` 子树的 `git status` 必须为空，即冻结资产不得带未提交漂移。任一条件不满足即失败。

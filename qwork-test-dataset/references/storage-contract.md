# QWork 私有 Dataset 存储契约

- 唯一实体根：私人仓库 `qwork-skills/qwork-test-dataset/`；`skill://qwork-test-dataset/` 是稳定逻辑地址。
- QWork 团队仓库只允许保留未追踪、被忽略的相对软链接 `.agents/skills/qwork-test-dataset -> ../../../../Skills/qwork-skills/qwork-test-dataset`；`.codex/skills` 与 `.claude/skills` 再相对链接到 `.agents/skills`。禁止在团队仓库保存实体副本或把任一入口加入 Git 历史。
- 专用 `qwork-skills` 仓库可以管理 Skill 的 `SKILL.md`、`agents/`、`references/`、`scripts/`，以及经脱敏、可复现且未来 E2E 会直接消费的 `data/{benchmarks,datasets,e2e,evidence,reference-runs,sources}`。这些版本化目录中的每个文件都必须已追踪且工作树干净，PNG、JPG、JPEG、WebP、ZIP 必须命中仓库 Git LFS 属性。
- `data/` 下除上述白名单外不得存在任何目录或文件，即使已被 `.gitignore` 排除也不允许。运行过程、构建目录、缓存、重试和未晋升报告必须写到 Git 工作树之外的临时 Evidence 根，晋升前不得进入专用仓库或团队仓库。
- 外部来源先进入 `data/sources/<source>/<snapshot-id>/`，派生资产只能引用快照。
- 禁止保存密码、Token、Cookie、授权头、Keychain 数据或未脱敏身份信息。
- `~/.workbuddy/` 只读扫描；凭据、缓存正文和用户会话内容默认仅保存 schema、文件元数据与内容哈希。
- WorkBuddy UI 截图与几何测量进入 `data/benchmarks/ui-visual/`，当前 QWork 截图只能进入 `data/evidence/`，不得反向批准为基线。
- 所有写入前后运行 `scripts/validate_private_storage.py`：团队仓库入口必须被忽略且未追踪；专用仓库中的版本化白名单资产必须全部已追踪、无未提交修改，并按扩展名命中 Git LFS；`data/` 下不得出现运行态子树，任一条件不满足即失败。

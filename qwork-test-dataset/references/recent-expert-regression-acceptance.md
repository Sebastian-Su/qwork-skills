# 近期专家与专家团验收标准（2026-09-08）

范围是本轮已批准的资源恢复、包描述只读兼容、精选配置、召唤与成员重试修复。QWork 提供桌面交互和包管理；ZiqDo 提供运行协议；本文件和 Case 由 qwork-skills 维护。本轮没有修改服务端、转换器或重新发布专家包。

冻结 QWork 基线 `57fc92fbfced8f63a6e9fe510a7c08d39a09d7db`，候选提交 `f22d6511c2187b77319ea0d8f989dbd0c0a07cda`。规范以已批准的用户决策及该版本专家包布局文档为准；QWork 测试与截图是执行证据，不替代 WorkBuddy 视觉 Oracle。

| 验收项 | 通过条件 | Case 与当前状态 |
| --- | --- | --- |
| 失效资源引用 | 既有受管理专家目录缺失时清理无效引用，应用仍能进入可操作窗口；不删用户工作区和其他有效资源。 | [QW-E2E-RESOURCE-RECOVERY-SPEC-1D3D6E57](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-RESOURCE-RECOVERY-SPEC-1D3D6E57.json)：partial / pending |
| 安装包精选配置 | 存在合法配置文件时按其展示；不需要请求新的服务端精选配置。 | [QW-E2E-FEATURED-SCENES-PACKAGE-CONFIG-SPEC-B8B443AC](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-FEATURED-SCENES-PACKAGE-CONFIG-SPEC-B8B443AC.json)：partial / pending |
| 精选配置缺失 | 文件不存在时使用内置十组场景，页面可用。 | [QW-E2E-FEATURED-SCENES-PACKAGE-CONFIG-SPEC-924338A1](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-FEATURED-SCENES-PACKAGE-CONFIG-SPEC-924338A1.json)：partial / pending |
| 新包描述入口 | 新包使用 .qwork-plugin/plugin.json；读取不生成旧文件。 | [QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-C996D43D](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-C996D43D.json)：partial / pending |
| 旧包只读兼容 | 新清单缺失时回退 ziqdo-plugin.json；保留字节、旧副本和 .claude-plugin 运行入口，不创建新别名。 | [QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-91077C3A](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-91077C3A.json)：partial / pending |
| 描述冲突 | 同内容优先新清单；新旧内容冲突拒绝该包，禁止改写成一致。 | [QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-38022C31](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-38022C31.json)：partial / pending |
| manifest 边界 | manifest.json 不独立启用；与旧描述冲突时拒绝；没有旧描述时不把它当第三套入口。 | [QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-4F460380](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-4F460380.json)：partial / pending |
| 新布局真实根路径 | 新布局从稳定包根创建会话，传给运行时的目录必须是包根。 | [QW-E2E-EXPERTS-SPEC-2AEC2FD1](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-EXPERTS-SPEC-2AEC2FD1.json)：partial / pending |
| 旧布局真实根路径 | 旧布局同样从包根创建会话，不通过改写下载制品实现兼容。 | [QW-E2E-EXPERTS-SPEC-F9A5B6A2](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-EXPERTS-SPEC-F9A5B6A2.json)：partial / pending |
| 旧专家团展示字段 | 旧专家团缺少可选展示字段时仍可创建会话，不把展示完整度当作执行条件。 | [QW-E2E-SOFTWARE-COMPANY-SPEC-AFE79D2A](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-SOFTWARE-COMPANY-SPEC-AFE79D2A.json)：partial / pending |
| 运行身份与成员流 | 保持软件开发团队负责人身份，成员必须产生独立真实协议事件；夹具协议通过不代表真实模型完成。 | [QW-E2E-SOFTWARE-COMPANY-SPEC-D04CB2B8](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-SOFTWARE-COMPANY-SPEC-D04CB2B8.json)：partial / pending |
| 成员登记状态 | 登记成员不等于已经运行，只有收到独立执行事件后才更新运行状态。 | [QW-E2E-EXPERT-TEAM-SPEC-20D48D28](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-EXPERT-TEAM-SPEC-20D48D28.json)：partial / pending |
| 成员指标 | 不展示“工具调用未上报”和无法证明的模型占位信息；保留已上报用量与独立输出。 | [QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-C16DF454](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-PRIVATE-FUNCTIONAL-CONTRACTS-SPEC-C16DF454.json)：partial / pending |
| 指定成员重试 | 成功提交后回到负责人并保留旧失败记录可查看；异常有可见反馈。 | [QW-E2E-EXPERT-TEAM-SPEC-7BA13688](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-EXPERT-TEAM-SPEC-7BA13688.json)：partial / pending |
| 跨页面重试状态 | 等待期间切走再返回仍禁用按钮；离开期间失败后返回仍可见错误，不重复发请求。 | [QW-E2E-EXPERT-TEAM-SPEC-66A24E9A](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-EXPERT-TEAM-SPEC-66A24E9A.json)：partial / pending |

召唤与授权弹窗还需同时满足：远端说明读取失败不阻断已有有效专家召唤；授权对话框位于专家详情上层且取得焦点，拒绝或 Escape 后详情仍可关闭。相关共享 Case 如下；每条均需核对实际测试体，不以标题替代因果断言。

- [QW-E2E-EXPERT-CLOUD-CATALOG-SPEC-9FCD78D0](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-EXPERT-CLOUD-CATALOG-SPEC-9FCD78D0.json)：keeps paid media approval above expert details and restores expert interaction
- [QW-E2E-EXPERT-CLOUD-CATALOG-SPEC-E30FA026](skill://qwork-test-dataset/data/datasets/cases/QW-E2E-EXPERT-CLOUD-CATALOG-SPEC-E30FA026.json)：combines bundled and paged cloud experts, then installs and updates without text preview

## 验证范围与待补验

这些条目已进入来源、需求、Case 与路由索引，但本次没有重新执行产品 E2E，也没有晋升上次临时目录的结果为 reference run。旧通过证据按当前 revision、spec 与 Oracle 哈希重新判定；partial / pending 不计为产品通过。

仍需单独验收：下载失败后的再次使用、单包损坏不阻断启动、错误提示关闭与 SLS 接收、安装包内资源及新上传产物约束、Windows/Linux 安装与实际运行、专家和专家团各三次真实任务。成员完整消息/工具时间线、旧团队名称及像素对齐仍以批准的 WorkBuddy 基线为准，不因本次功能修复而标为完成。

原生安装验收和隔离 Case 必须分别记录。旧包不得修改以凑齐通过；失败截图也不能成为新 Golden。

来源与追溯：
- [完整来源与覆盖索引](skill://qwork-test-dataset/data/datasets/source-acceptance.json)
- [新旧包兼容 Case 源码](skill://qwork-test-dataset/data/e2e/expert-descriptor-compatibility.spec.ts)
- [成员独立流 Case 源码](skill://qwork-test-dataset/data/e2e/team-event-causality.spec.ts)
- [目标 WorkBuddy 版本](skill://qwork-test-dataset/references/workbuddy-target-baseline.yaml)

# User Instruction Memory

This file records user instructions, preferences, and teachings for reference in future interactions.

## Format

### User Instruction Entry
User instruction entries should follow this format:

[User Instruction Summary]
- Date: [YYYY-MM-DD]
- Context: [Mentioned scenario or time]
- Instructions:
  - [Content of user teaching or instruction, described line by line]

### Project Knowledge Entry
Entries discovered by the Agent during task execution should follow this format:

[Project Knowledge Summary]
- Date: [YYYY-MM-DD]
- Context: Discovered by Agent while performing [specific task description]
- Category: [Operations & Deployment|Build Methods|Testing Methods|Troubleshooting & Debugging|Workflow & Collaboration|Environment Configuration]
- Instructions:
  - [Specific knowledge points, described line by line]

## Deduplication Strategy
- Before adding a new entry, check for similar or identical instructions.
- If a duplicate is found, skip the new entry or merge it with the existing one.
- When merging, update the context or date information.
- This helps avoid redundant entries and keeps the memory file tidy.

## Entries

[Project Knowledge Summary]
- Date: 2026-10-13
- Context: Discovered by Agent while deploying the netbox-nutanix plugin for testing
- Category: Environment Configuration
- Instructions:
  - 本环境不支持 background terminal 的 cgroup 资源限制。带 `memory_percent`/`cpu_percent` 的 `background_terminal_create` 会以 "requested cgroup limits are unsupported: ... read-only file system" 失败。创建后台终端时应省略这两类限制，仅设置 `timeout`。
  - 系统 Python 为 3.11.2（Debian 12），默认无 `ensurepip`；创建 venv 前需 `apt-get install -y python3.11-venv`。
  - GitHub `github.com` 直连不可用，但 `codeload.github.com` 可下载源码 tarball（`https://codeload.github.com/<org>/<repo>/tar.gz/refs/tags/<tag>`）。pypi.org 可直连。

[Project Knowledge Summary]
- Date: 2026-10-13
- Context: Discovered by Agent while deploying the netbox-nutanix plugin for testing
- Category: Operations & Deployment
- Instructions:
  - 测试部署基线：NetBox 4.4.0（源码 `/opt/netbox-4.4.0`）+ PostgreSQL 15 + Redis 7 + venv `/opt/netboxenv`。
  - NetBox 4.5.0 起要求 Python 3.12+，本机为 3.11，因此测试环境选用 NetBox 4.4.0（要求 Python 3.10+）。
  - 部署步骤：apt 安装 `postgresql redis-server build-essential python3-dev libpq-dev libffi-dev libssl-dev libjpeg-dev zlib1g-dev`；`pg_ctlcluster 15 main start`；`redis-server /etc/redis/redis.conf --daemonize yes`；建库 `runuser -u postgres -- psql -c "CREATE USER netbox ..."`。
  - NetBox 需要在 `/opt/netbox-4.4.0/netbox/netbox/configuration.py` 提供配置（`DATABASE` 单数键、`REDIS`、`SECRET_KEY`、`PLUGINS`）。
  - 执行插件迁移前，必须在 configuration.py 设置 `DEVELOPER = True`，否则 NetBox 内置的 `makemigrations` 命令会被禁用。
  - 启动 Web：`cd /opt/netbox-4.4.0/netbox && /opt/netboxenv/bin/python manage.py runserver 0.0.0.0:8000 --insecure`（`--insecure` 使 DEBUG=False 时仍可提供静态文件）。
  - 启动后台任务：`/opt/netboxenv/bin/python manage.py rqworker high default low`，否则 `JobRunner` 任务不会被消费。
  - 插件以可编辑方式安装：`/opt/netboxenv/bin/pip install -e /workspace`。

[Project Knowledge Summary]
- Date: 2026-10-13
- Context: Discovered by Agent while deploying the netbox-nutanix plugin for testing
- Category: Build Methods
- Instructions:
  - netbox-nutanix 依赖 `netbox.object_actions`（4.4+），因此 `min_version` 至少为 `4.4.0`；在 NetBox 4.2/4.3 上加载会因缺少该模块失败。
  - 插件模型必须继承 `netbox.models.NetBoxModel`（而非 `ChangeLoggedModel`），否则 `NetBoxModelFilterSet` 自动注入的 `tag` 过滤器会因模型缺少 `tags` 字段而报错 `Invalid field name/lookup on tag: tags__slug`。
  - 修改模型基类后需重新生成迁移：把 `netbox_nutanix/migrations/0001_initial.py` 移走后执行 `manage.py makemigrations netbox_nutanix`（需 `DEVELOPER = True`）。

[Project Knowledge Summary]
- Date: 2026-10-13
- Context: Discovered by Agent while running the netbox-nutanix test suite
- Category: Testing Methods
- Instructions:
  - 运行插件测试：`cd /opt/netbox-4.4.0/netbox && /opt/netboxenv/bin/python manage.py test netbox_nutanix -v1 --noinput --keepdb`。
  - 该目录下模型的 DB 集成测试（`TestCase`）首次会创建完整 NetBox 测试库，需应用全部迁移，耗时约 10 分钟；务必使用 `--keepdb` 复用测试库，后续运行仅需数秒。
  - 若测试库残留导致删除提示，加 `--noinput` 让其自动处理。
  - 该命令属资源密集型长任务，应通过 background terminal 执行（省略 cgroup 限制，仅设 `timeout`）。
  - 纯 `SimpleTestCase` 单元测试不建库，运行很快；只有引入 `TestCase` 才会触发建库。

[Project Knowledge Summary]
- Date: 2026-10-13
- Context: Discovered by Agent while enabling the netbox_vmware plugin alongside netbox_nutanix for testing
- Category: Environment Configuration
- Instructions:
  - setuptools 可编辑安装（`pip install -e /workspace`）只会暴露 `pyproject.toml` 中 `packages.find.include` 列出的包；同一工作区里的其他包无法导入，即使它在 `/workspace` 下。
  - 要让同一工作区的第二个插件包（如 `netbox_nutanix`）可导入，可在 venv 的 site-packages 放一个 `.pth` 文件，内容为 `/workspace`；随后把该插件加入 `configuration.py` 的 `PLUGINS`，其 ContentType 才能被 `model_class()` 解析。
  - 当某个插件的残留 `core.Job` 记录引用了一个已卸载插件的 ContentType 时，`/core/jobs/` 会因预取失败报 `'NoneType' object has no attribute '_base_manager'`（500）。修复方式：让对应插件重新可导入并启用，或清理这些残留 Job。
  - ESXi 端点的 SOAP API（`/sdk`）用 pyvmomi 访问；部分 ESXi 只提供 SOAP，不提供 vSphere Automation REST（`/api`，会返回 400/JSON-RPC 错误）。连接 ESXi 需在 venv 安装 `pyvmomi`（`/opt/netboxenv/bin/pip install pyvmomi`）。
  - 手动触发端点同步（走 worker）：`VMwareSyncJob.enqueue(instance=endpoint, name=..., cluster_pk=endpoint.pk, sync_hosts=True, sync_vms=True)`。

[Project Knowledge Summary]
- Date: 2026-10-14
- Context: Discovered by Agent while troubleshooting a NetBox "Static Media Failure" after the dev environment restarted
- Category: Troubleshooting & Debugging
- Instructions:
  - 开发环境重启后 PostgreSQL 与 Redis 都会停：需 `pg_ctlcluster 15 main start` 与 `redis-server /etc/redis/redis.conf --daemonize yes`（`service redis-server start` 会因日志文件属主 root 报 Permission denied 而失败）。
  - 环境重启后 STATIC_ROOT（`/opt/netbox-4.4.0/netbox/static`，源自 `project-static/`）会被清空，页面报 "Static Media Failure ... setmode.js"。修复：`manage.py collectstatic --noinput`。
  - Web 以 `runserver 0.0.0.0:8000 --insecure --noreload` 启动（DEBUG=False 时 `--insecure` 才服务 /static/）；Python 代码改动需重启，模板改动实时生效。
  - 后台任务需 `manage.py rqworker`（新版 rqworker 无需显式队列名，默认 high/default/low）。

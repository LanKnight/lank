# 彻底清除 GitHub 仓库里的 AI 署名（保姆级全流程）

适用场景：GitHub 仓库的 Contributors（贡献者）列表里出现了 `claude` 或其它 AI 账号，需要从提交历史、本地对象、GitHub 服务端缓存三个方向彻底清除。也适用于把这件事交给 AI Agent 代劳时，如何给出可验收的指令。

本文基于 `LanKnight/lank` 仓库 2026-10 的一次完整实战写成，并修正了网传流程里几处会导致"删了还在"的疏漏。文中命令以 Windows PowerShell 为准，Linux/macOS 用户把 `%USERPROFILE%`、盘符路径换成对应写法即可。

---

## 目录

- 阶段 0：先建立正确的心智模型（五个位置，别只处理一层）
- 阶段 1：环境与安全准备（备份放在仓库外）
- 阶段 2：第 ① 层排查——当前历史里到底有没有署名
- 阶段 3：第 ② 层排查——本地还有没有指向旧历史的引用
- 阶段 4：第 ① 层修复——重写历史
- 阶段 5：推送并做本地物理清理
- 阶段 6：第 ③ 层验证与修复——服务端缓存（本文重点）
- 阶段 7：交付验收清单
- 阶段 8：防复发
- 附录 A：让 AI Agent 代操作的完整规范
- 附录 B：踩坑与排错对照表
- 附录 C：本次实战事实记录

---

## 阶段 0：先建立正确的心智模型

"署名还在"通常不是一件事，是**五个独立的位置**。绝大多数人失败的原因，是只处理了其中一层，然后对着另外几层反复 force push。

| 编号 | 它到底是什么 | 在哪能看到 | 处理手段 | 生效速度 |
| --- | --- | --- | --- | --- |
| ① | **当前历史**：提交信息里真的有 `Co-Authored-By: Claude <noreply@anthropic.com>` 这类尾注 | `git log`、commit 页面、`.patch` 文件 | 重写历史（filter-repo / filter-branch） | 推送后即时 |
| ② | **本地旧对象**：tag、分支、`refs/original/`、reflog、stash 还指向带署名的老提交 | `git for-each-ref`、`git fsck --unreachable` | 删引用 + `reflog expire` + `gc --prune=now` | 即时（仅本地） |
| ③-A | **commit 图索引**：Insights → Contributors 折线图、`/repos/{owner}/{repo}/contributors` API、`/stats/contributors` API | 图表页、API | 等索引重算 | 十几分钟到数小时 |
| ③-B | **仓库首页右栏 Contributors 缓存**：走 `/_sidebar` 端点，是一份独立的仓库级贡献者统计 | 仓库首页右侧边栏 | **切默认分支来回**，逼 GitHub 重算 | 约 30 秒 |
| ③-C | **服务端旧对象直链**：老 commit 的 URL 短期仍能打开 | `/commit/<老SHA>` | 等它自行过期，或提 Support 工单 | 数天 |

**这一节是全文最重要的判断依据**，务必记住两句话：

1. **③-A 干净 ≠ ③-B 干净。** 网上流传的流程把 `/graphs/contributors-data?all=1` 当作"权威唯一真相"，实测会翻车：该接口只剩真实作者时，仓库首页右栏依然能显示 2 人（含 AI 账号）。侧栏和图表根本不是一个数据源。
2. **③-C 不影响名单。** 老 commit 直链残留是正常的服务端对象缓存，不参与贡献者统计，不用为它反复重写历史。

### 按症状直达

先对一下你看到的现象，直接跳到对应阶段，不要从头跑一遍。

| 你看到的现象 | 问题在哪层 | 直接跳到 |
| --- | --- | --- |
| 仓库首页右栏 Contributors 里有 AI 账号 | ③-B | 阶段 6.2 → 6.3（重点） |
| Insights → Contributors 图表里有 AI 账号 | ③-A | 阶段 6.1 |
| `git log` 能看到 `Co-Authored-By` | ① | 阶段 2 → 4 |
| 推送报 `stale info` | ①（本地引用错位） | 阶段 5.1 |
| 老 commit 链接还能打开 | ③-C | 正常现象，等过期 |
| 控制台中文乱码、以为提交信息坏了 | 工具链 | 阶段 2.4 |

---

## 阶段 1：环境与安全准备

### 1.1 确认工具版本

```powershell
git --version
python -V
```

要求 git 2.30 以上（`--force-with-lease` 语义完善）、有可用的 Python 3（重写脚本用）。

### 1.2 PowerShell 的两个硬性注意点

- **不要在 PowerShell 里用 `&&` 串联命令**，5.x 会直接报语法错误，一律用分号 `;`。
- **git 的进度/警告走 stderr**，PowerShell 会把它们标成红色"错误"，看着像失败其实不是。判断成败看退出码：

```powershell
echo $LASTEXITCODE
```

### 1.3 先做仓库外镜像备份（不然后面没有退路）

```powershell
cd D:\aboutWork
git clone --mirror --no-hardlinks D:\aboutWork\lank D:\aboutWork\_lank_backup_before_rewrite.git
```

预期输出：`Cloning into bare repository ...` 加 `done.`。

验证备份里有全部提交：

```powershell
cd D:\aboutWork\_lank_backup_before_rewrite.git
git rev-list --all --count
```

**注意**：备份必须放在**仓库目录之外**。放在仓库里、或者用 tag 备份在仓库里，都会成为"署名复活"的种子——一次手滑的 `git push --mirror` 就能把老历史推回去。

### 1.4 网络：直连 GitHub 可能被重置

如果后面 `git push` 报 `Recv failure: Connection was reset`，改用代理（端口按你本机实际代理调整）：

```powershell
git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin main
```

### 1.5 记录重写前的远端真值（后面修复引用要用）

```powershell
git ls-remote origin
```

把那一刻的 `refs/heads/main` 的完整 SHA 抄下来，例如 `43b32f1...`。这个值在第 5.3 节会用两次。

---

## 阶段 2：第 ① 层排查——当前历史里到底有没有署名

### 2.1 搜全部引用

```powershell
git --no-pager log --all -i --grep="co-authored-by" --format="%h %s"
```

- **有输出**：说明存在带尾注的提交，必须重写历史（进入阶段 4）。
- **无输出**：当前历史干净，跳到阶段 3 检查本地引用。

### 2.2 只看当前分支

```powershell
git --no-pager log -i --grep="co-authored-by" --format="%h %s" main
```

如果 `--all` 有、`main` 没有，说明署名挂在别的分支/tag 上（层②），此时**不要**重写 `main` 历史，先处理那些引用。

### 2.3 看清完整提交信息与作者身份

```powershell
git --no-pager log --all -i --grep="claude" --format="===%h===%n%B" -n 10
```

要确认两件事：

1. 尾注到底长什么样（`Co-Authored-By: Claude <noreply@anthropic.com>` 还是带 `Claude Code` 链接的其它格式）。**正则要按实际格式写**，不要照抄别人的。
2. `Author` / `Committer` 是不是你自己。如果 author 邮箱就是 AI 账号关联的邮箱，光删尾注没用，还要改 author 邮箱。

查看作者与提交者：

```powershell
git --no-pager log --all -i --grep="claude" --format="%h %an <%ae> | %cn <%ce>"
```

### 2.4 中文提交信息显示乱码 ≠ 仓库坏了

在 PowerShell 里用 `>` 或 `Out-File` 重定向 `git log` 的输出，中文会变成 `鏂囨。` 这种乱码。这是**重定向时的编码转换**问题，不是仓库真的坏了。想确认原始字节，让 Python 直接读子进程输出：

```powershell
python -c "import subprocess;d=subprocess.run(['git','log','-1','--format=%B'],capture_output=True);open('_verify.txt','wb').write(d.stdout)"
```

然后用 UTF-8 编辑器看 `_verify.txt`。**不要因为控制台乱码就以为提交信息需要修复**，会白白多改一轮。

---

## 阶段 3：第 ② 层排查——本地还有没有指向旧历史的引用

### 3.1 本地所有引用

```powershell
git for-each-ref --format="%(objecttype) %(refname) %(objectname:short)"
```

逐行看，重点关注：

- `refs/tags/*`：任何 tag 都可能是老历史的锚点
- `refs/original/*`：`filter-branch` 留下的备份引用，必须删
- `refs/heads/*`：除主分支外是否还有别的分支
- `refs/stash`：有没有藏起来的 stash
- `refs/remotes/*`：远端追踪引用（这一项在阶段 5.3 有专门的坑）

### 3.2 远端所有引用

```powershell
git ls-remote origin
```

**重点**：如果远端存在你本地没见过的小分支或 tag，先想清楚它们是什么。它们若指向带署名的老提交，会通过 PR 或镜像推送让署名复活。

### 3.3 不可达对象数量

```powershell
(git fsck --unreachable --no-progress 2>$null | Measure-Object -Line).Lines
```

记录这个数字。重写并清理后，它应该回到 0。

---

## 阶段 4：第 ① 层修复——重写历史

### 4.1 前置：工作区必须干净

```powershell
git status --porcelain
```

有未提交改动就先提交或 stash。重写期间不要让工作区处于半改动状态。

### 4.2 方案 A：git filter-repo（首选，若无网络则走方案 B）

安装：

```powershell
python -m pip install git-filter-repo
```

如果报 `SSL: UNEXPECTED_EOF_WHILE_READING`（国内常见），依次尝试：

```powershell
python -m pip install --proxy http://127.0.0.1:7897 git-filter-repo
```

还不行就**直接用方案 B**，`filter-branch` 是 git 内置的，零依赖，37 个提交量级完全够用。

用 filter-repo 删尾注（正则按阶段 2 确认的实际格式改写）：

```powershell
git filter-repo --force --message-callback "return re.sub(rb'(?im)^Co-Authored-By:\s*Claude[^\n]*\n?', b'', message)"
```

两个容易忽略的点：

- **必须加 `--force`**：`filter-repo` 默认拒绝在非 fresh clone 上重写历史。
- **`filter-repo` 出于防误推会动 `origin`**（不同版本行为不一致，可能直接移除，也可能改名备份）。跑完先检查：

```powershell
git remote -v
```

如果为空，重新加回来，再继续后续步骤：

```powershell
git remote add origin https://github.com/<owner>/<repo>.git
```

### 4.3 方案 B：git filter-branch（Windows 实测可行）

**第一步**，把剥离逻辑写成独立脚本 `D:\tools\_strip_coauthor.py`（放仓库外，避免污染工作区）：

```python
import re
import sys

data = sys.stdin.buffer.read()

# 删除整行 co-authored-by 尾注（大小写不敏感，兼容任意邮箱）
pattern = re.compile(rb"(?im)^[ \t]*co-authored-by:[ \t]*(claude|anthropic)[^\n]*\n?")
data = pattern.sub(b"", data)

# 顺带压掉尾部多余空行，避免留下连续空行
data = re.sub(rb"\n{3,}", b"\n\n", data).rstrip(b"\n") + b"\n"

sys.stdout.buffer.write(data)
```

用二进制读写是关键：提交信息是 UTF-8 字节，用文本模式容易在 Windows 上被转码破坏。

**第二步**，只重写当前分支，**不要用 `--all`**：

```powershell
git filter-branch -f --msg-filter "python D:/tools/_strip_coauthor.py" -- HEAD
```

预期输出一堆 `Rewrite <sha> (n/总数)`，最后 `Ref 'refs/heads/main' was rewritten`。

为什么坚持不用 `--all`：`--all` 会把 `refs/remotes/origin/main` 一起重写，导致远端追踪引用的值和真实远端不一致，后面 `--force-with-lease` 会因为"本地认为远端已经是新值"而失效，甚至误判冲突。只用 `HEAD`（或 `main`）就足够，且不碰任何远端引用。

**如果你已经用了 `--all`**，跳到阶段 5.3 做引用修复。

### 4.4 重写后立刻做的三项校验

**校验一：尾注真的没了**

```powershell
git --no-pager log --all -i --grep="co-authored-by" --format="%h %s"
```

必须无输出。注意：`git log` 无匹配时**退出码仍是 0**，这里只能看"有没有输出"，不能看退出码。

**校验二：代码内容一字未变（只改了 message）**

```powershell
git --no-pager diff --stat <重写前的完整SHA> HEAD
```

必须无输出。如果有输出，说明你的 msg-filter 脚本出错了（比如误读了 stdin），立刻用备份回滚：

```powershell
git reset --hard <重写前的完整SHA>
```

**校验三：提交数量没有意外减少**

```powershell
git rev-list --all --count
```

重写只改 SHA，不会增加或减少提交数量。

---

## 阶段 5：推送并做本地物理清理

### 5.1 用 force-with-lease 而不是 force

```powershell
git push --force-with-lease origin main
```

`--force-with-lease` 会在"远端当前值 ≠ 本地记录的远端追踪值"时拒绝推送，避免覆盖别人的新提交。

前提：本地 `refs/remotes/origin/main` 必须还是真实远端的旧值。如果你跑过 `filter-branch --all` 或 `filter-repo`，这个前提可能已被破坏，表现是：

```
! [rejected] main -> main (stale info)
```

两种处理：

```powershell
# 做法一：重新对齐远端追踪引用，再推
git fetch origin
git push --force-with-lease origin main

# 做法二：显式声明你预期远端是哪个 SHA（更精确）
git push --force-with-lease=main:<阶段 1.5 记下的旧SHA> origin main
```

### 5.2 推送成功的样子

```
 + 43b32f1...5ce9848 main -> main (forced update)
```

### 5.3 引用修复：`--all` 与 `origin/HEAD` 的坑

如果你跑过 `filter-branch --all`，会出现两个后遗症，**必须修**，否则会出现"远端引用莫名指向另一个 SHA"的怪现象：

```powershell
# 1) 看被改写成什么样了
git for-each-ref --format="%(refname) %(objectname:short)" refs/remotes

# 2) 把远端追踪引用恢复成真实远端值（阶段 1.5 记下的 SHA）
git update-ref refs/remotes/origin/main <旧SHA>
```

`origin/HEAD` 原本是一个**符号引用**（指向 `origin/main`），`update-ref` 会把它变成普通引用，必须改回来：

```powershell
git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
git symbolic-ref refs/remotes/origin/HEAD   # 确认输出 refs/remotes/origin/main
```

### 5.4 删掉 filter-branch 的备份引用（层②的关键一步）

```powershell
git for-each-ref refs/original --format="%(refname)"
git update-ref -d refs/original/refs/heads/main
git update-ref -d refs/original/refs/remotes/origin/main
git for-each-ref refs/original --format="%(refname)"   # 应无输出
```

### 5.5 物理丢弃不可达对象

```powershell
git reflog expire --expire=now --all
git gc --prune=now
```

`reflog` 不清，老提交就还"可达"；只 `gc` 不 `reflog expire`，多数情况下对象删不掉。

### 5.6 验证老历史真的死了

```powershell
git cat-file -t <旧SHA>
```

预期：`fatal: Not a valid object name <旧SHA>`。

```powershell
(git fsck --unreachable --no-progress 2>$null | Measure-Object -Line).Lines
```

预期：`0`。

这两条都过了，本地就不会再有任何途径把带署名的历史推回远端——包括 `git push --mirror`。

---

## 阶段 6：第 ③ 层验证与修复——服务端缓存

### 6.1 先查 ③-A（图表与 API）

四条探针，任选其一即可（建议都跑，判断更稳）。命令里的 `<owner>/<repo>` 换成你的仓库，比如 `LanKnight/lank`：

```powershell
# 1) 仓库贡献者 API
python -c "import json,urllib.request;u='https://api.github.com/repos/<owner>/<repo>/contributors';r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=30);print([x['login'] for x in json.loads(r.read())])"

# 2) 提交统计 API
#    直接浏览器打开 https://api.github.com/repos/<owner>/<repo>/stats/contributors
#    看返回数组里每个元素的 author.login

# 3) 图表数据接口（未登录可访问）
#    直接浏览器打开 https://github.com/<owner>/<repo>/graphs/contributors-data?all=1
#    看返回 JSON 里的 author.login
```

- 都只剩你自己 → ③-A 已经干净，去查 ③-B。
- 命中 `403 rate limit exceeded` → 是 API 匿名限流，**不是**"还没删干净"。等一会儿、换接口（3 号探针不需要 token）或直接在浏览器看。
- 仍含 AI 账号 → 要么历史没重写干净，要么索引还没重算，隔几小时再查。

### 6.2 关键：如何判断问题在 ③-B（服务端）而不是浏览器缓存

这一步是本次实战最大的坑。用"硬刷新没用"就断定"肯定是缓存"是错的，必须做下面三步判定。

**判据一：侧栏数据走哪个端点**

仓库首页右栏的 Contributors 是懒加载的，早期端点 `/contributors_list?count=10` 已经**废弃**，现在一律返回空列表，拿它当证据会得出错误结论：

```html
<ul class="list-style-none ">
</ul>
```

新版页面真正取数的是 `/_sidebar` 端点（未登录直接请求会返回 `406`，属正常）。判断它有没有被浏览器缓存，看响应头：

```
Cache-Control: no-cache
```

`no-cache` 的含义是"每次都要回源校验"。既然每次都回源，页面上还显示旧数据，那就说明**旧数据在 GitHub 服务端**，本地怎么刷都没用。这正是"删了还在"的真正原因。

**判据二：两个数据源口径不一致就是对不上的铁证**

在同一个浏览器、同一时刻：

| 观察点 | 修好前 | 修好后 |
| --- | --- | --- |
| 首页右栏 Contributors | 2 人（自己 + claude） | 1 人（只有自己） |
| Insights → Contributors 图表 | 1 人 | 1 人 |
| `contributors-data?all=1` | 1 人 | 1 人 |

侧栏 2 人、图表 1 人——这就是 ③-B 缓存未重算的典型特征。

**判据三：只有登录态才能看到侧栏名单**

未登录访问首页，Contributors 区块是骨架屏，不会渲染名单。所以"我这边用脚本抓 HTML 是干净的"并不能反证你看到的是缓存——**必须用登录态浏览器实地截图**（见附录 A）。

### 6.3 修复：切默认分支逼重算

原理：贡献者索引以"默认分支可达历史"为基准。把默认分支短暂指向一段新历史，会强制 GitHub 重算，切回来时按干净历史再算一次。

**第 1 步：准备临时分支（必须与主分支同一个 commit）**

```powershell
git branch temp-cache-refresh main
git push origin temp-cache-refresh
```

同一个 commit 的意义：切换期间仓库对外显示的内容**零差异**，只是换了个分支名。

**第 2 步：在网页改默认分支**

> 注意：GitHub 新版已经把 Default branch 从 `Settings → Branches` 迁到 **`Settings → General`**。`Settings → Branches` 现在只剩 Branch protection rules，照老教程找会找不到。

路径：

```
仓库页 → Settings → General → 找到 "Default branch" → 点右侧的切换图标（双向箭头）
→ 下拉选 temp-cache-refresh → Update
→ 二次确认框："I understand, update the default branch." → 确认
```

成功标志：页面顶部横幅 `Default branch changed to temp-cache-refresh`。

**第 3 步：等 30~40 秒，再切回原分支**

同样的路径，选回 `main`，确认后横幅应显示 `Default branch changed to main`。

**第 4 步：验证**

回到仓库首页，等侧栏渲染（懒加载，可能需要滚动一下或等 10 秒），看 Contributors：

- 计数变成 1，只剩你自己 → 成功。
- 再按 `Ctrl+Shift+R` 硬刷新一次，确认结果稳定。

**第 5 步：删掉临时分支**

```powershell
git push origin --delete temp-cache-refresh
git branch -D temp-cache-refresh
git remote prune origin
```

如果 `--delete` 报 `Recv failure: Connection was reset`，是网络抖动，**先重试一次**；仍失败就走代理：

```powershell
git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin --delete temp-cache-refresh
```

本地那个 `refs/remotes/origin/temp-cache-refresh` 要用 `git remote prune origin` 清掉，否则每次 `for-each-ref` 都会看到一个幽灵分支。

### 6.4 如果切默认分支也没用

按代价从低到高：

| 方案 | 代价 | 说明 |
| --- | --- | --- |
| 等 24 小时后再看 | 时间 | 官方口径约 24 小时刷新一次贡献者索引 |
| 提 GitHub Support 工单 | 慢，需登录 | 说明"已 force push 清理历史，请求清除贡献者缓存"，附仓库地址与操作时间 |
| orphan 分支强推覆盖 | 高 | 默认分支会短暂接近空仓库，风险大，不建议 |
| 删库重建 | 最高 | 丢 star / issue / 旧链接，非必要不做 |

---

## 阶段 7：交付验收清单

全部命令都通过，才算真的做完。

```powershell
# 1. 当前历史无尾注（应无输出）
git --no-pager log --all -i --grep="co-authored-by" --format="%h %s"

# 2. 本地不可达对象为 0
(git fsck --unreachable --no-progress 2>$null | Measure-Object -Line).Lines

# 3. 老 SHA 已不存在（应报 fatal: Not a valid object name）
git cat-file -t <旧SHA>

# 4. 本地只有主分支
git for-each-ref --format="%(refname) %(objectname:short)"

# 5. 远端只有主分支（无临时分支、无老 tag）
git ls-remote origin

# 6. 工作区干净
git status --porcelain
```

页面侧验收（必须用**登录态浏览器 + 截图**）：

- 仓库首页右栏 Contributors 计数为 1，名单里没有 AI 账号
- `Ctrl+Shift+R` 硬刷新后仍是 1
- Insights → Contributors 图表只有自己
- 换一个浏览器账号或隐身窗口（未登录也能看图表页）复核一致

---

## 阶段 8：防复发

### 8.1 从源头关掉尾注

多数 AI 编码工具默认会写 `Co-Authored-By`。在工具配置里关闭该行为；同时确认自己的提交身份是你的、且已验证的 GitHub 邮箱：

```powershell
git config --global user.name "你的名字"
git config --global user.email "你的GitHub已验证邮箱"
git config --global --list | Select-String user
```

### 8.2 提交钩子兜底（本地拦截）

创建 `.git/hooks/commit-msg`，内容：

```sh
#!/bin/sh
# 剥离 AI co-author 尾注
msg_file="$1"
if grep -qiE '^[[:space:]]*co-authored-by:.*(claude|anthropic|openai|copilot)' "$msg_file"; then
  sed -i.bak -E '/^[[:space:]]*[Cc]o-[Aa]uthored-[Bb]y:.*([Cc]laude|[Aa]nthropic|[Oo]pen[Aa][Ii]|[Cc]opilot)/d' "$msg_file"
  rm -f "$msg_file.bak"
fi
exit 0
```

Git for Windows 用自带的 Git Bash 执行钩子，`sed -E` 可用。建好后随手验证一次：故意写一条带尾注的提交，看信息里是否被剥离。

### 8.3 CI 自检（防止绕过钩子混进主干）

`.github/workflows/no-ai-coauthor.yml`：

```yaml
name: no-ai-coauthor
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Reject AI co-author trailers
        run: |
          out=$(git log --all -i --grep='co-authored-by:.*\(claude\|anthropic\)' --format='%h %s')
          if [ -n "$out" ]; then
            echo "::error::发现 AI co-author 尾注："
            echo "$out"
            exit 1
          fi
```

### 8.4 定期复查

```powershell
git --no-pager log --all -i --grep="co-authored-by" --format="%h %s"
```

建议每次批量 AI 生成代码后跑一次，成本极低，能在推送前发现漏网的尾注。

---

## 附录 A：让 AI Agent 代操作的完整规范

场景：你让 Agent "自己打开浏览器看"。这一步不是让 Agent 猜，而是让它做**登录态实地截图 + 逐项断言**。以下是可直接复用的规范。

### A.1 为什么必须用登录态浏览器

| 检查方式 | 能看到侧栏名单吗 | 能否作为定论 |
| --- | --- | --- |
| `curl` / `urllib` 抓首页 HTML | 否，未登录只有骨架屏 | 不能 |
| 抓 `/contributors_list` 旧端点 | 否，该端点已废弃，恒返回空 `<ul>` | 不能，会误导 |
| 抓 `contributors-data?all=1` | 是（但这是图表数据源） | 只能说明 ③-A |
| **登录态浏览器打开首页** | **是** | **可作为定论** |

### A.2 第一段指令：只读侦察（不碰任何设置）

把下面这段原样发给 Agent：

```
请用浏览器实地检查 GitHub 仓库 <仓库URL> 的贡献者情况，全程只读，不要点击任何修改设置的按钮。

1. 打开仓库首页，等待右侧栏 Contributors 区块懒加载完成（可能要等 10 秒或滚动一次）。
2. 记录：Contributors 计数是几？逐个列出其中的账号名（链接里的 login），特别确认是否还有 <目标账号名>。
3. 确认当前浏览器是否处于登录态：读取 meta[name="user-login"] 的值，或看右上角是否有账户菜单。
4. 截图并给出截图的绝对文件路径。
5. 再打开 /graphs/contributors 页面，等图表加载完成（不再显示 "Crunching the latest data"），
   列出贡献者账号名，同样截图给路径。
6. 用中文回报：侧栏计数与账号列表、图表账号列表、两张截图的绝对路径、当前登录账号名。
   如果某个区块没有渲染出来，如实说明，不要猜测。
```

**验收标准**（Agent 的回答必须同时满足）：

- 明确写出了计数（如 "Contributors 2"），不是"看起来差不多"
- 逐个列出了账号 login，而不是只有数量
- 给出了截图的**绝对路径**，且你能用图片查看工具打开
- 明确回答了登录状态与登录名

### A.3 第二段指令：写操作（仅在用户明确授权后）

本例中"写操作"只有一个：切换默认分支。指令模板：

```
请代我执行"切默认分支逼重算"，严格限定：只操作 Default branch 这一个设置，
不要碰 Branch protection rules、Rulesets 或任何其它设置，不要删除分支。

1. 打开 Settings → General（注意：不是 Settings → Branches，新版已迁移）。
2. 记录当前 Default branch 并截图。
3. 点切换图标，选 temp-cache-refresh，确认（含二次确认框），确认横幅出现
   "Default branch changed to temp-cache-refresh"，截图并记录时间。
4. 等待 30~40 秒。
5. 切回 main，确认横幅出现 "Default branch changed to main"，截图。
6. 回仓库首页，等侧栏渲染，检查 Contributors 计数与账号列表，截图。
7. Ctrl+Shift+R 硬刷新后再检查一次，确认结果稳定。
8. 回报：默认分支的完整变化链路（原值→临时值→原值）、每一步截图绝对路径、
   最终侧栏计数与账号列表、硬刷新后是否一致。
   任何一步失败（找不到按钮、下拉里没有临时分支、报错）立即停止后续步骤，
   保持默认分支为原值，并如实说明卡在哪一步。
```

**验收标准**：

- 报告里能看到两次变化横幅（去和回），不是只说"我切了"
- 最终默认分支已回到原值
- 侧栏计数由 2 变 1（或目标期望值）
- 硬刷新后结果一致

### A.4 常见 Agent 误判与纠正

| Agent 的说法 | 问题 | 你要追问什么 |
| --- | --- | --- |
| "API 已经是干净的了，是你浏览器缓存" | 只看 ③-A，漏了 ③-B | "首页右栏 Contributors 实际显示几个人？截图给我" |
| "`contributors_list` 返回空，说明没问题" | 该端点已废弃，空是正常的 | "改用登录态首页截图，或看 `/_sidebar`" |
| "我抓的 HTML 里没有 claude" | 未登录时侧栏不渲染 | "你登录了吗？meta user-login 是什么" |
| "Controls 里找不到 Default branch" | 走错到 Branches 页 | "去 Settings → General" |
| "截图在我这边看不到" | 没给绝对路径 | "把截图保存到 <项目目录>/环境报告/ 并给我绝对路径" |

### A.5 权限边界

- 只读侦察（A.2）不需要额外授权，随时可做。
- 写操作（A.3）涉及仓库设置，必须**事先获得仓库所有者明确同意**，且限定单一设置项。
- 不要代填任何 GitHub 凭据；需要登录时必须由本人在浏览器里完成。

---

## 附录 B：踩坑与排错对照表

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| 删完尾注，侧栏还显示 AI 账号 | 侧栏是独立缓存（③-B），跟图表/API 不是一个数据源 | 切默认分支逼重算（阶段 6.3） |
| 硬刷新、无痕窗口都还在 | 旧数据在服务端，`_sidebar` 是 `no-cache` | 同上，别在浏览器层面折腾 |
| `pip install git-filter-repo` 报 SSL EOF | 网络受限 | 加 `--proxy`，或直接用 `filter-branch`（阶段 4.3） |
| `filter-repo` 报 "not a fresh clone" | 它默认拒绝重写非全新克隆 | 加 `--force` |
| `filter-repo` 跑完 `git remote -v` 空了 | 它故意移除 origin 防误推 | `git remote add origin ...` |
| `filter-branch` 报 "previous backup already exists" | `refs/original/` 已存在 | 加 `-f`，或先删 `refs/original` |
| 推送报 `stale info` | 远端追踪引用被 `--all` 改过，与真实远端不一致 | `git fetch` 或用 `--force-with-lease=main:<SHA>` |
| `origin/HEAD` 不再是符号引用 | `update-ref` 把它变成了普通引用 | `git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main` |
| 控制台中文全是乱码 | PowerShell 重定向的编码转换，不是仓库坏了 | 用 Python 读子进程字节后另存 UTF-8（阶段 2.4） |
| `git log --grep` 没命中但退出码是 0 | `git log` 无匹配也返回 0 | 只看有没有输出，不看退出码 |
| `git log` 输出里 Git 警告标红一片 | PowerShell 把 stderr 当错误 | 看退出码与实际输出，忽略颜色 |
| API 返回 403 rate limit exceeded | 匿名 API 限流 | 换接口（图表接口不需 token）或等一会儿 |
| `git gc --dry-run` 报参数不支持 | 部分 git 版本未实现 | 不用 dry-run，直接 `gc --prune=now` |
| 删远端分支报 Connection was reset | 网络抖动 | 重试一次，仍失败走代理 |
| 老 commit 直链还能打开 | ③-C 服务端旧对象缓存 | 正常现象，不影响名单，等待过期 |

---

## 附录 C：本次实战事实记录

供复盘对照，也方便你确认自己走到了哪一步。

| 项 | 值 |
| --- | --- |
| 仓库 | `github.com/LanKnight/lank` |
| 重写前 main tip | `43b32f1`（共 37 个提交） |
| 带署名提交 | `e004891`、`f1fd6f0`、`e4c750b`、`7ba8d07`、`c183444`（5 个） |
| 署名格式 | `Co-Authored-By: Claude <noreply@anthropic.com>` |
| 重写工具 | `git filter-branch -f --msg-filter`（`filter-repo` 因网络无法安装） |
| 重写后 main tip | `ee24b91` → 追加一次注释中性化提交后为 `5ce9848` |
| 内容校验 | 重写前后 `git diff --stat` 无输出，代码零变化 |
| 层② 清理 | 删 `refs/original/*` → `reflog expire --expire=now --all` → `gc --prune=now`；`fsck --unreachable` 归零 |
| 层③-A 修复时间 | 重写推送后数小时内，`contributors-data` 由 202（重算中）转为 200，仅剩 LanKnight |
| 层③-B 修复方式 | 临时分支 `temp-cache-refresh` → Settings → General 切默认分支 → 35 秒后切回 main |
| 层③-B 效果 | 侧栏 Contributors 由 2 人变为 1 人，硬刷新后稳定 |
| 收尾 | 删除临时分支（远端 + 本地）、`git remote prune origin`，远端仅剩 `refs/heads/main` |

一句话总结这份流程的重点：**先分层定位，再用能证明问题在哪一层的证据下结论，最后才动手。** 对着已经干净的历史反复 force push，和对着服务端缓存反复硬刷新，是这件事上最容易浪费时间的两种做法。

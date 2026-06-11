# BQL 查询链路分析

本文档详细分析 Fava 中 BQL (Beancount Query Language) 查询的完整链路，包括前端条件构建、后端解析规划、缓存复用机制和 reload 失效边界。

## 一、前端条件构建链路

### 1.1 查询条件来源

BQL 查询的条件由两部分组成：

1. **用户输入的 BQL 查询语句** (`query_string`)
2. **全局过滤器参数** (`filter_params`)：`time`、`account`、`filter`

**关键代码位置**：`frontend/src/reports/query/Query.svelte:43-68`

```javascript
function submit() {
  const query = query_string;
  // ...
  query_shell_history.add(query);
  router.set_search_param("query_string", query);
  get_query({ query_string: query, ...$filter_params })
    .then(/* ... */);
}
```

### 1.2 全局过滤器状态管理

**关键代码位置**：`frontend/src/stores/filters.ts:34-42`

```typescript
export const filter_params = derived(
  [time_filter, account_filter, fql_filter],
  ([$time_filter, $account_filter, $fql_filter]): Filters => ({
    time: $time_filter,
    account: $account_filter,
    filter: $fql_filter,
  }),
);
```

三个过滤器均派生自 `searchParams` store，与 URL 同步：

| 过滤器 | URL 参数 | 作用 |
|--------|----------|------|
| `time_filter` | `time` | 时间范围过滤 |
| `account_filter` | `account` | 账户过滤 |
| `fql_filter` | `filter` | 高级 FQL 语法过滤 |

### 1.3 查询触发机制

**场景 1：用户提交查询**
- 用户在 `QueryEditor` 中输入 BQL 语句
- 点击提交或按回车触发 `submit()`
- 将 `query_string` 同步到 URL
- 调用 `get_query()` API，携带 `query_string` 和 `filter_params`

**场景 2：全局过滤器变化**
**关键代码位置**：`frontend/src/reports/query/Query.svelte:36-40, 70-88`

```javascript
onMount(() =>
  filter_params.subscribe(() => {
    rerun_all_open();
  }),
);

function rerun_all_open() {
  const to_rerun = Object.entries(is_open)
    .filter(([, is_open]) => is_open)
    .map(([query]) => query);
  results = {};
  for (const query of to_rerun) {
    get_query({ query_string: query, ...$filter_params })
      .then(/* ... */);
  }
}
```

- 订阅 `filter_params` 变化
- 变化时清空当前结果 `results = {}`
- 重新运行所有打开的查询（`is_open[query] === true`）

### 1.4 API 调用封装

**关键代码位置**：`frontend/src/api/index.ts:302-305`

```typescript
export const get_query = define_endpoint("query", query_validator, [
  ...filters,  // ["account", "filter", "time"]
  "query_string",
]);
```

`define_endpoint` 自动将参数拼接为 URL 查询字符串，最终请求格式为：
```
GET /<bfile>/api/query?query_string=...&time=...&account=...&filter=...
```

---

## 二、后端解析规划链路

### 2.1 API 端点接收

**关键代码位置**：`src/fava/json_api.py:316-320`

```python
@api_endpoint
def get_query(query_string: str) -> QueryResultTable | QueryResultText:
    """Run a Beancount query."""
    return g.ledger.query_shell.execute_query_serialised(
        g.filtered.entries_with_all_prices, query_string
    )
```

### 2.2 过滤后的账本数据 (`g.filtered`)

**关键代码位置**：`src/fava/_ctx_globals_class.py:47-54`

```python
@cached_property
def filtered(self) -> FilteredLedger:
    """The filtered ledger."""
    args = request.args
    return self.ledger.get_filtered(
        account=args.get("account", ""),
        filter=args.get("filter", ""),
        time=args.get("time", ""),
    )
```

`FilteredLedger` 构造过程 (`src/fava/core/__init__.py:119-155`)：

```python
def __init__(self, ledger, *, account=None, filter=None, time=None):
    entries = ledger.all_entries
    if account:
        entries = AccountFilter(account).apply(entries)
    if filter and filter.strip():
        entries = AdvancedFilter(filter.strip()).apply(entries)
    if time:
        time_filter = TimeFilter(ledger.options, ledger.fava_options, time)
        entries = time_filter.apply(entries)
        self.date_range = time_filter.date_range
    self.entries = entries
```

**重要**：BQL 查询使用的是 `entries_with_all_prices`，它会重新加入价格条目：

**关键代码位置**：`src/fava/core/__init__.py:181-186`

```python
@cached_property
def entries_with_all_prices(self) -> Sequence[Directive]:
    """The filtered entries, with all prices added back in for queries."""
    entries = [*self.entries, *self.ledger.all_entries_by_type.Price]
    entries.sort(key=_incomplete_sortkey)
    return entries
```

### 2.3 QueryShell 执行查询

**关键代码位置**：`src/fava/core/query_shell.py:167-185`

```python
def execute_query_serialised(
    self, entries: Sequence[Directive], query: str
) -> QueryResultTable | QueryResultText:
    res = self.shell.run(entries, query)
    return (
        QueryResultText(res) if isinstance(res, str) else _serialise(res)
    )
```

### 2.4 FavaBQLShell 与 beanquery 集成

**关键代码位置**：`src/fava/core/query_shell.py:79-108`

```python
class FavaBQLShell(BQLShell):
    def run(self, entries: Sequence[Directive], query: str) -> Cursor | str:
        self.context = connect(
            "beancount:",
            entries=entries,
            errors=self.ledger.errors,
            options=self.ledger.options,
        )
        try:
            result = self.onecmd(query)
        except ParseError as exc:
            raise QueryParseError(exc) from exc
        except CompilationError as exc:
            raise QueryCompilationError(exc) from exc

        if isinstance(result, Cursor):
            return result
        contents = self.outfile.getvalue().strip()
        self.outfile.truncate(0)
        return contents.strip().strip("\x00")
```

执行流程：
1. 调用 `beanquery.connect()` 创建查询上下文，传入过滤后的 entries、errors 和 options
2. 调用 `self.onecmd(query)` 执行查询（继承自 `BQLShell`）
3. 捕获 `ParseError` 和 `CompilationError` 并转换为 Fava 自定义异常
4. 如果返回 `Cursor` 则是表格结果，否则是文本结果（如 help、run 列表等）

### 2.5 结果序列化

**关键代码位置**：`src/fava/core/query_shell.py:242-253`

```python
def _serialise(cursor: Cursor) -> QueryResultTable:
    dtypes = [
        COLUMNS.get(c.datatype, ObjectColumn)(c.name)
        for c in cursor.description
    ]
    mappers = [d.serialise for d in dtypes]
    mapped_rows = [
        tuple(mapper(row[i]) for i, mapper in enumerate(mappers))
        for row in cursor
    ]
    return QueryResultTable(dtypes, mapped_rows)
```

列类型映射 (`src/fava/core/query.py:160-170`)：
```python
COLUMNS = {
    Amount: AmountColumn,
    Decimal: DecimalColumn,
    Inventory: InventoryColumn,
    Position: PositionColumn,
    bool: BoolColumn,
    datetime.date: DateColumn,
    int: IntColumn,
    set: SetColumn,
    str: StrColumn,
}
```

---

## 三、缓存复用机制

### 3.1 后端缓存层级

#### 层级 1：`FavaLedger.get_filtered` - LRU 缓存

**关键代码位置**：`src/fava/core/__init__.py:388, 443-458`

```python
def __init__(self, path: str, *, poll_watcher: bool = False):
    self.get_filtered = lru_cache(maxsize=16)(self._get_filtered)
    # ...

def _get_filtered(
    self, account: str | None = None, filter: str | None = None, time: str | None = None
) -> FilteredLedger:
    return FilteredLedger(
        ledger=self, account=account, filter=filter, time=time
    )
```

- 使用 `functools.lru_cache(maxsize=16)` 装饰
- 缓存键：`(account, filter, time)` 三元组
- 最多缓存 16 个不同过滤组合的 `FilteredLedger` 实例

#### 层级 2：`FilteredLedger` 属性缓存

**关键代码位置**：`src/fava/core/__init__.py:181-203`

```python
@cached_property
def entries_with_all_prices(self) -> Sequence[Directive]:
    entries = [*self.entries, *self.ledger.all_entries_by_type.Price]
    entries.sort(key=_incomplete_sortkey)
    return entries

@cached_property
def root_tree(self) -> Tree:
    return Tree(self.entries)

@cached_property
def root_tree_closed(self) -> Tree:
    tree = Tree(self.entries)
    tree.cap(self.ledger.options)
    return tree
```

- 使用 `functools.cached_property` 装饰
- 每个 `FilteredLedger` 实例内部缓存计算密集型属性
- `entries_with_all_prices` 是 BQL 查询的数据源

#### 层级 3：`Context.g` 请求上下文缓存

**关键代码位置**：`src/fava/_ctx_globals_class.py:32-54`

```python
@cached_property
def conversion(self) -> str:
    return request.args.get("conversion", "") or "at_cost"

@cached_property
def filtered(self) -> FilteredLedger:
    return self.ledger.get_filtered(...)
```

- Flask 的 `g` 对象使用 `cached_property`
- 同一请求内多次访问 `g.filtered` 只会调用一次 `get_filtered`

### 3.2 缓存命中场景

**场景 1：相同过滤器的重复查询**
```
查询1: SELECT account, sum(position) WHERE date = 2024-01-01
        with filter_params: {time: "2024", account: "", filter: ""}

查询2: SELECT account, sum(position) WHERE date = 2024-01-02
        with filter_params: {time: "2024", account: "", filter: ""}
```
- 两次查询使用相同的 `filter_params`
- `get_filtered` 缓存命中，复用同一个 `FilteredLedger`
- `entries_with_all_prices` 也会复用

**场景 2：同一请求内的多次查询**
- 如 `get_statistics` 等报告端点可能多次访问 `g.filtered`
- `Context.cached_property` 确保同一请求内只计算一次

### 3.3 前端状态跟踪

**关键代码位置**：`frontend/src/stores/mtime.ts:1-32`

```typescript
const ledger_mtime_writable = writable(BigInt("0"));

export function set_mtime(text: string): void {
  const new_value = text.startsWith("X")
    ? BigInt(text.replaceAll("X", "1"))
    : BigInt(text);
  ledger_mtime_writable.update((v) => (new_value > v ? new_value : v));
}
```

- 每次 API 响应都会返回 `mtime` 字段 (`json_api.py:108-110`)
- 前端更新本地 `ledger_mtime` store
- 用于判断后端数据是否发生变化

---

## 四、Reload 失效边界

### 4.1 文件变化检测机制

#### Watcher 架构

**关键代码位置**：`src/fava/core/watcher.py:93-134`

```python
class WatcherBase(abc.ABC):
    last_checked: int      # 上次检测到变化的时间戳
    last_notified: int     # 上次手动通知变化的时间戳

    def check(self) -> bool:
        latest_mtime = max(self._get_latest_mtime(), self.last_notified)
        has_higher_mtime = latest_mtime > self.last_checked
        if has_higher_mtime:
            self.last_checked = latest_mtime
        return has_higher_mtime

    def notify(self, path: Path) -> None:
        """手动通知变化（如文件保存后立即调用）"""
        try:
            change_mtime = Path(path).stat().st_mtime_ns
        except FileNotFoundError:
            change_mtime = max(self.last_notified, self.last_checked) + 1
        self.last_notified = max(self.last_notified, change_mtime)
```

有两种 Watcher 实现：

| Watcher 类型 | 实现方式 | 适用场景 |
|-------------|----------|----------|
| `WatchfilesWatcher` | 后台线程 + watchfiles 库（基于 inotify/fsevents） | 默认，性能好 |
| `Watcher` | 轮询检查文件 mtime | 旧系统兼容 |

### 4.2 触发 Reload 的时机

#### 时机 1：请求前自动检测

**关键代码位置**：`src/fava/application.py:261-271`

```python
@fava_app.before_request
def _perform_global_filters() -> None:
    if request.endpoint in {"json_api.get_changed", "json_api.get_errors"}:
        return
    ledger = getattr(g, "ledger", None)
    if ledger:
        # check (and possibly reload) source file
        if request.blueprint != "json_api":
            ledger.changed()

        ledger.extensions.before_request()
```

- 每个非 `json_api` 请求前都会调用 `ledger.changed()`
- `json_api` 请求中，除 `get_changed` 和 `get_errors` 外，大多在端点内部调用

#### 时机 2：`changed()` 方法

**关键代码位置**：`src/fava/core/__init__.py:511-524`

```python
def changed(self) -> bool:
    """Check if the file needs to be reloaded."""
    if self._is_encrypted:
        return False
    changed = self.watcher.check()
    if changed:
        self.load_file()
    return changed
```

#### 时机 3：手动文件操作后

**关键代码位置**：`src/fava/core/file.py:165, 168, 194, 219, 236, 259`

```python
# set_source 中
self.ledger.watcher.notify(path)
self.ledger.load_file()

# insert_metadata 中
self.ledger.watcher.notify(path)

# save_entry_slice 中
self.ledger.watcher.notify(Path(get_position(entry)[0]))

# delete_entry_slice 中
self.ledger.watcher.notify(Path(get_position(entry)[0]))

# insert_entries 中
self.ledger.watcher.notify(path)
```

- 文件写入后立即调用 `watcher.notify()` 更新 `last_notified`
- 部分操作（如 `set_source`）直接调用 `load_file()`

### 4.3 `load_file()` 缓存失效

**关键代码位置**：`src/fava/core/__init__.py:407-441`

```python
def load_file(self) -> None:
    """Load the main file and all included files and set attributes."""
    self.all_entries, self.load_errors, self.options = load_uncached(
        self.beancount_file_path,
        is_encrypted=self._is_encrypted,
    )
    self.get_filtered.cache_clear()  # 清除 LRU 缓存
    self.get_entry.cache_clear()     # 清除 LRU 缓存

    self.all_entries_by_type = group_entries_by_type(self.all_entries)
    self.prices = FavaPriceMap(self.all_entries_by_type.Price)
    # ... 重新初始化所有模块
    self.accounts.load_file()
    self.attributes.load_file()
    self.budgets.load_file()
    # ... 所有模块的 load_file 被调用
```

**失效的缓存包括**：
1. ✅ `self.get_filtered.cache_clear()` - 清除所有过滤组合的缓存
2. ✅ `self.get_entry.cache_clear()` - 清除条目查找缓存
3. ✅ 所有模块的 `load_file()` 被调用，内部状态重置
4. ✅ `FilteredLedger` 实例的 `cached_property` 随实例失效

### 4.4 前端 Reload 触发

**关键代码位置**：`frontend/src/api/index.ts:125-136`

```typescript
async function fetch_and_handle_api_call<R>(
    url: URL, init: RequestInit, validator: Validator<R>
): Promise<R> {
    const json = await fetch_json(url, init);
    if (typeof json.mtime === "string") {
        set_mtime(json.mtime);  // 更新本地 mtime
    }
    const res = validator(json.data);
    return res.unwrap(InvalidResponseDataError);
}
```

- 每次 API 响应都会返回最新的 `mtime`
- 前端更新 `ledger_mtime` store

**关键代码位置**：`frontend/src/api/index.ts:393-403`

```typescript
export async function save_entries(entries: NonEmptyArray<Entry>): Promise<void> {
    try {
        const msg = await put_add_entries({ entries });
        router.reload();  // 保存成功后强制 reload
        notify(msg);
    } catch (error) {
        // ...
    }
}
```

### 4.5 薄弱边界 1：时间戳粒度与二次改动漏检

#### 4.5.1 精确字段与精度级别

Watcher 比对依赖的**全部是纳秒级时间戳** `st_mtime_ns`，而非秒级 `st_mtime`：

**关键代码位置**：`src/fava/core/watcher.py:71, 111-122, 124-130, 208-216`

```python
# 后台监听线程：拿 stat().st_mtime_ns 写线程内 mtime
change_mtime = path.stat().st_mtime_ns          # watcher.py:71
self.mtime = max(change_mtime, self.mtime)

# notify() 手动通知：同样拿 stat().st_mtime_ns 写 last_notified
change_mtime = Path(path).stat().st_mtime_ns    # watcher.py:127
self.last_notified = max(self.last_notified, change_mtime)

# check() 比对：严格的 > 比较
latest_mtime = max(self._get_latest_mtime(), self.last_notified)
has_higher_mtime = latest_mtime > self.last_checked   # 注意是 >，不是 >=
```

三个关键字段的单位全是 **int 纳秒**：
| 字段 | 更新方 | 含义 |
|------|--------|------|
| `_WatchfilesThread.mtime` | 后台线程 via `stat().st_mtime_ns` | 监听到事件时的文件时间戳最大值 |
| `last_notified` | 代码主动调用 `notify()` via `stat().st_mtime_ns` | 手动通知的变化时间戳 |
| `last_checked` | `check()` 方法返回 True 时写入 | 上次成功触发 reload 的时间戳 |

#### 4.5.2 判定公式

```
latest_mtime = max(文件系统最新 mtime, last_notified)
需要 reload  <=>  latest_mtime  >  last_checked
```

严格的大于比较，而不是大于等于。这意味着：**两次改动拿到同一个时间戳数值，第二次永远通不过判定**。

#### 4.5.3 漏洞复现路径

**场景 A：外部编辑器连续两次保存（不经过 Fava API）**

**关键代码路径**：`watcher.py:59-77`（`_WatchfilesThread.run`）

```
时刻 Tns（纳秒时间戳 X）：
  1. 编辑器第 1 次写入 → 文件 mtime_ns = X
     → inotify/fsevents 触发 watch() 回调
     → change_mtime = X → self.mtime = max(0, X) = X

  2. Fava 下一次请求触发 ledger.changed()
     → check(): latest_mtime = X, last_checked = 0, X > 0 → True
     → load_file()，缓存失效 ✓
     → last_checked 推进到 X

  3. 同一文件系统时间粒度内，编辑器第 2 次写入
     → 文件 mtime_ns 仍为 X（时间戳没前进）
     → inotify/fsevents 事件照常触发
     → 但 change_mtime = X → self.mtime = max(X, X) = X（没变！）

  4. Fava 再下一次请求触发 ledger.changed()
     → check(): latest_mtime = X, last_checked = X
     → X > X 为 False → ❌ 不触发 reload
     → 缓存一直停留在第 1 次改动后的数据
```

**漏洞成立的前提**：两次写入落在文件系统时间戳的同一精度内。
- macOS APFS：纳秒精度，理论窗口极小（< 1ns），实际极难触发
- Linux ext4：通常支持纳秒，但某些虚拟化层可能降级
- 老旧/网络文件系统：可能只有秒级或毫秒级，1s 窗口内完全可能

**场景 B：Fava 内部操作连续调用 notify()**

**关键代码路径**：`watcher.py:124-130`

```python
def notify(self, path: Path) -> None:
    try:
        change_mtime = Path(path).stat().st_mtime_ns  # ← 每次都重新读文件
    except FileNotFoundError:
        change_mtime = max(self.last_notified, self.last_checked) + 1
    self.last_notified = max(self.last_notified, change_mtime)
```

连续两次调用 `notify()`（如 `insert_entries` 批量插入多条）：
```
第 1 次 notify:  stat → X  → last_notified = max(0, X) = X
第 2 次 notify:  stat → X  → last_notified = max(X, X) = X（不变）
```

`check()` 中 `last_notified` 没前进，依赖它的分支也不会触发。但在 Fava 内部操作的实际代码中，`set_source` 和 `insert_entries` 场景有不同的保护：

**关键代码位置**：`src/fava/core/file.py:141-170, 239-261`

```python
# set_source：直接显式调用 load_file()，不依赖 check()
self.ledger.watcher.notify(path)
self.ledger.load_file()   # ← 绕过了 check()，不会漏

# insert_entries：先调 changed() 保证 last_checked 推进
with self._lock:
    self.ledger.changed()   # ← 写操作前先调用一次，推进 last_checked
    # ... 实际写入 ...
    self.ledger.watcher.notify(path)
```

虽然 `insert_entries` 先 `changed()` 再写入，但如果写入后 `notify()` 的时间戳没有前进，**后续的请求**仍然不会知道有新改动发生，直到文件系统时间戳下一次跳变。

#### 4.5.4 代码中的补救通道

**关键代码位置**：`watcher.py:128-129`

```python
except FileNotFoundError:
    change_mtime = max(self.last_notified, self.last_checked) + 1
```

只有当文件不存在时（创建/删除场景），代码才会**主动 +1 构造一个单调递增的时间戳**，规避了时间戳不动的问题。正常存在的文件没有这个保护。

#### 4.5.5 结论

> **同一时间刻度内连改两次，第二次改动确实会被 `>` 比较漏掉，缓存会停留在第一次改动后的数据。**
>
> 但这是一个窄窗口问题：现代文件系统（APFS/ext4）均支持纳秒级时间戳，只在老旧/网络文件系统或极端高并发写入场景下才会实际触发。
>
> Fava 只对 `FileNotFoundError` 做了 `+1` 兜底，正常文件修改路径没有类似的版本号或单调计数器机制。

---

### 4.6 薄弱边界 2：查询执行中途账本被改写的一致性

#### 4.6.1 前置结论：`get_query` **不做** `changed()` 检测

**关键代码位置**：`src/fava/json_api.py:316-320` vs 其他端点

```python
# get_query 端点 —— 注意没有 g.ledger.changed()
@api_endpoint
def get_query(query_string: str) -> QueryResultTable | QueryResultText:
    return g.ledger.query_shell.execute_query_serialised(
        g.filtered.entries_with_all_prices, query_string
    )

# 对比 get_journal 端点 —— 有 changed()
@api_endpoint
def get_journal() -> Sequence[Directive]:
    g.ledger.changed()   # ← 显式调用
    return [serialise(e) for e in g.filtered.entries]
```

这意味着：查询请求进入时，**不会**主动触发文件检测和 reload。
如果请求到达时文件已经变了但还没任何其他端点触发 `changed()`，查询仍然在旧数据上执行。

#### 4.6.2 过滤数据的定格时机

整条查询链路按顺序会访问以下数据，每一项的"定格"时机不同：

**阶段 1：`g.filtered` 首次访问 —— 请求内首次定格**

**关键代码位置**：`src/fava/_ctx_globals_class.py:47-55`

```python
@cached_property
def filtered(self) -> FilteredLedger:
    args = request.args
    return self.ledger.get_filtered(
        account=args.get("account", ""),
        filter=args.get("filter", ""),
        time=args.get("time", ""),
    )
```

- `@cached_property` 在 Flask 请求上下文 `g` 上
- 同一次请求里第一次访问 `g.filtered` 时才计算一次
- 之后同一请求无论访问多少次，返回同一个 `FilteredLedger` 对象
- 这一层的对象引用在**首次访问瞬间被冻结**

**阶段 2：`FilteredLedger.__init__` —— entries 列表引用定格**

**关键代码位置**：`src/fava/core/__init__.py:119-155`

```python
def __init__(self, ledger, *, account=None, filter=None, time=None):
    entries = ledger.all_entries      # ← 读取 ledger.all_entries 的引用
    if account:
        entries = AccountFilter(account).apply(entries)  # 产生新 list
    ...
    self.entries = entries            # ← 保存到实例属性
```

`ledger.all_entries` 是一个**列表对象的引用**。`load_file()` 执行时会**重新绑定属性**：

```python
# load_file() 中
self.all_entries, ... = load_uncached(...)   # 重新赋值，不是原地修改
```

Python 的属性重绑定不会修改旧列表对象本身。所以：
- 如果 `FilteredLedger` 在 `load_file()` **之前**创建：`self.entries` 指向旧列表，不会随 `load_file()` 改变
- 如果 `FilteredLedger` 在 `load_file()` **之后**创建：`self.entries` 指向新列表

**阶段 3：`entries_with_all_prices` 首次访问 —— 半冻结状态**

**关键代码位置**：`src/fava/core/__init__.py:181-186`

```python
@cached_property
def entries_with_all_prices(self) -> Sequence[Directive]:
    entries = [*self.entries, *self.ledger.all_entries_by_type.Price]
    #                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    #                                    这里重新读取 ledger 上的属性！
    entries.sort(key=_incomplete_sortkey)
    return entries
```

⚠️ **这里出现了第一个不一致点**：
- `self.entries`：`FilteredLedger` 构造时定格的过滤结果
- `self.ledger.all_entries_by_type.Price`：**每次访问时实时读取** `self.ledger` 上当前的值

场景：
```
请求 R 开始，get_filtered 命中缓存 → 旧 FilteredLedger 实例
  → self.entries = 过滤后的旧 entries ✓
中途：另一线程执行 set_source → load_file()
  → ledger.all_entries_by_type = 新的分组
  → ledger.prices = 新的价格图
请求 R 继续，首次访问 entries_with_all_prices：
  → [*旧 self.entries, *新 ledger.all_entries_by_type.Price]
  → ❌ 混合了两个版本的数据：过滤结果是旧版，价格是新版
```

但是，`@cached_property` 一旦计算过就会被缓存，所以：
- 如果 `entries_with_all_prices` 在 `load_file()` **之前**已经被访问过：后续拿到的是缓存结果，**整体一致**（但都旧）
- 如果 `entries_with_all_prices` 在 `load_file()` **之后**才首次访问：**出现跨版本混合**

**阶段 4：`FavaBQLShell.run()` 调用 beanquery —— 彻底冻结**

**关键代码位置**：`src/fava/core/query_shell.py:89-108`

```python
def run(self, entries, query):
    self.context = connect(
        "beancount:",
        entries=entries,          # ← 参数传入 entries_with_all_prices
        errors=self.ledger.errors,    # ← 实时读取
        options=self.ledger.options,  # ← 实时读取
    )
    result = self.onecmd(query)
    ...
```

- `entries` 参数：`entries_with_all_prices` 的对象引用，传入 beanquery 后由 `connect()` 内部保存
- beanquery 后续解析执行时，所有遍历都在这个传入对象上进行，**不会再回到 ledger 读取**
- 但 `errors` 和 `options` 是调用瞬间从 `self.ledger` 读取，和 `entries` 可能不是同一次加载的产物

**阶段 5：`_serialise()` 结果序列化**

**关键代码位置**：`src/fava/core/query_shell.py:242-253`

```python
def _serialise(cursor: Cursor) -> QueryResultTable:
    dtypes = [COLUMNS.get(c.datatype, ObjectColumn)(c.name) for c in cursor.description]
    mappers = [d.serialise for d in dtypes]
    mapped_rows = [
        tuple(mapper(row[i]) for i, mapper in enumerate(mappers))
        for row in cursor       # 遍历 cursor，cursor 已在 beanquery 内部持有数据
    ]
```

遍历的是 `cursor`（beanquery 内部持有），不再访问 ledger，**不会再引入新的不一致**。

#### 4.6.3 最坏场景下的完整时序

```
线程 A（查询请求）                         线程 B（另一个端点/写入请求）
    |                                          |
    |  1. 首次访问 g.filtered                  |
    |     命中 get_filtered LRU 缓存           |
    |     → 旧 FilteredLedger 实例             |
    |     self.entries = [旧过滤结果]          |
    |                                          |
    |  2. 还没访问 entries_with_all_prices     |
    |                                          |  3. 用户保存文件：set_source()
    |                                          |     → ledger.load_file()
    |                                          |     → ledger.all_entries = 新列表
    |                                          |     → ledger.all_entries_by_type = 新分组
    |                                          |     → ledger.options = 新选项
    |                                          |     → get_filtered.cache_clear()
    |                                          |
    |  4. 访问 g.filtered.entries_with_all_prices
    |     (cached_property 首次计算)           |
    |     → [*旧 self.entries,                 |
    |        *新 ledger.all_entries_by_type.Price]  ❌ 混合版本
    |                                          |
    |  5. query_shell.execute_query_serialised()
    |     connect(entries=混合列表,             |
    |             errors=新 errors,             |  ❌ 来自新版本
    |             options=新 options)          |  ❌ 来自新版本
    |                                          |
    |  6. beanquery 执行 & 序列化              |
    |     → 在混合列表上计算，引用新选项        |
```

#### 4.6.4 结论

> **查询执行中途账本被改写，不保证单次请求内看到一致性快照**。
>
> 具体表现由"首次访问的时机"决定：
>
> | 访问时机 / 数据项 | `self.entries`（过滤结果） | `all_entries_by_type.Price`（价格） | `errors` / `options`（配置） |
> |------------------|--------------------------|-------------------------------------|------------------------------|
> | 在 load_file **之前** 首次计算 entries_with_all_prices | ✅ 旧版一致 | ✅ 旧版一致 | ⚠️ connect() 时读取，可能是新版 |
> | 在 load_file **之后** 首次计算 entries_with_all_prices | ✅ 旧版 | ❌ 新版（不一致） | ❌ 新版（不一致） |
>
> **关键观察**：
> 1. 纯数据层面的不一致几乎不会造成报错，但查询结果可能"部分旧、部分新"，语义上不直观
> 2. 最核心的 entries 主体（过滤后的交易列表）在 `FilteredLedger.__init__` 时就已锁定，**大部分场景下不会出现半条交易半条新交易的极端混乱**
> 3. 风险最大的是价格条目：`entries_with_all_prices` 会拼接旧过滤结果 + 新价格条目 → 可能用旧账本上下文查询新价格
> 4. `get_query` 端点没有前置 `changed()` 调用 → 查询请求自身不承担检测职责，靠其他端点的 `changed()` 间接推进
> 5. 没有任何锁/事务机制保证 `ledger.all_entries`、`ledger.all_entries_by_type`、`ledger.options` 是原子地一起被观测到
>
> 但实践中这是**低概率**事件：需要查询恰好落在另一个线程执行 `load_file()` 的毫秒级窗口内。且因为是只读查询，最坏结果是返回一组不一致但不崩溃的数据，不会损坏账本文件。

---

### 4.7 失效边界总表（已补充两个薄弱边界）

| 操作/场景 | 后端缓存失效 | 前端触发机制 | 备注 |
|----------|-------------|-------------|------|
| 文件被外部修改 | ✅ `watcher.check()` 检测到变化 → `load_file()` | 下一次 API 请求返回新 `mtime` | 时间戳粒度内二次改动会漏（见 4.5） |
| Fava 内保存文件 | ✅ 立即调用 `load_file()` | `router.reload()` 或下次请求 | `set_source` 直接 load_file，其他走 notify |
| 全局过滤器变化 | ❌ 不失效（不同的缓存键） | 前端 `rerun_all_open()` 重新查询 | 新缓存键，创建新 FilteredLedger |
| BQL 语句变化 | ❌ 不影响数据缓存 | 前端发起新的 API 请求 | 只影响 beanquery 执行阶段 |
| 切换账本文件 | ✅ 不同的 `FavaLedger` 实例 | 页面导航 | 完全不同的 Python 对象 |
| 同一纳秒窗口内连改两次 | ❌ `>` 比较 + 时间戳未前进 → 漏检 | 无自动触发 | 仅老旧文件系统可能复现（见 4.5） |
| 查询中途其他线程触发 load_file | ⚠️ 本次查询不失效，下次才会 | 本次返回值已在路上 | 可能出现跨版本混合（见 4.6） |

---

## 五、完整链路时序图

```
前端 (Query.svelte)                          后端 (json_api.py)
       |                                           |
1. 用户输入 BQL + 过滤器                           |
       |                                           |
2. submit() 调用 get_query({ query_string, ...$filter_params })
       |                                           |
       | ------ HTTP GET -------------------------> |
       |        /api/query?query_string=...&time=...
       |                                           |
       |                                     3. g.filtered 构建
       |                                        (可能命中 LRU 缓存)
       |                                           |
       |                                     4. g.filtered.entries_with_all_prices
       |                                        (可能命中 cached_property)
       |                                           |
       |                                     5. query_shell.execute_query_serialised()
       |                                        ├─ connect(entries, errors, options)
       |                                        ├─ onecmd(query) → beanquery 解析执行
       |                                        └─ _serialise(cursor)
       |                                           |
       | <------ JSON Response ------------------- |
       |        { data: ..., mtime: "123456789" }
       |                                           |
6. 更新 results[query]                            |
   更新 ledger_mtime                               |
       |                                           |
```

---

## 六、关键优化点与潜在问题

### 6.1 设计优点

1. **分层缓存**：LRU + cached_property + 请求上下文，多级缓存减少重复计算
2. **过滤下推**：先过滤 entries 再执行 BQL，减少查询处理的数据量
3. **主动通知**：文件写入后立即 `notify()`，避免轮询延迟
4. **响应式设计**：前端 `filter_params` 与 URL 同步，变化自动触发重查

### 6.2 注意事项

1. **BQL 与 FQL 过滤器的关系**：
   - 全局过滤器（FQL）在 entries 层面先过滤
   - BQL 的 WHERE 子句在过滤后的 entries 上再过滤
   - 两者是 AND 关系，不是 OR 关系

2. **价格条目特殊处理**：
   - `entries_with_all_prices` 会把所有 Price 条目加回来
   - 即使 time filter 排除了某个时间段，价格仍然可用

3. **缓存大小限制**：
   - `get_filtered` 只有 16 个缓存槽位
   - 如果用户频繁切换不同过滤组合，可能导致缓存颠簸

4. **查询结果未缓存**：
   - 相同 BQL + 相同过滤器的重复查询不会缓存结果
   - 每次都会重新执行 beanquery 解析和执行

### 6.3 代码引用速查表

| 模块 | 文件位置 | 关键行 |
|------|---------|--------|
| 前端查询提交 | `frontend/src/reports/query/Query.svelte` | 43-88 |
| 过滤器 store | `frontend/src/stores/filters.ts` | 34-42 |
| API 封装 | `frontend/src/api/index.ts` | 302-305 |
| 后端查询端点 | `src/fava/json_api.py` | 316-320 |
| FilteredLedger | `src/fava/core/__init__.py` | 104-292 |
| get_filtered 缓存 | `src/fava/core/__init__.py` | 388, 443-458 |
| entries_with_all_prices | `src/fava/core/__init__.py` | 181-186 |
| QueryShell | `src/fava/core/query_shell.py` | 160-240 |
| FavaBQLShell | `src/fava/core/query_shell.py` | 79-157 |
| load_file 失效 | `src/fava/core/__init__.py` | 407-441 |
| changed() 检测 | `src/fava/core/__init__.py` | 511-524 |
| Watcher 基类 | `src/fava/core/watcher.py` | 93-134 |
| WatchfilesWatcher | `src/fava/core/watcher.py` | 137-186 |
| _WatchfilesThread.run | `src/fava/core/watcher.py` | 55-78 |
| 请求前检测 | `src/fava/application.py` | 261-271 |
| 请求上下文 g.filtered | `src/fava/_ctx_globals_class.py` | 47-54 |
| 文件写入 notify | `src/fava/core/file.py` | 141-261 |

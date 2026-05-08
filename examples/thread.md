Thread 的写法很简单：每条推文之间用一行 `---` 分隔。空白行和段首尾空格会被自动清理。

---

每条 ≤ 280 字（非 Premium 上限）。整个 thread ≤ 25 条。`meti validate` 会按这两条规则逐条 lint，超长会以 `TWEET_TOO_LONG` / `THREAD_TOO_LONG` 报错。

---

执行流程：浏览器流会打开 `x.com/compose/post`，逐条填进去，**停在「Post all」按钮前**——你自己看一遍再发。X 没有 thread 草稿概念，停在 modal 前是最近似的草稿。

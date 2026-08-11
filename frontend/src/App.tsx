import { FormEvent, useEffect, useMemo, useState } from "react";

type Tab = "inbox" | "digest" | "history" | "settings";
type Job = { id: string; status: string; stage: string; progress: number; error?: string; new_count: number; duplicate_count: number; digest_date: string };
type DigestItem = { id: number; section: "must_read" | "interesting"; rank: number; category: string; conclusion: string; why_read: string; context_summary: string; source_excerpt: string; source_time: string; source_author: string; links: string[]; credibility: "verified" | "unverified" | "disputed" };
type Digest = { digest_date: string; generated_at: string; stats: { total: number; must_read: number; interesting: number; categories: Record<string, number>; model_mode?: string }; items: DigestItem[] };
type HistoryEntry = { digest_date: string; generated_at: string; stats: Digest["stats"] };
type Settings = { api_base_url: string; screening_model: string; final_model: string; monthly_budget_cny: number; retention_days: number; input_price_cny_per_million: number; output_price_cny_per_million: number; api_key_configured: boolean; monthly_spend_cny: number; allow_local_fallback: boolean };

const today = new Date().toLocaleDateString("en-CA");

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...options, headers: { "Content-Type": "application/json", ...options?.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败（${response.status}）`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

function Empty({ children }: { children: string }) {
  return <div className="empty"><span>○</span><p>{children}</p></div>;
}

function DigestCard({ item }: { item: DigestItem }) {
  const credibility = { verified: "已核验", unverified: "仅群友说法", disputed: "存在争议" }[item.credibility];
  const [feedbackValue, setFeedbackValue] = useState<"useful" | "not_useful" | null>(null);
  const [feedbackStatus, setFeedbackStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const sendFeedback = async (value: "useful" | "not_useful") => {
    setFeedbackStatus("saving");
    try {
      await api("/api/feedback", { method: "POST", body: JSON.stringify({ digest_item_id: item.id, value }) });
      setFeedbackValue(value);
      setFeedbackStatus("saved");
    } catch {
      setFeedbackStatus("error");
    }
  };
  return (
    <article className="digest-card">
      <div className="card-top"><span className="category">{item.category}</span><span className={`credibility ${item.credibility}`}>{credibility}</span></div>
      <h3>{item.conclusion}</h3>
      <p className="why"><strong>为什么值得看</strong>{item.why_read}</p>
      <p>{item.context_summary}</p>
      <blockquote>{item.source_excerpt}</blockquote>
      <div className="source"><span>{item.source_author}</span><span>{item.source_time}</span><span>回群定位：搜索“{item.source_excerpt.slice(0, 24)}”</span></div>
      {item.links.length > 0 && <div className="links">{item.links.map((link) => <a key={link} href={link} target="_blank" rel="noreferrer">查看相关链接 ↗</a>)}</div>}
      <div className="feedback">
        <span className={`feedback-status ${feedbackStatus}`} aria-live="polite">
          {feedbackStatus === "saving" ? "正在保存…" : feedbackStatus === "saved" ? "已记录，感谢反馈" : feedbackStatus === "error" ? "保存失败，请重试" : "可选反馈"}
        </span>
        <button type="button" className={feedbackValue === "useful" ? "selected" : ""} disabled={feedbackStatus === "saving"} aria-pressed={feedbackValue === "useful"} onClick={() => sendFeedback("useful")} aria-label="有用">有用</button>
        <button type="button" className={feedbackValue === "not_useful" ? "selected" : ""} disabled={feedbackStatus === "saving"} aria-pressed={feedbackValue === "not_useful"} onClick={() => sendFeedback("not_useful")} aria-label="没用">没用</button>
      </div>
    </article>
  );
}

function DigestView({ digest }: { digest: Digest | null }) {
  if (!digest) return <Empty>这一天还没有简报。去“今日收件箱”粘贴群聊记录吧。</Empty>;
  const must = digest.items.filter((item) => item.section === "must_read");
  const interesting = digest.items.filter((item) => item.section === "interesting");
  return <div className="digest-view">
    <div className="digest-heading">
      <div><p className="eyebrow">{digest.digest_date}</p><h2>每日简报</h2></div>
      <div className="summary-count"><strong>{digest.stats.total}</strong><span>条精选</span></div>
    </div>
    {digest.stats.model_mode === "local_fallback" && <div className="notice">当前未配置 API Key，本简报由本地规则生成，仅用于跑通流程。配置模型后可获得正式摘要。</div>}
    <div className="topic-row">{Object.entries(digest.stats.categories || {}).map(([name, count]) => <span key={name}>{name} · {count}</span>)}</div>
    <section><div className="section-title"><h2>必看</h2><span>最多 3 条</span></div>{must.length ? must.map((item) => <DigestCard key={item.id} item={item} />) : <Empty>今天没有必看内容。</Empty>}</section>
    <section><div className="section-title"><h2>可能感兴趣</h2><span>最多 7 条</span></div>{interesting.length ? interesting.map((item) => <DigestCard key={item.id} item={item} />) : <Empty>今天没有更多值得打扰你的内容。</Empty>}</section>
  </div>;
}

export default function App() {
  const [tab, setTab] = useState<Tab>("inbox");
  const [date, setDate] = useState(today);
  const [text, setText] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [digest, setDigest] = useState<Digest | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [query, setQuery] = useState("");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadDigest = async (targetDate = date) => {
    try { setDigest(await api<Digest>(`/api/digests/${targetDate}`)); } catch { setDigest(null); }
  };
  const loadHistory = async (search = query) => setHistory(await api<HistoryEntry[]>(`/api/history?q=${encodeURIComponent(search)}`));
  const loadSettings = async () => setSettings(await api<Settings>("/api/settings"));

  useEffect(() => { loadDigest(date); }, [date]);
  useEffect(() => { if (tab === "history") loadHistory(); if (tab === "settings") loadSettings(); }, [tab]);
  useEffect(() => {
    if (!job || ["completed", "failed"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      const updated = await api<Job>(`/api/jobs/${job.id}`).catch(() => null);
      if (!updated) return;
      setJob(updated);
      if (updated.status === "completed") { setText(""); await loadDigest(updated.digest_date); setTab("digest"); }
      if (updated.status === "failed") setError(updated.error || "处理失败");
    }, 700);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  const charCount = useMemo(() => text.length.toLocaleString("zh-CN"), [text]);
  const generate = async (event: FormEvent) => {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      const result = await api<{ job_id: string; new_count: number; duplicate_count: number }>("/api/jobs", { method: "POST", body: JSON.stringify({ digest_date: date, text }) });
      setJob({ id: result.job_id, status: "queued", stage: "等待处理", progress: 0, new_count: result.new_count, duplicate_count: result.duplicate_count, digest_date: date });
      if (result.new_count === 0) { setText(""); await loadDigest(date); setTab("digest"); }
    } catch (exc) { setError(exc instanceof Error ? exc.message : "提交失败"); }
    finally { setBusy(false); }
  };

  const saveSettings = async (event: FormEvent) => {
    event.preventDefault(); if (!settings) return; setBusy(true); setError("");
    try { setSettings(await api<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(settings) })); }
    catch (exc) { setError(exc instanceof Error ? exc.message : "保存失败"); }
    finally { setBusy(false); }
  };

  return <div className="app-shell">
    <aside>
      <div className="brand"><div className="brand-mark">Q</div><div><strong>群聊简报</strong><small>LOCAL DIGEST</small></div></div>
      <nav>
        {(["inbox", "digest", "history", "settings"] as Tab[]).map((name) => <button key={name} className={tab === name ? "active" : ""} onClick={() => setTab(name)}><span>{({ inbox: "＋", digest: "◇", history: "◷", settings: "⚙" })[name]}</span>{({ inbox: "今日收件箱", digest: "今日简报", history: "历史简报", settings: "模型与设置" })[name]}</button>)}
      </nav>
      <div className="privacy"><span>●</span><div><strong>只在本机运行</strong><p>原始文本成功生成后删除</p></div></div>
    </aside>
    <main>
      <header><div><p className="eyebrow">QQ DAILY DIGEST</p><h1>{({ inbox: "今日收件箱", digest: "今日简报", history: "历史简报", settings: "模型与设置" })[tab]}</h1></div><label className="date-control">简报日期<input type="date" value={date} onChange={(event) => setDate(event.target.value)} /></label></header>
      {error && <div className="error"><span>!</span>{error}<button onClick={() => setError("")}>×</button></div>}
      {tab === "inbox" && <div className="inbox-layout">
        <section className="intro"><p className="eyebrow">STEP 01 · PASTE</p><h2>把群聊里的噪音，<br />变成今天真正值得看的事。</h2><p>复制当天 QQ 群聊记录，直接粘贴到右侧。同一天可多次追加，系统会自动去重，只处理新内容。</p><ul><li>最多 3 条必看 + 7 条可能感兴趣</li><li>只打开初筛候选中的公开链接</li><li>图片、文件和视频仅提示回群查看</li></ul></section>
        <form className="paste-card" onSubmit={generate}><div className="paste-label"><strong>粘贴群聊记录</strong><span>{charCount} 字符</span></div><textarea value={text} onChange={(event) => setText(event.target.value)} placeholder={'例如：\n张三 09:31\n发现一个很实用的开源工具 https://...\n\n李四 09:35\n这里有个坑，报错是...'} /><div className="paste-footer"><p>内容仅在生成期间保留。聊天和网页中的指令不会被执行。</p><button disabled={busy || !text.trim()}>{busy ? "正在提交…" : "开始生成简报 →"}</button></div></form>
        {job && <section className="progress-card"><div><strong>{job.stage}</strong><span>{job.progress}%</span></div><div className="progress-track"><i style={{ width: `${job.progress}%` }} /></div><p>新增 {job.new_count} 条，跳过重复 {job.duplicate_count} 条</p></section>}
      </div>}
      {tab === "digest" && <DigestView digest={digest} />}
      {tab === "history" && <div className="history-view"><form onSubmit={(e) => { e.preventDefault(); loadHistory(); }} className="search"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索结论、摘要或主题…" /><button>搜索</button></form>{history.length ? <div className="history-list">{history.map((entry) => <button key={entry.digest_date} onClick={async () => { setDate(entry.digest_date); await loadDigest(entry.digest_date); setTab("digest"); }}><time>{entry.digest_date}</time><strong>{entry.stats.total} 条精选</strong><span>{Object.keys(entry.stats.categories || {}).join(" · ") || "无入选内容"}</span><i>查看 →</i></button>)}</div> : <Empty>还没有匹配的历史简报。</Empty>}</div>}
      {tab === "settings" && settings && <form className="settings-form" onSubmit={saveSettings}>
        <div className="settings-status"><div><span className={settings.api_key_configured ? "ok-dot" : "warn-dot"} />API Key {settings.api_key_configured ? "已从 .env 读取" : "未配置（当前使用本地回退）"}</div><div>本月估算 <strong>¥{settings.monthly_spend_cny.toFixed(4)}</strong> / ¥{settings.monthly_budget_cny.toFixed(2)}</div></div>
        <section><div><h2>模型接口</h2><p>兼容 OpenAI Chat Completions API。API Key 只通过本机 .env 配置，界面不会读取或展示它。</p></div><div className="field-grid"><label className="wide">API Base URL<input value={settings.api_base_url} onChange={(e) => setSettings({ ...settings, api_base_url: e.target.value })} /></label><label>初筛模型<input value={settings.screening_model} onChange={(e) => setSettings({ ...settings, screening_model: e.target.value })} /></label><label>最终模型<input value={settings.final_model} onChange={(e) => setSettings({ ...settings, final_model: e.target.value })} /></label></div></section>
        <section><div><h2>预算与保留</h2><p>达到月度预算后停止云端调用。价格留空或为 0 时无法准确估算费用。</p></div><div className="field-grid"><label>月度上限（元）<input type="number" step="0.01" value={settings.monthly_budget_cny} onChange={(e) => setSettings({ ...settings, monthly_budget_cny: +e.target.value })} /></label><label>历史保留（天）<input type="number" value={settings.retention_days} onChange={(e) => setSettings({ ...settings, retention_days: +e.target.value })} /></label><label>输入价格（元/百万 token）<input type="number" step="0.01" value={settings.input_price_cny_per_million} onChange={(e) => setSettings({ ...settings, input_price_cny_per_million: +e.target.value })} /></label><label>输出价格（元/百万 token）<input type="number" step="0.01" value={settings.output_price_cny_per_million} onChange={(e) => setSettings({ ...settings, output_price_cny_per_million: +e.target.value })} /></label></div></section>
        <button className="save-button" disabled={busy}>{busy ? "保存中…" : "保存设置"}</button>
      </form>}
    </main>
  </div>;
}

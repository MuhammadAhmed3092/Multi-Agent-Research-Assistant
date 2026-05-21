import { useState, useRef, useEffect } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

const AGENT_META = {
  orchestrator:  { icon: "🧠", label: "Orchestrator",   color: "#7F77DD" },
  web_search:    { icon: "🔍", label: "Web Search",     color: "#378ADD" },
  pdf_reader:    { icon: "📄", label: "PDF Reader",     color: "#1D9E75" },
  code_executor: { icon: "💻", label: "Code Executor",  color: "#BA7517" },
  summarizer:    { icon: "✍️",  label: "Summarizer",    color: "#D85A30" },
};

function QuotaBadge({ used, limit, resetAt }) {
  const remaining = Math.max(0, limit - used);
  const pct       = (used / limit) * 100;
  const color     = remaining === 0 ? "#e53" : remaining <= 2 ? "#c80" : "#1D9E75";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10,
                  padding: "8px 14px", background: "#f9f9f9",
                  border: "1px solid #eee", borderRadius: 8, fontSize: 13 }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ color: "#555" }}>Daily prompts</span>
          <span style={{ fontWeight: 600, color }}>
            {remaining} / {limit} left
          </span>
        </div>
        <div style={{ height: 4, background: "#e8e8e8", borderRadius: 2 }}>
          <div style={{ height: 4, width: `${pct}%`, background: color,
                        borderRadius: 2, transition: "width 0.4s" }} />
        </div>
      </div>
      {remaining === 0 && resetAt && (
        <span style={{ fontSize: 11, color: "#999", whiteSpace: "nowrap" }}>
          resets {new Date(resetAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>
      )}
    </div>
  );
}

export default function App() {
  const [query,     setQuery]     = useState("");
  const [steps,     setSteps]     = useState([]);
  const [sources,   setSources]   = useState([]);
  const [answer,    setAnswer]    = useState("");
  const [status,    setStatus]    = useState("idle");
  const [pdfFile,   setPdfFile]   = useState("");
  const [error,     setError]     = useState("");
  const [quota,     setQuota]     = useState({ used: 0, limit: 6, remaining: 6, reset_at: "" });
  const [exceeded,  setExceeded]  = useState(false);
  const fileRef = useRef();

  useEffect(() => {
    fetch(`${API}/quota`)
      .then(r => r.json())
      .then(d => setQuota({ used: d.prompts_used, limit: d.prompt_limit,
                             remaining: d.prompts_remaining, reset_at: d.quota_reset_at }))
      .catch(() => {});
  }, []);

  async function uploadPdf(file) {
    const form = new FormData();
    form.append("file", file);
    const res  = await fetch(`${API}/upload`, { method: "POST", body: form });
    const data = await res.json();
    setPdfFile(data.saved_as);
  }

  async function runResearch() {
    if (!query.trim() || status === "running") return;
    setSteps([]); setSources([]); setAnswer("");
    setError(""); setExceeded(false); setStatus("running");

    const res = await fetch(`${API}/research`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, pdf_filenames: pdfFile ? [pdfFile] : [] }),
    });

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();

      for (const part of parts) {
        const eLine = part.split("\n").find(l => l.startsWith("event:"));
        const dLine = part.split("\n").find(l => l.startsWith("data:"));
        if (!eLine || !dLine) continue;
        const event = eLine.replace("event:", "").trim();
        const data  = JSON.parse(dLine.replace("data:", "").trim());

        if (event === "start") {
          setQuota({ used: data.prompts_used, limit: data.prompt_limit,
                     remaining: data.prompts_remaining, reset_at: quota.reset_at });
        }
        if (event === "step")    setSteps(s => [...s, data]);
        if (event === "sources") setSources(data.sources);
        if (event === "answer")  setAnswer(data.answer);
        if (event === "done") {
          setStatus("done");
          setQuota(q => ({ ...q, used: data.prompts_used, remaining: data.prompts_remaining }));
        }
        if (event === "error")         { setError(data.message); setStatus("error"); }
        if (event === "quota_exceeded"){ setExceeded(true); setStatus("idle"); }
      }
    }
  }

  return (
    <div style={{ maxWidth: 880, margin: "0 auto", padding: "2rem 1rem",
                  fontFamily: "'Inter', system-ui, sans-serif" }}>

      {/* Header */}
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, color: "#1a1a1a" }}>
          🧠 Multi-Agent Research Assistant
        </h1>
        <p style={{ color: "#777", marginTop: 5, fontSize: 13 }}>
          Groq · LangGraph · DuckDuckGo · Local embeddings — 100% free stack
        </p>
      </div>

      {/* Quota tracker */}
      <div style={{ marginBottom: 16 }}>
        <QuotaBadge used={quota.used} limit={quota.limit} resetAt={quota.reset_at} />
      </div>

      {/* Quota exceeded banner */}
      {exceeded && (
        <div style={{ background: "#fff3f3", border: "1px solid #fcc",
                      borderRadius: 8, padding: "14px 18px", marginBottom: 16 }}>
          <p style={{ margin: 0, fontWeight: 600, color: "#c00", fontSize: 14 }}>
            Daily limit reached
          </p>
          <p style={{ margin: "6px 0 0", color: "#555", fontSize: 13 }}>
            You've used all {quota.limit} free prompts for today.
            Your quota resets every 24 hours.
          </p>
        </div>
      )}

      {/* Input row */}
      <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === "Enter" && runResearch()}
          placeholder="Ask a research question…"
          disabled={status === "running" || exceeded || quota.remaining === 0}
          style={{ flex: 1, padding: "10px 14px", fontSize: 15,
                   border: "1px solid #ddd", borderRadius: 8,
                   outline: "none", color: "#1a1a1a" }}
        />
        <button
          onClick={runResearch}
          disabled={status === "running" || !query.trim() || exceeded || quota.remaining === 0}
          style={{ padding: "10px 22px", fontSize: 14, fontWeight: 600,
                   background: (status === "running" || quota.remaining === 0) ? "#bbb" : "#534AB7",
                   color: "#fff", border: "none", borderRadius: 8,
                   cursor: status === "running" ? "not-allowed" : "pointer" }}>
          {status === "running" ? "Researching…" : "Research ↗"}
        </button>
      </div>

      {/* PDF upload */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: "1.5rem" }}>
        <input ref={fileRef} type="file" accept=".pdf" style={{ display: "none" }}
          onChange={e => e.target.files[0] && uploadPdf(e.target.files[0])} />
        <button onClick={() => fileRef.current.click()}
          style={{ padding: "6px 14px", border: "1px solid #ddd", borderRadius: 6,
                   background: "#fafafa", cursor: "pointer", fontSize: 13 }}>
          📎 Upload PDF
        </button>
        {pdfFile && <span style={{ fontSize: 13, color: "#1D9E75" }}>✓ PDF ready</span>}
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: "#fff0f0", border: "1px solid #fcc", borderRadius: 8,
                      padding: "12px 16px", marginBottom: 16, color: "#c00", fontSize: 14 }}>
          ⚠ {error}
        </div>
      )}

      {/* Agent activity */}
      {steps.length > 0 && (
        <div style={{ background: "#f8f8f8", border: "1px solid #eee",
                      borderRadius: 10, padding: "14px 16px", marginBottom: 20 }}>
          <p style={{ margin: "0 0 10px", fontWeight: 600, fontSize: 13, color: "#333" }}>
            Agent Activity
          </p>
          {steps.map((step, i) => {
            const m = AGENT_META[step.agent] || { icon: "•", label: step.agent, color: "#888" };
            return (
              <div key={i} style={{ display: "flex", gap: 10, marginBottom: 8, fontSize: 13, alignItems: "flex-start" }}>
                <span>{m.icon}</span>
                <div>
                  <span style={{ fontWeight: 600, color: m.color }}>{m.label}</span>
                  <span style={{ color: "#444", marginLeft: 6 }}>{step.action}</span>
                  {step.detail && <span style={{ color: "#999", marginLeft: 6, fontSize: 12 }}>— {step.detail}</span>}
                </div>
              </div>
            );
          })}
          {status === "running" && <p style={{ margin: "8px 0 0", color: "#aaa", fontSize: 12 }}>⏳ Working…</p>}
        </div>
      )}

      {/* Sources grid */}
      {sources.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <p style={{ fontWeight: 600, fontSize: 13, color: "#333", marginBottom: 10 }}>
            Sources ({sources.length})
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px,1fr))", gap: 10 }}>
            {sources.map((s, i) => {
              const m = AGENT_META[s.agent] || {};
              return (
                <div key={i} style={{ background: "#fff", border: "1px solid #e8e8e8",
                                      borderRadius: 8, padding: "10px 14px" }}>
                  <div style={{ fontSize: 11, color: m.color || "#888", fontWeight: 600, marginBottom: 4 }}>
                    {m.icon} {m.label}
                  </div>
                  <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 4 }}>
                    {s.url
                      ? <a href={s.url} target="_blank" rel="noreferrer"
                           style={{ color: "#1a0dab", textDecoration: "none" }}>
                          {s.title.slice(0, 55)}{s.title.length > 55 ? "…" : ""}
                        </a>
                      : <span>{s.title.slice(0, 55)}</span>}
                  </div>
                  <div style={{ fontSize: 12, color: "#666", lineHeight: 1.5 }}>
                    {s.snippet.slice(0, 110)}…
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Final answer */}
      {answer && (
        <div style={{ background: "#fff", border: "1px solid #e0dff8",
                      borderRadius: 10, padding: "20px 24px" }}>
          <p style={{ fontWeight: 700, fontSize: 13, color: "#534AB7", marginBottom: 14 }}>
            ✍️ Research Answer
          </p>
          <div style={{ fontSize: 15, lineHeight: 1.8, color: "#1a1a1a",
                        whiteSpace: "pre-wrap" }}>
            {answer}
          </div>
        </div>
      )}
    </div>
  );
}

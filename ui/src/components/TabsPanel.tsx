import { useEffect, useRef, useState } from "react";

/* ---- 曲谱面板（共享组件，S3）----
   缩略图墙 + 上传 + 删除 + 点击看大图（lightbox）。
   文件路径约定：tab_files 存相对 data/ 的路径（tabs/歌名/文件），
   访问 URL = "/" + 路径（后端把 data/tabs 挂到 /tabs 静态路由）。
   使用方：歌曲库展开面板、学歌卡片。直播速查窗是独立只读实现（QuickView）。 */

const isPdf = (rel: string) => rel.toLowerCase().endsWith(".pdf");
const fileName = (rel: string) => rel.split("/").pop() ?? rel;

export default function TabsPanel({ title, tabFiles, dark, onChanged }: {
  title: string;
  tabFiles: string[];
  dark: boolean;
  onChanged: (files: string[]) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewer, setViewer] = useState<string | null>(null);  // lightbox 中的文件
  const inputRef = useRef<HTMLInputElement>(null);

  const upload = async (file: File) => {
    setBusy(true); setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch(`/api/songs/${encodeURIComponent(title)}/tabs`, { method: "POST", body: fd });
      if (!r.ok) throw new Error(await r.text());
      const d = await r.json();
      onChanged(d.tab_files);
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const remove = async (rel: string) => {
    setBusy(true); setError(null);
    try {
      const r = await fetch(`/api/songs/${encodeURIComponent(title)}/tabs?file=${encodeURIComponent(rel)}`,
        { method: "DELETE" });
      if (!r.ok) throw new Error(await r.text());
      const d = await r.json();
      onChanged(d.tab_files);
      if (viewer === rel) setViewer(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally { setBusy(false); }
  };

  /* lightbox：Esc / 点击遮罩关闭 */
  useEffect(() => {
    if (!viewer) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setViewer(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [viewer]);

  const muted = dark ? "text-zinc-500" : "text-muted-foreground";
  const cellBg = dark ? "bg-zinc-800/80 hover:bg-zinc-800" : "bg-muted/60 hover:bg-muted";

  return (
    <div>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        {tabFiles.map(rel => (
          <div key={rel} className="group relative">
            <button onClick={() => setViewer(rel)} title={fileName(rel)}
              className={`block w-16 h-20 rounded-lg overflow-hidden transition-colors cursor-pointer ${cellBg}`}>
              {isPdf(rel)
                ? <span className={`flex flex-col items-center justify-center h-full gap-1 text-[10px] ${muted}`}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>
                    </svg>PDF</span>
                : <img src={`/${rel}`} alt={fileName(rel)} loading="lazy"
                    className="w-full h-full object-cover bg-white" />}
            </button>
            <button onClick={() => remove(rel)} title="删除这张谱"
              className="absolute -top-1.5 -right-1.5 hidden group-hover:flex w-5 h-5 items-center justify-center
                rounded-full bg-red-500 text-white text-[11px] leading-none cursor-pointer shadow">×</button>
          </div>
        ))}
        <button onClick={() => inputRef.current?.click()} disabled={busy}
          className={`w-16 h-20 rounded-lg border border-dashed flex flex-col items-center justify-center gap-1
            text-[11px] transition-colors cursor-pointer disabled:opacity-50
            ${dark ? "border-zinc-700 text-zinc-500 hover:text-zinc-300 hover:border-zinc-500"
                   : "border-border text-muted-foreground hover:text-foreground hover:border-primary/50"}`}>
          <span className="text-base leading-none">{busy ? "…" : "＋"}</span>
          {busy ? "上传中" : "传谱子"}
        </button>
        <input ref={inputRef} type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.pdf" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) upload(f); }} />
      </div>
      {error && <p className="mt-1.5 text-[11px] text-red-500">{error}</p>}
      {tabFiles.length === 0 && !error && (
        <p className={`mt-1.5 text-[11px] ${muted}`}>还没有曲谱附件，可传图片或 PDF</p>
      )}

      {/* ===== 大图 lightbox ===== */}
      {viewer && (
        <div onClick={() => setViewer(null)}
          className="fixed inset-0 z-50 bg-black/85 flex items-center justify-center p-8 cursor-zoom-out">
          {isPdf(viewer)
            ? <iframe src={`/${viewer}`} title={fileName(viewer)}
                className="w-full h-full max-w-4xl rounded-lg bg-white" />
            : <img src={`/${viewer}`} alt={fileName(viewer)}
                className="max-w-full max-h-full rounded-lg shadow-2xl object-contain bg-white p-3" />}
        </div>
      )}
    </div>
  );
}

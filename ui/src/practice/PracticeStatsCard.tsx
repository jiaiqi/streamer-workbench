/// P4 R4: 学歌练习打卡统计卡片区。
///
/// 在 LearningView 顶部显示:
///   连续 N 天 / 累计 X 分钟 / 本月 X 次 / TOP5 歌曲
/// + 一个快速打卡按钮 (今日练习 30 分钟)。
///
/// 数据从 /api/practice/stats 拉取; 冷启动时 (无打卡) 显示引导文案。
import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { toRequestFailure, type RequestFailure } from "../async/requestState";

interface PracticeStats {
  total_minutes: number;
  total_sessions: number;
  current_streak_days: number;
  longest_streak_days: number;
  last_30_days: number;
  songs_practiced: number;
  top_practiced: Array<{ title: string; sessions: number; minutes: number }>;
  month_current_minutes: number;
  month_current_sessions: number;
  months: Array<{ month: string; total_minutes: number }>;
}

interface PracticeStatsCardProps {
  dark: boolean;
  onLogClick: () => void;
}

function fmtMinutes(m: number): string {
  if (m < 60) return `${m} 分钟`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  return rest > 0 ? `${h} 小时 ${rest} 分钟` : `${h} 小时`;
}

export default function PracticeStatsCard({ dark, onLogClick }: PracticeStatsCardProps) {
  const [stats, setStats] = useState<PracticeStats | null>(null);
  const [error, setError] = useState<RequestFailure | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const data = await apiRequest<PracticeStats>("/api/practice/stats");
        if (!active) return;
        setStats(data);
        setError(null);
      } catch (reason) {
        if (!active) return;
        setError(toRequestFailure(reason, "加载练习统计失败"));
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, []);

  if (loading) return null;

  // 冷启动: 无任何打卡
  const empty = !stats || stats.total_sessions === 0;

  return (
    <section aria-label="练习统计" className={`mb-6 rounded-2xl p-5 ${dark ? "bg-zinc-800/70 border border-zinc-700/60" : "bg-card border border-border"}`}
      style={{ boxShadow: "var(--shadow-sm)" }}>
      {/* 标题行 */}
      <div className="flex items-center justify-between mb-4">
        <h2 className={`font-serif text-[16px] font-semibold ${dark ? "text-zinc-100" : "text-foreground"}`}>
          {empty ? "开始你的第一次练习" : "练习动态"}
        </h2>
        <button onClick={onLogClick}
          className="rounded-xl px-4 py-1.5 text-xs font-medium text-white transition-all active:scale-95"
          style={{ background: "linear-gradient(150deg, var(--color-primary), var(--color-primary-strong))" }}>
          {empty ? "记录一次练习" : "打卡"}
        </button>
      </div>

      {error ? (
        <p className="text-xs text-red-500" role="alert">{error.message}</p>
      ) : empty ? (
        <p className="text-sm text-muted-foreground leading-relaxed">
          还没有练习记录。每次练完歌点「记录一次练习」打卡，我们会帮你算连续天数和累计时长。
        </p>
      ) : (
        <>
          {/* 统计数字行 */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="text-center">
              <p className={`text-[22px] font-bold tabular-nums ${dark ? "text-amber-400" : "text-amber-600"}`}>
                {stats.current_streak_days}
              </p>
              <p className="text-[11px] text-muted-foreground">连续天数</p>
            </div>
            <div className="text-center">
              <p className={`text-[22px] font-bold tabular-nums ${dark ? "text-emerald-400" : "text-emerald-600"}`}>
                {fmtMinutes(stats.total_minutes)}
              </p>
              <p className="text-[11px] text-muted-foreground">累计时长</p>
            </div>
            <div className="text-center">
              <p className={`text-[22px] font-bold tabular-nums ${dark ? "text-sky-400" : "text-sky-600"}`}>
                {stats.last_30_days}
              </p>
              <p className="text-[11px] text-muted-foreground">近 30 天</p>
            </div>
          </div>

          {/* 本月摘要 + TOP5 */}
          {stats.top_practiced.length > 0 && (
            <div className={`rounded-xl p-3 text-xs leading-relaxed ${dark ? "bg-zinc-700/50" : "bg-muted/60"}`}>
              <p className="mb-1 font-semibold text-[11px] uppercase tracking-wider text-muted-foreground">
                练习最多
              </p>
              <div className="flex flex-wrap gap-2">
                {stats.top_practiced.slice(0, 5).map((t, i) => (
                  <span key={i} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] ${dark ? "bg-zinc-600/50 text-zinc-300" : "bg-muted text-muted-foreground"}`}>
                    {t.title || "无歌曲"} ×{t.sessions}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 本月统计 */}
          {stats.month_current_sessions > 0 && (
            <p className="mt-3 text-[11px] text-muted-foreground">
              本月已练习 {stats.month_current_sessions} 次，共 {fmtMinutes(stats.month_current_minutes)}
            </p>
          )}
        </>
      )}
    </section>
  );
}

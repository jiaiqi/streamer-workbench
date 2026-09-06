/// P1-A1.1 今晚视图 — 升格自 TonightWorkbench。
///
/// 设计动机（design/prototypes/2026-09-06-功能与UIUX优化分析.md §1 判断 1）：
///   原 IA 把海报工作台放在首屏，TonightWorkbench 是 256px 侧栏里的"塞进海报台的 guest"。
///   真实动线是「白天备演 → 夜间直播 → 下播复盘」（ADR-008 / v3 §6.6），海报是产出物而非入口。
///   本视图把 TonightWorkbench 5 区（状态/动作/歌单/准备/推荐）升格为顶级 view，作为默认首屏。
///
/// 范围（v0.1，最小切片）：
///   - 复用 TonightWorkbench 全部 5 区（不改 925 行内部）
///   - 顶部一个屏幕级标题区：场景说明 + 「去工作台」CTA
///   - 把 PosterBridge 主题墙也带过来（首屏展示策展资源；用户停留 > 0 帧即可见）
///   - 不引入 keep-alive / URL 路由（走 P1 阶段二第 2 步）
///   - 不接 entitlements / lyric 端点（走 P1 阶段二第 2/3 步）
///
/// 不触碰 core/ / server/ 任何 Python 边界。
import TonightWorkbench, { type TonightWorkbenchProps } from "../components/TonightWorkbench";
import WorkspacePosterBridge from "../posters/WorkspacePosterBridge";

export interface TonightViewProps {
  dark: boolean;
  /** 工作台主题列表（从 useWorkspaceState 拿） */
  themes: { name: string }[];
  /** 选择主题回调 */
  onSelectTheme: (name: string) => void;
  /** 选择画布回调 */
  onSelectCanvas: (canvas: string) => void;
  /** 切到工作台 view（给 CTA 用） */
  onGoToWorkspace: () => void;
  /* ---- 透传给 TonightWorkbench 的 4+3 回调 ---- */
  onPlaySong: TonightWorkbenchProps["onPlaySong"];
  onOpenLiveView: TonightWorkbenchProps["onOpenLiveView"];
  onCreatePosterFromTop: TonightWorkbenchProps["onCreatePosterFromTop"];
  onSwitchToStats: TonightWorkbenchProps["onSwitchToStats"];
  onGenerateRecap?: TonightWorkbenchProps["onGenerateRecap"];
  onGenerateLearningReport?: TonightWorkbenchProps["onGenerateLearningReport"];
  onOpenQuickView?: TonightWorkbenchProps["onOpenQuickView"];
}

/**
 * 今晚视图主组件。
 *
 * 布局（双栏，左主右辅）：
 *   - 左侧主区：TonightWorkbench（A-E 5 区）+ 屏幕标题
 *   - 右侧辅区：WorkspacePosterBridge（海报文档区 + 主题墙）
 *
 * 注：保留 TonightWorkbench 原视觉与交互，不在容器层加任何 overlay。
 */
export default function TonightView({
  dark,
  themes,
  onSelectTheme,
  onSelectCanvas,
  onGoToWorkspace,
  onPlaySong,
  onOpenLiveView,
  onCreatePosterFromTop,
  onSwitchToStats,
  onGenerateRecap,
  onGenerateLearningReport,
  onOpenQuickView,
}: TonightViewProps) {
  return (
    <div
      data-testid="tonight-view"
      className={`flex flex-1 overflow-hidden ${dark ? "bg-zinc-900" : "bg-background"}`}
    >
      {/* ===== 左侧主区：今晚工作台 5 区 ===== */}
      <main className="flex-1 overflow-y-auto">
        {/* 屏幕标题区（每屏 1 个） */}
        <header
          className={`px-6 py-4 border-b ${dark ? "border-zinc-700/50" : "border-border"}`}
          data-testid="tonight-view-header"
        >
          <p className="eyebrow">今晚</p>
          <div className="mt-1 flex items-baseline gap-3 flex-wrap">
            <h1
              className={`font-serif text-[22px] font-semibold tracking-wide ${dark ? "text-zinc-100" : "text-foreground"}`}
            >
              开播前 · 准备
            </h1>
            <span className={`text-[12px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
              先看就绪度，再开直播
            </span>
          </div>
          <p className={`mt-1.5 text-[12px] leading-relaxed max-w-[640px] ${dark ? "text-zinc-400" : "text-muted-foreground"}`}>
            5 区：当前场次状态 · 动作入口 · 今晚歌单 · 演出准备检查 · 数据反哺。
            海报创作是这条动线上的产出物，移到了右下角的策展资源区。
          </p>
        </header>

        {/* 今晚工作台 5 区（A-E 全部复用） */}
        <TonightWorkbench
          dark={dark}
          onPlaySong={onPlaySong}
          onOpenLiveView={onOpenLiveView}
          onCreatePosterFromTop={onCreatePosterFromTop}
          onSwitchToStats={onSwitchToStats}
          onGenerateRecap={onGenerateRecap}
          onGenerateLearningReport={onGenerateLearningReport}
          onOpenQuickView={onOpenQuickView}
        />

        {/* 海报工作台入口 CTA — 解释为何海报搬到右下角，不让用户找不到 */}
        <div
          className={`mx-6 my-4 rounded-2xl p-4 border ${
            dark ? "border-zinc-700/50 bg-zinc-800/30" : "border-border bg-muted/40"
          }`}
        >
          <p className={`text-[12px] font-semibold ${dark ? "text-zinc-200" : "text-foreground"}`}>
            需要专门做一张海报？
          </p>
          <p className={`mt-1 text-[11px] leading-relaxed ${dark ? "text-zinc-400" : "text-muted-foreground"}`}>
            海报创作已搬到工作台视图。点下方按钮进入，调参 / 换主题 / 切画布 / 导出 PNG。
          </p>
          <button
            type="button"
            data-testid="tonight-go-to-workspace"
            onClick={onGoToWorkspace}
            className={`mt-2.5 inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors cursor-pointer ${
              dark
                ? "bg-zinc-100 text-zinc-900 hover:bg-white"
                : "bg-foreground text-background hover:opacity-90"
            }`}
          >
            进入海报工作台
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </main>

      {/* ===== 右侧辅区：海报文档 + 主题墙（与原 workspace 视图一致） ===== */}
      <aside
        className={`w-72 shrink-0 border-l overflow-y-auto hidden min-[1100px]:block transition-colors duration-500 ${
          dark ? "border-zinc-700/50 bg-zinc-800/30" : "border-border"
        }`}
        data-testid="tonight-poster-rail"
      >
        {/* R1a.5 海报文档区 + 歌曲来源（独立 hook 状态机） */}
        <WorkspacePosterBridge
          dark={dark}
          availableThemeNames={themes.map(t => t.name)}
          onThemeSelect={onSelectTheme}
          onCanvasSelect={onSelectCanvas}
        />
        <div className="px-4 pt-5 pb-3">
          <p className="eyebrow">策展资源</p>
          <h2 className="panel-title">海报主题</h2>
          <p className="panel-copy">主题与布局独立组合。选择后切到工作台实时更新中央展品。</p>
        </div>
        <div className="px-3 pb-4">
          <p className={`text-[11px] leading-relaxed ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            主题缩略图与参数调节在点击「进入海报工作台」后展开。
          </p>
        </div>
      </aside>
    </div>
  );
}

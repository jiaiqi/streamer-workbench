/// P1 R1a.5 工作台 Poster 桥接：
///
/// 这个组件挂载在 `<aside>` 左栏头部，封装：
/// 1. usePosterStore()：单文档状态机
/// 2. 把 store.current.theme_id / canvas_id 同步回 App 的 setSelTheme / setCanvas
///    （effect：标题/画布变化 → 预览输入层跟着变）
/// 3. 渲染 <PostersSidebar /> + <SongSourcePicker />
///
/// App.tsx 不持有 poster store，避免破坏既有 600+ 行的工作台主流程。
import { useEffect, useRef } from "react";
import { usePosterStore } from "./usePosterStore";
import PostersSidebar from "./PostersSidebar";
import SongSourcePicker from "./SongSourcePicker";

interface WorkspacePosterBridgeProps {
  dark: boolean;
  /** 当前已选主题，用于侦测首次需要同步。回调 → 父级 setSelTheme。 */
  onThemeSelect: (themeName: string) => void;
  /** 当前已选画布，用于「海报切回来时就用画布」。回调 → 父级 setCanvas。 */
  onCanvasSelect: (canvasId: string) => void;
  /** 当前主题列表（来自 App 的 themes）。用于自动同步时校验存在。 */
  availableThemeNames: string[];
}

export default function WorkspacePosterBridge({
  dark, onThemeSelect, onCanvasSelect, availableThemeNames,
}: WorkspacePosterBridgeProps) {
  const store = usePosterStore();

  // 同步 Poster → App 预览层：theme_id / canvas_id 变化时反向注入父级。
  // 仅在已存在该主题 / 已知画布时同步，避免空字符串污染。
  const lastThemeRef = useRef<string>("");
  const lastCanvasRef = useRef<string>("");
  useEffect(() => {
    const desiredTheme = store.current.theme_id;
    if (desiredTheme && desiredTheme !== lastThemeRef.current
        && availableThemeNames.includes(desiredTheme)) {
      lastThemeRef.current = desiredTheme;
      onThemeSelect(desiredTheme);
    }
  }, [store.current.theme_id, availableThemeNames, onThemeSelect]);

  useEffect(() => {
    const desiredCanvas = store.current.canvas_id;
    if (desiredCanvas && desiredCanvas !== lastCanvasRef.current) {
      lastCanvasRef.current = desiredCanvas;
      onCanvasSelect(desiredCanvas);
    }
  }, [store.current.canvas_id, onCanvasSelect]);

  // P2 R4: 监听全局 Cmd+Z / Cmd+Shift+Z 事件
  useEffect(() => {
    const onUndo = () => store.undo();
    const onRedo = () => store.redo();
    window.addEventListener("poster:undo", onUndo);
    window.addEventListener("poster:redo", onRedo);
    return () => {
      window.removeEventListener("poster:undo", onUndo);
      window.removeEventListener("poster:redo", onRedo);
    };
  }, [store]);

  return (
    <>
      <PostersSidebar store={store} dark={dark} />
      <SongSourcePicker store={store} dark={dark} />
    </>
  );
}

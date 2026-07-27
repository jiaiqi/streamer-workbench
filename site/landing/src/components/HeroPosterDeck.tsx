import { useEffect, useRef, useState } from 'react';

// 7 主题 metadata（与 ThemeGallery 同步）
const THEMES = [
  { id: 'ocean', name: '海洋柔光',   c1: '#2b544e', c2: '#246e60', c3: '#bce0d2' },
  { id: 'dream', name: '梦幻海洋',   c1: '#5f4658', c2: '#7c4a63', c3: '#f0d0e0' },
  { id: 'cream', name: '奶油花园',   c1: '#6b4a3f', c2: '#8a4a38', c3: '#f7c7b2' },
  { id: 'green', name: '青提气泡',   c1: '#3d5e58', c2: '#4f8576', c3: '#d4e8b8' },
  { id: 'note',  name: '卡通音符',   c1: '#465044', c2: '#406e5a', c3: '#c6e9d2' },
  { id: 'glass', name: '奶油玻璃',   c1: '#465064', c2: '#406a94', c3: '#e4eef6' },
  { id: 'retro', name: '轻复古唱片', c1: '#3a2820', c2: '#7a4a32', c3: '#e8b888' },
];

/**
 * Hero 主交互区：3D poster stack + 主题轮播 + 鼠标光晕。
 * 7 张主题 poster 错位叠放，hover 散开；每 3s 切换主色。
 */
export default function HeroPosterDeck() {
  const [active, setActive] = useState(0);
  const [page, setPage] = useState(1);
  const [glow, setGlow] = useState({ x: 50, y: 50 });
  const rootRef = useRef<HTMLDivElement>(null);

  // 自动轮播
  useEffect(() => {
    const t = setInterval(() => setActive((i) => (i + 1) % THEMES.length), 3000);
    return () => clearInterval(t);
  }, []);

  // 键盘 ←/→ 切主题，↑/↓ 切页
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.key === 'ArrowLeft')  setActive((i) => (i - 1 + THEMES.length) % THEMES.length);
      if (e.key === 'ArrowRight') setActive((i) => (i + 1) % THEMES.length);
      if (e.key === 'ArrowUp')    setPage(1);
      if (e.key === 'ArrowDown')  setPage(2);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // 鼠标移动驱动光晕
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!rootRef.current) return;
      const rect = rootRef.current.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      setGlow({ x, y });
    };
    const el = rootRef.current;
    if (el) {
      el.addEventListener('mousemove', onMove);
      return () => el.removeEventListener('mousemove', onMove);
    }
  }, []);

  // 当前主题注入 CSS 变量（聚光灯色随主题变化）
  useEffect(() => {
    const t = THEMES[active];
    document.documentElement.style.setProperty('--active-theme-c2', t.c2);
  }, [active]);

  return (
    <div ref={rootRef} className="hero-deck">
      <div
        className="hero-spotlight"
        style={{
          background: `radial-gradient(circle, ${THEMES[active].c2}55, transparent 65%)`,
          left: `${glow.x}%`,
          top: `${glow.y}%`,
        }}
      />

      <div className="poster-stack">
        {[0, 1, 2, 3].map((i) => {
          const idx = (active + i) % THEMES.length;
          const t = THEMES[idx];
          return (
            <div
              key={i}
              className="poster-card"
              style={{
                background: `linear-gradient(180deg, ${t.c1} 0%, ${t.c2} 30%, ${t.c3} 65%, #f7f6f2 100%)`,
                color: '#fff',
                textShadow: '0 1px 4px rgba(0,0,0,.3)',
              }}
            >
              {t.name}
            </div>
          );
        })}
      </div>

      <div className="poster-dots">
        {THEMES.map((_, i) => (
          <span key={i} className={i === active ? 'active' : ''} />
        ))}
      </div>

      <div className="page-indicator">
        <button
          className={page === 1 ? 'active' : ''}
          onClick={() => setPage(1)}
        >
          P1
        </button>
        <button
          className={page === 2 ? 'active' : ''}
          onClick={() => setPage(2)}
        >
          P2
        </button>
      </div>

      <style>{`
        .hero-deck {
          position: relative;
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 500px;
        }
        .hero-spotlight {
          position: absolute;
          width: 380px;
          height: 380px;
          border-radius: 50%;
          filter: blur(60px);
          transform: translate(-50%, -50%);
          transition: background 0.6s var(--ease-cinematic);
          pointer-events: none;
        }
        .poster-stack {
          position: relative;
          width: 280px;
          height: 497px;
        }
        .poster-card {
          position: absolute;
          width: 260px;
          height: 462px;
          border-radius: var(--radius-lg);
          overflow: hidden;
          background: var(--surface-1);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-card);
          display: grid;
          place-items: center;
          font-size: 14px;
          transition: all 0.5s var(--ease-cinematic);
          cursor: pointer;
        }
        .poster-card:nth-child(1) { z-index: 4; top: 0; left: 10px; transform: rotate(-2deg); }
        .poster-card:nth-child(2) { z-index: 3; top: 14px; left: -28px; transform: rotate(-6deg); }
        .poster-card:nth-child(3) { z-index: 2; top: 10px; left: 44px; transform: rotate(3deg); }
        .poster-card:nth-child(4) { z-index: 1; top: 26px; left: 8px; transform: rotate(7deg); }
        .poster-stack:hover .poster-card:nth-child(1) { transform: rotate(-4deg) translateX(-60px); }
        .poster-stack:hover .poster-card:nth-child(2) { transform: rotate(-14deg) translateX(-100px); }
        .poster-stack:hover .poster-card:nth-child(3) { transform: rotate(8deg) translateX(80px); }
        .poster-stack:hover .poster-card:nth-child(4) { transform: rotate(16deg) translateX(40px); }
        .poster-dots {
          position: absolute;
          bottom: -36px;
          left: 50%;
          transform: translateX(-50%);
          display: flex;
          gap: 8px;
        }
        .poster-dots span {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--text-3);
          transition: all 0.3s;
        }
        .poster-dots span.active {
          background: var(--spotlight);
          box-shadow: var(--glow-spot);
        }
        .page-indicator {
          position: absolute;
          top: 16px;
          right: -8px;
          display: flex;
          flex-direction: column;
          gap: 4px;
          font-family: var(--font-mono);
        }
        .page-indicator button {
          width: 36px;
          height: 28px;
          border-radius: 6px;
          border: 1px solid var(--border);
          background: var(--surface-1);
          color: var(--text-3);
          font-size: 11px;
          cursor: pointer;
          transition: all 0.2s;
        }
        .page-indicator button.active {
          background: var(--primary);
          color: var(--primary-foreground);
          border-color: var(--primary);
        }
      `}</style>
    </div>
  );
}
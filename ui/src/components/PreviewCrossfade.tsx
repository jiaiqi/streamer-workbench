import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";

/* ---- 海报预览 crossfade（主规格 §4.6 预览管线 POC）----
   旧图保持到新图加载完成，再 220–320ms 淡入替换，避免闪白/白屏跳变；
   prefers-reduced-motion 下取消位移与淡入时长，直接替换。
   加载失败不替换旧图，错误态由父级处理。 */

interface Frame {
  id: number;
  src: string;
}

export default function PreviewCrossfade({ src, alt, onLoaded, onFailed }: {
  src: string;
  alt: string;
  onLoaded: () => void;
  onFailed: () => void;
}) {
  const reducedMotion = useReducedMotion();
  const [displayed, setDisplayed] = useState<Frame | null>(null);
  const [incoming, setIncoming] = useState<Frame | null>(null);
  const counter = useRef(0);

  useEffect(() => {
    if (!src) {
      setDisplayed(null);
      setIncoming(null);
      return;
    }
    setDisplayed(current => {
      if (current?.src === src) return current;
      setIncoming(previous => {
        if (previous?.src === src) return previous;
        counter.current += 1;
        return { id: counter.current, src };
      });
      return current;
    });
  }, [src]);

  const promote = (frame: Frame) => {
    setDisplayed(frame);
    setIncoming(null);
    onLoaded();
  };

  return (
    <>
      {displayed && (
        <img key={displayed.id} src={displayed.src} alt={alt}
          className="absolute inset-0 h-full w-full object-contain" />
      )}
      {incoming && (
        <motion.img
          key={incoming.id}
          src={incoming.src}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full object-contain"
          initial={{ opacity: reducedMotion ? 1 : 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: reducedMotion ? 0 : 0.26, ease: [0.22, 1, 0.36, 1] }}
          onLoad={() => promote(incoming)}
          onError={() => { setIncoming(null); onFailed(); }}
        />
      )}
    </>
  );
}

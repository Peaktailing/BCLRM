import { useMemo } from "react";

/** 分子结构背景动画 - 苯环 + 连接键 + 浮动粒子 */

interface Particle {
  x: number;
  y: number;
  r: number;
  duration: number;
  delay: number;
  opacity: number;
}

interface MoleculeNode {
  cx: number;
  cy: number;
  r: number;
  rotate: number;
  duration: number;
  delay: number;
}

export default function MolecularBackground() {
  // 浮动粒子 - 随机生成位置
  const particles = useMemo<Particle[]>(() => {
    return Array.from({ length: 40 }, () => ({
      x: Math.random() * 100,
      y: Math.random() * 100,
      r: Math.random() * 2 + 0.5,
      duration: Math.random() * 15 + 10,
      delay: Math.random() * 5,
      opacity: Math.random() * 0.4 + 0.1,
    }));
  }, []);

  // 分子结构节点（苯环位置）
  const molecules = useMemo<MoleculeNode[]>(() => {
    return [
      { cx: 15, cy: 20, r: 35, rotate: 0, duration: 25, delay: 0 },
      { cx: 75, cy: 15, r: 45, rotate: 30, duration: 30, delay: 2 },
      { cx: 50, cy: 55, r: 50, rotate: 15, duration: 35, delay: 1 },
      { cx: 20, cy: 75, r: 30, rotate: 45, duration: 28, delay: 3 },
      { cx: 80, cy: 70, r: 40, rotate: 60, duration: 32, delay: 1.5 },
      { cx: 60, cy: 35, r: 25, rotate: 20, duration: 22, delay: 0.5 },
    ];
  }, []);

  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden">
      {/* 网格背景 */}
      <div className="grid-bg absolute inset-0 opacity-60" />

      {/* 径向渐变遮罩 - 中心透明，边缘渐暗 */}
      <div className="radial-fade absolute inset-0" />

      {/* 浮动粒子 */}
      <svg className="absolute inset-0 h-full w-full">
        {particles.map((p, i) => (
          <circle
            key={`particle-${i}`}
            cx={`${p.x}%`}
            cy={`${p.y}%`}
            r={p.r}
            fill="#00d4ff"
            opacity={p.opacity}
            style={{
              animation: `particleDrift ${p.duration}s linear infinite`,
              animationDelay: `${p.delay}s`,
            }}
          />
        ))}
      </svg>

      {/* 分子结构 - 苯环 */}
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="xMidYMid slice"
      >
        <defs>
          <linearGradient id="bondGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00d4ff" stopOpacity="0.3" />
            <stop offset="50%" stopColor="#14b8a6" stopOpacity="0.2" />
            <stop offset="100%" stopColor="#00d4ff" stopOpacity="0.1" />
          </linearGradient>
          <radialGradient id="atomGradient">
            <stop offset="0%" stopColor="#00d4ff" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#00d4ff" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* 分子之间的连接键 */}
        <g stroke="url(#bondGradient)" strokeWidth="0.15" fill="none">
          <line x1="15" y1="20" x2="50" y2="55" />
          <line x1="75" y1="15" x2="50" y2="55" />
          <line x1="50" y1="55" x2="20" y2="75" />
          <line x1="50" y1="55" x2="80" y2="70" />
          <line x1="50" y1="55" x2="60" y2="35" />
          <line x1="75" y1="15" x2="60" y2="35" />
        </g>

        {/* 苯环 */}
        {molecules.map((mol, i) => (
          <g
            key={`molecule-${i}`}
            style={{
              transformOrigin: `${mol.cx}% ${mol.cy}%`,
              animation: `moleculeFloat ${mol.duration}s ease-in-out infinite`,
              animationDelay: `${mol.delay}s`,
            }}
          >
            <BenzeneRing cx={mol.cx} cy={mol.cy} r={mol.r} rotate={mol.rotate} />
          </g>
        ))}
      </svg>

      {/* 底部辉光 */}
      <div
        className="absolute inset-x-0 bottom-0 h-1/3"
        style={{
          background:
            "linear-gradient(to top, rgba(0,212,255,0.05) 0%, transparent 100%)",
        }}
      />
    </div>
  );
}

/** 单个苯环结构 - 六边形 + 内部双键 */
function BenzeneRing({
  cx,
  cy,
  r,
  rotate,
}: {
  cx: number;
  cy: number;
  r: number;
  rotate: number;
}) {
  const points = Array.from({ length: 6 }, (_, i) => {
    const angle = (Math.PI / 3) * i - Math.PI / 2 + (rotate * Math.PI) / 180;
    return {
      x: cx + r * 0.4 * Math.cos(angle),
      y: cy + r * 0.4 * Math.sin(angle),
    };
  });

  const polygonPoints = points.map((p) => `${p.x},${p.y}`).join(" ");

  // 内部双键线
  const innerPoints = points.map((p) => ({
    x: cx + (p.x - cx) * 0.7,
    y: cy + (p.y - cy) * 0.7,
  }));

  return (
    <g>
      {/* 外环 */}
      <polygon
        points={polygonPoints}
        fill="none"
        stroke="#00d4ff"
        strokeWidth="0.2"
        opacity="0.25"
      />
      {/* 内环（双键效果） */}
      <polygon
        points={innerPoints.map((p) => `${p.x},${p.y}`).join(" ")}
        fill="none"
        stroke="#14b8a6"
        strokeWidth="0.15"
        opacity="0.15"
      />
      {/* 顶点原子 */}
      {points.map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r="0.6"
          fill="url(#atomGradient)"
          opacity="0.4"
        />
      ))}
      {/* 中心原子 */}
      <circle cx={cx} cy={cy} r="1" fill="#00d4ff" opacity="0.15" />
    </g>
  );
}

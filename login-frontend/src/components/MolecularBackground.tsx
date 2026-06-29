/** 浅色背景装饰 - 柔和的色块 + 网格 */

export default function MolecularBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden">
      {/* 浅色网格底纹 */}
      <div
        className="absolute inset-0 opacity-[0.4]"
        style={{
          backgroundImage:
            "linear-gradient(#f1f3f5 1px, transparent 1px), linear-gradient(90deg, #f1f3f5 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      {/* 漂浮色块 - 珊瑚红 */}
      <div
        className="animate-blob-drift absolute -left-20 -top-20 h-96 w-96 rounded-full opacity-20 blur-3xl"
        style={{ background: "#FF6B6B" }}
      />

      {/* 漂浮色块 - 暖橙 */}
      <div
        className="animate-blob-drift-slow absolute -bottom-32 -right-20 h-[28rem] w-[28rem] rounded-full opacity-15 blur-3xl"
        style={{ background: "#ffa94d" }}
      />

      {/* 漂浮色块 - 淡蓝 */}
      <div
        className="animate-blob-drift absolute right-1/4 top-1/3 h-72 w-72 rounded-full opacity-10 blur-3xl"
        style={{ background: "#74c0fc", animationDelay: "5s" }}
      />

      {/* 顶部高光 */}
      <div
        className="absolute inset-x-0 top-0 h-64"
        style={{
          background:
            "linear-gradient(to bottom, rgba(255,107,107,0.06) 0%, transparent 100%)",
        }}
      />
    </div>
  );
}

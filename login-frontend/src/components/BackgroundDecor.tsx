export default function BackgroundDecor() {
  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden">
      <div className="absolute inset-0 opacity-[0.4]" style={{ backgroundImage: "linear-gradient(#f1f3f5 1px, transparent 1px), linear-gradient(90deg, #f1f3f5 1px, transparent 1px)", backgroundSize: "40px 40px" }} />
      <div className="absolute -left-20 -top-20 h-96 w-96 rounded-full opacity-20 blur-3xl" style={{ background: "#FF6B6B" }} />
      <div className="absolute -bottom-32 -right-20 h-[28rem] w-[28rem] rounded-full opacity-15 blur-3xl" style={{ background: "#ffa94d" }} />
      <div className="absolute right-1/4 top-1/3 h-72 w-72 rounded-full opacity-10 blur-3xl" style={{ background: "#74c0fc" }} />
      <div className="absolute inset-x-0 top-0 h-64" style={{ background: "linear-gradient(to bottom, rgba(255,107,107,0.06) 0%, transparent 100%)" }} />
    </div>
  );
}

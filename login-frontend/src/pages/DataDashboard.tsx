import { useState } from "react";
import { motion } from "motion/react";
import {
  BarChart3, TrendingUp, TrendingDown, PackageOpen, ArrowRightLeft,
  RotateCcw, AlertTriangle,
} from "lucide-react";

type Period = "本周" | "本月" | "本季度" | "本年";
const PERIODS: Period[] = ["本周", "本月", "本季度", "本年"];

const KPI_CARDS = [
  {
    key: "stockIn",
    label: "本月入库",
    value: "47瓶",
    change: "+12%",
    changeLabel: "vs上月",
    isUp: true,
    icon: PackageOpen,
    color: "accent-green",
  },
  {
    key: "borrow",
    label: "本月领用",
    value: "89瓶",
    change: "+5%",
    changeLabel: "vs上月",
    isUp: true,
    icon: ArrowRightLeft,
    color: "accent-blue",
  },
  {
    key: "return",
    label: "本月归还",
    value: "72瓶",
    change: "-8%",
    changeLabel: "vs上月",
    isUp: false,
    icon: RotateCcw,
    color: "accent-cyan",
  },
  {
    key: "expiring",
    label: "即将过期",
    value: "23瓶",
    change: "-15%",
    changeLabel: "vs上月",
    isUp: false,
    icon: AlertTriangle,
    color: "accent-orange",
  },
];

const PIE_DATA = [
  { label: "无机", percent: 35, color: "#E1251B" },
  { label: "有机", percent: 28, color: "#5E71E4" },
  { label: "生化", percent: 20, color: "#00B42A" },
  { label: "标准品", percent: 12, color: "#FF7D00" },
  { label: "其他", percent: 5, color: "#94A3B8" },
];

const STORAGE_DATA = [
  { label: "常温A区", value: 234, color: "#E1251B" },
  { label: "常温B区", value: 189, color: "#5E71E4" },
  { label: "冷藏区", value: 156, color: "#0FC6C2" },
  { label: "冷冻区", value: 87, color: "#00B42A" },
  { label: "危险品柜", value: 68, color: "#FF7D00" },
];

const BORROW_RANK = [
  { name: "无水乙醇", count: 156, percent: 100 },
  { name: "浓盐酸", count: 132, percent: 85 },
  { name: "氢氧化钠", count: 108, percent: 69 },
  { name: "甲醇", count: 89, percent: 57 },
  { name: "丙酮", count: 74, percent: 47 },
];

export default function DataDashboard() {
  const [period, setPeriod] = useState<Period>("本月");

  const maxStorage = Math.max(...STORAGE_DATA.map((s) => s.value));

  return (
    <div className="space-y-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-wrap items-center justify-between gap-3"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-blue/10">
            <BarChart3 className="h-5 w-5 text-accent-blue" />
          </div>
          <h1 className="text-2xl font-bold text-text-main">数据看板</h1>
        </div>
        <div className="flex items-center gap-1 rounded-lg bg-bg-sub p-1">
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                period === p
                  ? "bg-primary text-white shadow-sm"
                  : "text-text-sub hover:text-text-main"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </motion.div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        {KPI_CARDS.map((card, i) => {
          const Icon = card.icon;
          return (
            <motion.div
              key={card.key}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 * (i + 1) }}
              className="rounded-xl border border-border bg-bg-surface p-4 shadow-card"
            >
              <div className="flex items-center justify-between">
                <div
                  className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                    card.color === "accent-green"
                      ? "bg-accent-green/10"
                      : card.color === "accent-blue"
                      ? "bg-accent-blue/10"
                      : card.color === "accent-cyan"
                      ? "bg-accent-cyan/10"
                      : "bg-accent-orange/10"
                  }`}
                >
                  <Icon
                    className={`h-5 w-5 ${
                      card.color === "accent-green"
                        ? "text-accent-green"
                        : card.color === "accent-blue"
                        ? "text-accent-blue"
                        : card.color === "accent-cyan"
                        ? "text-accent-cyan"
                        : "text-accent-orange"
                    }`}
                  />
                </div>
                <div
                  className={`flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-medium ${
                    card.isUp
                      ? "bg-accent-green/10 text-accent-green"
                      : "bg-accent-red/10 text-accent-red"
                  }`}
                >
                  {card.isUp ? (
                    <TrendingUp size={12} />
                  ) : (
                    <TrendingDown size={12} />
                  )}
                  {card.change}
                </div>
              </div>
              <div className="mt-3">
                <div className="text-2xl font-bold text-text-main">{card.value}</div>
                <div className="mt-0.5 text-xs text-text-muted">
                  {card.label} · {card.changeLabel}
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 库存趋势 */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-xl border border-border bg-bg-surface p-5 shadow-card"
        >
          <h2 className="mb-4 text-base font-semibold text-text-main">库存趋势</h2>
          <div className="flex items-end justify-between gap-1 h-48 px-2">
            {["1月", "2月", "3月", "4月", "5月", "6月"].map((month, i) => {
              const heights = [60, 75, 90, 85, 110, 130];
              const h = heights[i];
              return (
                <div key={month} className="flex flex-1 flex-col items-center gap-1.5">
                  <span className="text-xs font-medium text-text-main">{h}</span>
                  <div className="relative w-full max-w-[40px] flex-1 rounded-t-md bg-bg-sub">
                    <motion.div
                      initial={{ height: 0 }}
                      animate={{ height: `${(h / 140) * 100}%` }}
                      transition={{ duration: 0.8, delay: 0.3 + i * 0.1 }}
                      className="absolute bottom-0 w-full rounded-t-md bg-primary"
                    />
                  </div>
                  <span className="text-xs text-text-muted">{month}</span>
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex items-center justify-center gap-4 text-xs text-text-sub">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-sm bg-primary" />
              入库量
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-sm bg-primary-50 border border-primary" />
              领用量
            </span>
          </div>
        </motion.div>

        {/* 试剂类型分布 */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="rounded-xl border border-border bg-bg-surface p-5 shadow-card"
        >
          <h2 className="mb-4 text-base font-semibold text-text-main">试剂类型分布</h2>
          <div className="flex items-center gap-6">
            {/* Pie placeholder */}
            <div className="relative flex h-40 w-40 shrink-0 items-center justify-center">
              <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
                {(() => {
                  let cumulative = 0;
                  return PIE_DATA.map((item) => {
                    const startAngle = cumulative;
                    const angle = (item.percent / 100) * 360;
                    cumulative += angle;
                    const startRad = (startAngle * Math.PI) / 180;
                    const endRad = ((startAngle + angle) * Math.PI) / 180;
                    const r = 50;
                    const cx = 60;
                    const cy = 60;
                    const x1 = cx + r * Math.cos(startRad);
                    const y1 = cy + r * Math.sin(startRad);
                    const x2 = cx + r * Math.cos(endRad);
                    const y2 = cy + r * Math.sin(endRad);
                    const largeArc = angle > 180 ? 1 : 0;
                    return (
                      <path
                        key={item.label}
                        d={`M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`}
                        fill={item.color}
                      />
                    );
                  });
                })()}
                <circle cx="60" cy="60" r="28" fill="white" />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-lg font-bold text-text-main">156</span>
                <span className="text-xs text-text-muted">总计</span>
              </div>
            </div>
            {/* Legend */}
            <div className="flex-1 space-y-2.5">
              {PIE_DATA.map((item) => (
                <div key={item.label} className="flex items-center gap-2">
                  <span
                    className="inline-block h-3 w-3 rounded-sm shrink-0"
                    style={{ backgroundColor: item.color }}
                  />
                  <span className="text-sm text-text-main">{item.label}</span>
                  <span className="ml-auto text-sm font-medium text-text-sub">{item.percent}%</span>
                  <div className="w-20 h-1.5 rounded-full bg-bg-sub overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${item.percent}%`,
                        backgroundColor: item.color,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 存储位置统计 */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-xl border border-border bg-bg-surface p-5 shadow-card"
        >
          <h2 className="mb-4 text-base font-semibold text-text-main">存储位置统计</h2>
          <div className="space-y-4">
            {STORAGE_DATA.map((item) => (
              <div key={item.label} className="flex items-center gap-3">
                <span className="w-16 shrink-0 text-sm text-text-sub">{item.label}</span>
                <div className="flex-1 h-6 rounded-md bg-bg-sub overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${(item.value / maxStorage) * 100}%` }}
                    transition={{ duration: 0.8, delay: 0.4 }}
                    className="h-full rounded-md flex items-center justify-end pr-2"
                    style={{ backgroundColor: item.color }}
                  >
                    <span className="text-xs font-medium text-white">{item.value}</span>
                  </motion.div>
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* 领用排行 */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
          className="rounded-xl border border-border bg-bg-surface p-5 shadow-card"
        >
          <h2 className="mb-4 text-base font-semibold text-text-main">领用排行 TOP5</h2>
          <div className="space-y-3">
            {BORROW_RANK.map((item, i) => (
              <div key={item.name} className="flex items-center gap-3">
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white ${
                    i === 0
                      ? "bg-primary"
                      : i === 1
                      ? "bg-accent-orange"
                      : i === 2
                      ? "bg-accent-blue"
                      : "bg-text-muted"
                  }`}
                >
                  {i + 1}
                </span>
                <span className="w-20 shrink-0 text-sm text-text-main">{item.name}</span>
                <div className="flex-1 h-4 rounded-full bg-bg-sub overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${item.percent}%` }}
                    transition={{ duration: 0.6, delay: 0.5 + i * 0.1 }}
                    className="h-full rounded-full bg-primary-100"
                  >
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: "100%",
                        backgroundColor:
                          i === 0
                            ? "#E1251B"
                            : i === 1
                            ? "#FF7D00"
                            : i === 2
                            ? "#5E71E4"
                            : "#94A3B8",
                      }}
                    />
                  </motion.div>
                </div>
                <span className="w-10 shrink-0 text-right text-sm font-medium text-text-sub">
                  {item.count}
                </span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
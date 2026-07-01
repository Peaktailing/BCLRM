import { motion } from "motion/react";
import { Home, Package, PlusCircle, ArrowRightLeft, Search, BarChart3, ShieldAlert, Settings, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { getInventoryStats, REAGENT_BOTTLES, BORROW_RECORDS } from "@/data/mock";

const statsCards = [
  { key: "total", label: "试剂瓶总数", icon: Package, color: "#E1251B", bg: "rgba(225,37,27,0.08)" },
  { key: "borrowable", label: "可借数量", icon: Package, color: "#00B42A", bg: "rgba(0,180,42,0.08)" },
  { key: "borrowed", label: "已借出", icon: ArrowRightLeft, color: "#FF7D00", bg: "rgba(255,125,0,0.08)" },
  { key: "exhausted", label: "已耗尽", icon: Package, color: "#F53F3F", bg: "rgba(245,63,63,0.08)" },
] as const;

const quickEntries = [
  { to: "/inventory", icon: Package, label: "实时库存", color: "#E1251B", bg: "rgba(225,37,27,0.08)" },
  { to: "/stock-in", icon: PlusCircle, label: "试剂入库", color: "#00B42A", bg: "rgba(0,180,42,0.08)" },
  { to: "/borrow", icon: ArrowRightLeft, label: "领用归还", color: "#FF7D00", bg: "rgba(255,125,0,0.08)" },
  { to: "/query", icon: Search, label: "综合查询", color: "#0FC6C2", bg: "rgba(15,198,194,0.08)" },
  { to: "/dashboard", icon: BarChart3, label: "数据看板", color: "#5E71E4", bg: "rgba(94,113,228,0.08)" },
  { to: "/chemical-info", icon: Package, label: "化学品信息", color: "#E1251B", bg: "rgba(225,37,27,0.08)" },
  { to: "/controlled-list", icon: ShieldAlert, label: "管控目录", color: "#F53F3F", bg: "rgba(245,63,63,0.08)" },
  { to: "/settings", icon: Settings, label: "系统设置", color: "#94A3B8", bg: "rgba(148,163,184,0.12)" },
  { to: "/query", icon: FileText, label: "操作日志", color: "#94A3B8", bg: "rgba(148,163,184,0.12)" },
];

const recentActivities = [
  { time: "2026-06-29 10:23", type: "领用", reagent: "乙醇 (无水)", user: "张三", status: "已确认", statusColor: "bg-accent-green/10 text-accent-green" },
  { time: "2026-06-29 09:15", type: "入库", reagent: "盐酸 (分析纯)", user: "李四", status: "已入库", statusColor: "bg-accent-cyan/10 text-accent-cyan" },
  { time: "2026-06-28 16:42", type: "归还", reagent: "氢氧化钠", user: "王五", status: "已归还", statusColor: "bg-accent-green/10 text-accent-green" },
  { time: "2026-06-28 14:30", type: "入库", reagent: "硫酸铜 (五水)", user: "赵六", status: "已入库", statusColor: "bg-accent-cyan/10 text-accent-cyan" },
  { time: "2026-06-28 11:20", type: "领用", reagent: "丙酮 (分析纯)", user: "张三", status: "已确认", statusColor: "bg-accent-green/10 text-accent-green" },
];

export default function Dashboard() {
  const { user } = useAuth();
  const data = getInventoryStats();

  return (
    <div className="space-y-4">
      {/* Welcome Banner */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between rounded-lg bg-bg-surface p-5 lg:p-6"
      >
        <div className="flex items-center gap-4 min-w-0">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-primary-50">
            <Home className="h-6 w-6 text-primary" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold text-text-main">
              欢迎回来，{user?.display_name ?? "管理员"}
            </h1>
            <p className="truncate text-sm mt-1 text-text-sub">今日实验室运行状态正常</p>
          </div>
        </div>
        <div className="shrink-0 flex items-center gap-2">
          <div className="flex items-center gap-1.5 rounded-md bg-primary-50 px-3 py-1.5">
            <div className="h-1.5 w-1.5 rounded-full bg-primary" />
            <span className="text-xs font-medium text-primary whitespace-nowrap">运行正常</span>
          </div>
        </div>
      </motion.div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        {statsCards.map((s, i) => {
          const Icon = s.icon;
          const value = data[s.key];
          return (
            <motion.div
              key={s.key}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 * (i + 1) }}
              className="flex items-center gap-3 rounded-lg bg-bg-surface p-4"
            >
              <div
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg"
                style={{ backgroundColor: s.bg }}
              >
                <Icon className="h-5.5 w-5.5" style={{ color: s.color }} />
              </div>
              <div className="min-w-0">
                <div className="text-2xl font-bold text-text-main">{value}</div>
                <div className="text-xs text-text-muted">{s.label}</div>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Quick Entry Grid */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="rounded-lg bg-bg-surface p-4 lg:p-5"
      >
        <h2 className="mb-4 text-base font-semibold text-text-main">快捷入口</h2>
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-9 lg:gap-4">
          {quickEntries.map((entry) => {
            const Icon = entry.icon;
            return (
              <Link
                key={entry.label}
                to={entry.to}
                className="group flex flex-col items-center gap-2.5 rounded-lg border border-border bg-bg-surface py-4 px-2 transition-all duration-200 hover:border-primary hover:shadow-md"
              >
                <div
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full"
                  style={{ backgroundColor: entry.bg }}
                >
                  <Icon className="h-5.5 w-5.5" style={{ color: entry.color }} />
                </div>
                <span className="text-xs text-center text-text-sub whitespace-nowrap">{entry.label}</span>
              </Link>
            );
          })}
        </div>
      </motion.div>

      {/* Recent Activity */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="rounded-lg bg-bg-surface p-4 lg:p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-text-main">最近操作</h2>
          <Link to="/query" className="text-xs text-text-muted hover:text-primary transition-colors">
            查看全部
          </Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">时间</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">操作类型</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border min-w-[120px]">试剂名称</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">操作人</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">状态</th>
              </tr>
            </thead>
            <tbody>
              {recentActivities.map((a, i) => (
                <tr key={i}>
                  <td className="whitespace-nowrap px-3 py-3 text-text-sub border-b border-border">{a.time}</td>
                  <td className="whitespace-nowrap px-3 py-3 text-text-main border-b border-border">{a.type}</td>
                  <td className="px-3 py-3 text-text-main border-b border-border min-w-[120px]">{a.reagent}</td>
                  <td className="whitespace-nowrap px-3 py-3 text-text-sub border-b border-border">{a.user}</td>
                  <td className="whitespace-nowrap px-3 py-3 border-b border-border">
                    <span className={`inline-flex items-center justify-center px-2 py-0.5 rounded text-xs font-medium ${a.statusColor}`}>
                      {a.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  );
}
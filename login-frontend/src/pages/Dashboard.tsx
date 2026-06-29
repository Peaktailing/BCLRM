import { motion } from "motion/react";
import { Package, CheckCircle, Send, Clock, Plus, Search, BarChart3, Settings, FlaskConical } from "lucide-react";
import { Link } from "react-router-dom";
import { getInventoryStats } from "@/data/mock";

const stats = [
  { key: "total", label: "试剂瓶总数", icon: Package, color: "#FF6B6B" },
  { key: "borrowable", label: "可借数量", icon: CheckCircle, color: "#2f9e44" },
  { key: "borrowed", label: "已借出", icon: Send, color: "#f59e0b" },
  { key: "pending", label: "待审批", icon: Clock, color: "#1971c2" },
] as const;

const quickEntries = [
  { to: "/inventory", icon: Package, title: "实时库存", desc: "查看所有试剂瓶的实时状态与剩余量" },
  { to: "/inventory", icon: Plus, title: "试剂入库", desc: "新增试剂瓶入库登记与信息录入" },
  { to: "/borrow", icon: Send, title: "领用归还", desc: "发起借出申请与归还登记流程" },
  { to: "/inventory", icon: Search, title: "综合查询", desc: "按名称、CAS号、状态等条件检索" },
  { to: "/", icon: BarChart3, title: "数据看板", desc: "库存统计数据可视化分析" },
  { to: "/settings", icon: Settings, title: "系统设置", desc: "系统信息与角色权限说明" },
];

export default function Dashboard() {
  const data = getInventoryStats();

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="rounded-xl bg-gradient-to-r from-primary to-primary-light p-6 text-white shadow-card"
      >
        <h1 className="text-2xl font-bold">🧪 试剂库管理系统</h1>
        <p className="mt-1 text-white/90">实验室试剂库存管理系统</p>
        <p className="mt-2 text-sm text-white/80">高效管理 · 安全可控 · 数据透明</p>
      </motion.div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s, i) => {
          const Icon = s.icon;
          const value = data[s.key];
          return (
            <motion.div
              key={s.key}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.05 * (i + 1) }}
              className="rounded-xl border border-border-light bg-white p-5 shadow-card"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-3xl font-bold text-text-main">{value}</p>
                  <p className="mt-1 text-sm text-text-sub">{s.label}</p>
                </div>
                <div
                  className="flex h-12 w-12 items-center justify-center rounded-lg"
                  style={{ backgroundColor: `${s.color}15`, color: s.color }}
                >
                  <Icon size={24} />
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* 快速入口 */}
      <div>
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-text-main">
          <FlaskConical size={20} className="text-primary" />
          快速入口
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {quickEntries.map((entry, i) => {
            const Icon = entry.icon;
            return (
              <motion.div
                key={entry.title}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.05 * (i + 1) }}
              >
                <Link
                  to={entry.to}
                  className="block rounded-xl border border-border-light bg-white p-5 shadow-card transition-shadow hover:shadow-card-hover"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary">
                      <Icon size={20} />
                    </div>
                    <div>
                      <p className="font-medium text-text-main">{entry.title}</p>
                      <p className="mt-1 text-sm text-text-sub">{entry.desc}</p>
                    </div>
                  </div>
                </Link>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

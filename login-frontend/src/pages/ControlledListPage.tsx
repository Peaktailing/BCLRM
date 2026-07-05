import { useState } from "react";
import { motion } from "motion/react";
import { Search, ShieldAlert } from "lucide-react";

interface ControlledChemical {
  id: number;
  name: string;
  alias: string;
  cas_number: string;
  danger_type: string;
}

const MOCK_CONTROLLED: ControlledChemical[] = [
  {
    id: 1,
    name: "浓盐酸",
    alias: "盐酸、氢氯酸",
    cas_number: "7647-01-0",
    danger_type: "腐蚀品",
  },
  {
    id: 2,
    name: "丙酮",
    alias: "二甲酮、阿西通",
    cas_number: "67-64-1",
    danger_type: "易燃液体",
  },
  {
    id: 3,
    name: "硫酸",
    alias: "磺镪水、绿矾油",
    cas_number: "7664-93-9",
    danger_type: "腐蚀品",
  },
  {
    id: 4,
    name: "甲醇",
    alias: "木醇、木精",
    cas_number: "67-56-1",
    danger_type: "易燃液体",
  },
  {
    id: 5,
    name: "硝酸银",
    alias: "银丹",
    cas_number: "7761-88-8",
    danger_type: "氧化剂",
  },
  {
    id: 6,
    name: "三氯甲烷",
    alias: "氯仿",
    cas_number: "67-66-3",
    danger_type: "有毒",
  },
];

const DANGER_TYPE_STYLES: Record<string, string> = {
  "腐蚀品": "bg-accent-orange/10 text-accent-orange border-accent-orange/20",
  "易燃液体": "bg-accent-red/10 text-accent-red border-accent-red/20",
  "氧化剂": "bg-accent-blue/10 text-accent-blue border-accent-blue/20",
  "有毒": "bg-accent-red/10 text-accent-red border-accent-red/20",
};

const DANGER_ICONS: Record<string, string> = {
  "腐蚀品": "🧪",
  "易燃液体": "🔥",
  "氧化剂": "⚡",
  "有毒": "☠️",
};

export default function ControlledListPage() {
  const [search, setSearch] = useState("");

  const filtered = MOCK_CONTROLLED.filter((c) => {
    const keyword = search.trim().toLowerCase();
    return (
      !keyword ||
      c.name.toLowerCase().includes(keyword) ||
      c.alias.toLowerCase().includes(keyword) ||
      c.cas_number.toLowerCase().includes(keyword) ||
      c.danger_type.toLowerCase().includes(keyword)
    );
  });

  return (
    <div className="space-y-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-red/10">
            <ShieldAlert className="h-5 w-5 text-accent-red" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text-main">管控化学品目录</h1>
            <p className="text-sm text-text-sub">管控化学品清单与危险分类信息</p>
          </div>
        </div>
      </motion.div>

      {/* Search */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-bg-surface p-4 shadow-card"
      >
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索化学品名称、别名、CAS号、危险类型..."
            className="w-full rounded-lg border border-border-medium bg-white py-2 pl-10 pr-4 text-sm text-text-main placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
          />
        </div>
        <span className="text-sm text-text-sub">
          共 <span className="font-semibold text-text-main">{filtered.length}</span> 种管控化学品
        </span>
      </motion.div>

      {/* Table */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-xl border border-border bg-bg-surface shadow-card overflow-hidden"
      >
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-bg-sub text-xs uppercase text-text-sub">
                <th className="px-3 py-3 text-left">化学品名称</th>
                <th className="px-3 py-3 text-left">别名</th>
                <th className="px-3 py-3 text-left">CAS号</th>
                <th className="px-3 py-3 text-left">危险类型</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr
                  key={c.id}
                  className="border-b border-border-light hover:bg-primary-50 transition-colors"
                >
                  <td className="px-3 py-2.5 font-medium text-text-main">{c.name}</td>
                  <td className="px-3 py-2.5 text-text-sub">{c.alias}</td>
                  <td className="px-3 py-2.5 text-text-sub font-mono text-xs">{c.cas_number}</td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                        DANGER_TYPE_STYLES[c.danger_type] || "bg-bg-sub text-text-muted border-border"
                      }`}
                    >
                      <span>{DANGER_ICONS[c.danger_type] || ""}</span>
                      {c.danger_type}
                    </span>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-12 text-center text-text-muted">
                    没有匹配的管控化学品
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  );
}
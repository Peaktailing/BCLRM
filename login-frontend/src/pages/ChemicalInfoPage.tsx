import { useState } from "react";
import { motion } from "motion/react";
import { Search, Plus, Pencil, Trash2, FlaskConical } from "lucide-react";

interface Chemical {
  id: number;
  name: string;
  cas_number: string;
  molecular_formula: string;
  reagent_type: string;
  storage_requirement: string;
  controlled_type: string;
}

const MOCK_CHEMICALS: Chemical[] = [
  {
    id: 1,
    name: "乙醇",
    cas_number: "64-17-5",
    molecular_formula: "C₂H₆O",
    reagent_type: "有机试剂",
    storage_requirement: "常温、避光、密封",
    controlled_type: "—",
  },
  {
    id: 2,
    name: "盐酸",
    cas_number: "7647-01-0",
    molecular_formula: "HCl",
    reagent_type: "无机试剂",
    storage_requirement: "常温、通风、密封",
    controlled_type: "腐蚀品",
  },
  {
    id: 3,
    name: "氢氧化钠",
    cas_number: "1310-73-2",
    molecular_formula: "NaOH",
    reagent_type: "无机试剂",
    storage_requirement: "常温、干燥、密封",
    controlled_type: "腐蚀品",
  },
  {
    id: 4,
    name: "丙酮",
    cas_number: "67-64-1",
    molecular_formula: "C₃H₆O",
    reagent_type: "有机试剂",
    storage_requirement: "阴凉、避光、密封",
    controlled_type: "易燃液体",
  },
  {
    id: 5,
    name: "硫酸",
    cas_number: "7664-93-9",
    molecular_formula: "H₂SO₄",
    reagent_type: "无机试剂",
    storage_requirement: "常温、干燥、密封",
    controlled_type: "腐蚀品",
  },
  {
    id: 6,
    name: "甲醇",
    cas_number: "67-56-1",
    molecular_formula: "CH₄O",
    reagent_type: "有机试剂",
    storage_requirement: "阴凉、避光、密封",
    controlled_type: "易燃液体",
  },
];

const CONTROLLED_TYPE_STYLES: Record<string, string> = {
  "—": "bg-bg-sub text-text-muted",
  "腐蚀品": "bg-accent-orange/10 text-accent-orange",
  "易燃液体": "bg-accent-red/10 text-accent-red",
  "氧化剂": "bg-accent-blue/10 text-accent-blue",
  "有毒": "bg-accent-red/10 text-accent-red",
};

export default function ChemicalInfoPage() {
  const [search, setSearch] = useState("");
  const [chemicals, setChemicals] = useState<Chemical[]>(MOCK_CHEMICALS);

  const filtered = chemicals.filter((c) => {
    const keyword = search.trim().toLowerCase();
    return (
      !keyword ||
      c.name.toLowerCase().includes(keyword) ||
      c.cas_number.toLowerCase().includes(keyword) ||
      c.molecular_formula.toLowerCase().includes(keyword)
    );
  });

  const handleDelete = (id: number) => {
    setChemicals((prev) => prev.filter((c) => c.id !== id));
  };

  return (
    <div className="space-y-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <FlaskConical className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text-main">化学品信息管理</h1>
            <p className="text-sm text-text-sub">管理化学品基础信息库，维护化学品档案数据</p>
          </div>
        </div>
      </motion.div>

      {/* Search & Actions */}
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
            placeholder="搜索化学品名称、CAS号、分子式..."
            className="w-full rounded-lg border border-border-medium bg-white py-2 pl-10 pr-4 text-sm text-text-main placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
          />
        </div>
        <button className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white shadow-primary transition-colors hover:bg-primary-dark hover:shadow-primary-hover">
          <Plus size={16} />
          新增化学品
        </button>
      </motion.div>

      {/* Table */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-xl border border-border bg-bg-surface shadow-card overflow-hidden"
      >
        {filtered.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-bg-sub text-xs uppercase text-text-sub">
                  <th className="px-3 py-3 text-left">化学品名称</th>
                  <th className="px-3 py-3 text-left">CAS号</th>
                  <th className="px-3 py-3 text-left">分子式</th>
                  <th className="px-3 py-3 text-left">试剂类型</th>
                  <th className="px-3 py-3 text-left">存储要求</th>
                  <th className="px-3 py-3 text-left">管控类型</th>
                  <th className="px-3 py-3 text-center">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr
                    key={c.id}
                    className="border-b border-border-light hover:bg-primary-50 transition-colors"
                  >
                    <td className="px-3 py-2.5 font-medium text-text-main">{c.name}</td>
                    <td className="px-3 py-2.5 text-text-sub font-mono text-xs">{c.cas_number}</td>
                    <td className="px-3 py-2.5 text-text-sub">{c.molecular_formula}</td>
                    <td className="px-3 py-2.5">
                      <span className="rounded-full bg-bg-sub px-2 py-0.5 text-xs text-text-sub">
                        {c.reagent_type}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-text-sub">{c.storage_requirement}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          CONTROLLED_TYPE_STYLES[c.controlled_type] || "bg-bg-sub text-text-muted"
                        }`}
                      >
                        {c.controlled_type}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center justify-center gap-1">
                        <button
                          title="编辑"
                          className="flex h-7 w-7 items-center justify-center rounded-md text-text-muted hover:bg-accent-blue/10 hover:text-accent-blue transition-colors"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          title="删除"
                          onClick={() => handleDelete(c.id)}
                          className="flex h-7 w-7 items-center justify-center rounded-md text-text-muted hover:bg-accent-red/10 hover:text-accent-red transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 text-text-muted">
            <FlaskConical size={48} className="mb-3 text-text-muted/40" />
            <p className="text-sm">暂无化学品信息数据</p>
          </div>
        )}
      </motion.div>
    </div>
  );
}
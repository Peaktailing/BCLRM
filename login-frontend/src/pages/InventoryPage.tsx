import { useState } from "react";
import { motion } from "motion/react";
import { Search, Package, Filter, Download, ChevronDown, ChevronUp } from "lucide-react";
import { REAGENT_BOTTLES, type ReagentBottle } from "@/data/mock";

const STATUS_STYLES: Record<string, string> = {
  可借: "bg-accent-green/10 text-accent-green",
  已借出: "bg-accent-orange/10 text-accent-orange",
  耗尽: "bg-accent-red/10 text-accent-red",
};

export default function InventoryPage() {
  const [search, setSearch] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState({
    reagentType: "全部类型",
    purity: "全部规格",
    location: "全部位置",
    status: "全部状态",
    supplier: "全部供应商",
    expiry: "全部",
  });

  const filtered = REAGENT_BOTTLES.filter((b) => {
    const keyword = search.trim().toLowerCase();
    const matchKeyword =
      !keyword ||
      b.reagent_name.toLowerCase().includes(keyword) ||
      b.cas_number.toLowerCase().includes(keyword) ||
      String(b.bottle_number).includes(keyword);
    const matchStatus = filters.status === "全部状态" || b.status === filters.status;
    const matchSupplier = filters.supplier === "全部供应商" || b.supplier === filters.supplier;
    return matchKeyword && matchStatus && matchSupplier;
  });

  const suppliers = [...new Set(REAGENT_BOTTLES.map((b) => b.supplier))];
  const reagentTypes = ["全部类型", "无机试剂", "有机试剂", "分析试剂", "生化试剂", "标准品"];
  const purities = ["全部规格", "优级纯 (GR)", "分析纯 (AR)", "化学纯 (CP)", "实验纯 (LR)"];
  const locations = ["全部位置", "A区-易燃品柜", "B区-酸碱柜", "C区-普通试剂架", "D区-冷藏柜", "E区-毒麻品柜"];
  const statuses = ["全部状态", "可借", "已借出", "耗尽"];
  const expiryStatuses = ["全部", "正常", "即将过期", "已过期"];

  return (
    <div className="space-y-4">
      {/* Page Title */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-3"
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary">
          <Package className="h-5 w-5 text-white" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold text-text-main">实时库存</h1>
          <p className="truncate text-sm text-text-sub">查看所有试剂瓶的实时状态与剩余量</p>
        </div>
      </motion.div>

      {/* Search + Filter Panel */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="rounded-lg bg-bg-surface p-4 lg:p-5"
      >
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div className="flex-1 relative min-w-0">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="输入试剂名称、CAS号、编号进行搜索..."
              className="w-full rounded-md border border-border bg-bg-main py-2 pl-9 pr-3 text-sm text-text-main outline-none transition-colors focus:border-primary"
            />
          </div>
          <button
            className="flex items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            <Search className="h-3.5 w-3.5" />
            查询
          </button>
        </div>

        {/* Filter Toggle */}
        <div
          className="mt-3 flex cursor-pointer select-none items-center gap-1.5"
          onClick={() => setShowFilters(!showFilters)}
        >
          {showFilters ? (
            <ChevronUp className="h-3.5 w-3.5 text-text-muted" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 text-text-muted" />
          )}
          <span className="text-xs text-text-sub">展开更多筛选</span>
        </div>

        {/* Advanced Filters */}
        {showFilters && (
          <div className="mt-3 border-t border-border pt-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {[
                { label: "试剂类型", value: filters.reagentType, key: "reagentType", options: reagentTypes },
                { label: "纯度/规格", value: filters.purity, key: "purity", options: purities },
                { label: "存储位置", value: filters.location, key: "location", options: locations },
                { label: "库存状态", value: filters.status, key: "status", options: statuses },
                { label: "供应商", value: filters.supplier, key: "supplier", options: ["全部供应商", ...suppliers] },
                { label: "有效期状态", value: filters.expiry, key: "expiry", options: expiryStatuses },
              ].map((f) => (
                <div key={f.key} className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-text-sub">{f.label}</label>
                  <select
                    value={f.value}
                    onChange={(e) => setFilters({ ...filters, [f.key]: e.target.value })}
                    className="w-full rounded-md border border-border bg-bg-main px-3 py-2 text-sm text-text-main outline-none transition-colors focus:border-primary"
                  >
                    {f.options.map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
            <div className="mt-4 flex items-center gap-3">
              <button className="flex items-center gap-1.5 rounded-md bg-accent-red px-4 py-2 text-sm font-medium text-white hover:opacity-90">
                <Search className="h-3.5 w-3.5" /> 搜索
              </button>
              <button
                onClick={() => setFilters({ reagentType: "全部类型", purity: "全部规格", location: "全部位置", status: "全部状态", supplier: "全部供应商", expiry: "全部" })}
                className="flex items-center gap-1.5 rounded-md border border-border bg-bg-surface px-4 py-2 text-sm font-medium text-text-sub hover:border-primary hover:text-primary"
              >
                重置
              </button>
            </div>
          </div>
        )}
      </motion.div>

      {/* Results Summary */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex items-center justify-between"
      >
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-text-muted" />
          <span className="text-sm text-text-sub">
            共 <span className="font-semibold text-text-main">{filtered.length}</span> 条结果
          </span>
        </div>
        <button className="flex items-center gap-1 rounded-md border border-border bg-bg-surface px-3 py-1.5 text-xs font-medium text-text-sub hover:border-primary hover:text-primary">
          <Download className="h-3 w-3" />
          导出
        </button>
      </motion.div>

      {/* Results Table */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="overflow-hidden rounded-lg bg-bg-surface"
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">瓶号</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">试剂名称</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">CAS号</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">规格</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">剩余量</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">存储位置</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">状态</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">供应商</th>
                <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">入库日期</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((b) => (
                <tr key={b.id} className="hover:bg-primary-50/50">
                  <td className="whitespace-nowrap px-3 py-2.5 font-medium text-text-main">{b.bottle_number}</td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-text-main">
                    <span className="inline-flex items-center gap-1">
                      {b.reagent_name}
                      {b.is_controlled && (
                        <span title="管控试剂" className="text-accent-orange">⚠️</span>
                      )}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-text-sub">{b.cas_number || "—"}</td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-text-sub">{b.specification}</td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-text-sub">{b.quantity} {b.unit}</td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-text-sub">{b.storage_location}</td>
                  <td className="whitespace-nowrap px-3 py-2.5">
                    <span className={`inline-flex items-center justify-center rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[b.status]}`}>
                      {b.status}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-text-sub">{b.supplier}</td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-text-sub">{b.entry_date}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-3 py-12 text-center text-text-muted">
                    <Package className="mx-auto mb-2 h-8 w-8 opacity-30" />
                    没有匹配的试剂瓶
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
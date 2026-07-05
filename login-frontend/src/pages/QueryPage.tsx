import { useState } from "react";
import { motion } from "motion/react";
import {
  Search, Filter, ChevronDown, ChevronUp, Download, RotateCcw,
} from "lucide-react";
import { REAGENT_BOTTLES } from "@/data/mock";

type QueryTab = "试剂查询" | "领用记录" | "归还记录" | "操作日志";
const QUERY_TABS: QueryTab[] = ["试剂查询", "领用记录", "归还记录", "操作日志"];

const STATUS_STYLES: Record<string, string> = {
  可借: "bg-accent-green/10 text-accent-green",
  已借出: "bg-accent-orange/10 text-accent-orange",
  耗尽: "bg-text-muted/10 text-text-muted",
};

const REAGENT_TYPES = ["全部", "无机试剂", "有机试剂", "生化试剂", "标准品", "指示剂"];
const PURITY_OPTIONS = ["全部", "分析纯", "化学纯", "优级纯", "色谱纯"];
const LOCATIONS = ["全部", "A-01", "A-02", "B-01", "B-02", "C-01", "D-01", "E-01"];
const STATUS_OPTIONS = ["全部", "可借", "已借出", "耗尽"];
const SUPPLIERS = ["全部", "国药集团", "Sigma-Aldrich", "阿拉丁", "麦克林"];
const EXPIRY_OPTIONS = ["全部", "即将过期", "正常", "已过期"];

export default function QueryPage() {
  const [activeTab, setActiveTab] = useState<QueryTab>("试剂查询");
  const [search, setSearch] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState({
    reagentType: "全部",
    purity: "全部",
    location: "全部",
    status: "全部",
    supplier: "全部",
    expiry: "全部",
    dateFrom: "",
    dateTo: "",
  });

  const updateFilter = (key: string, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const resetFilters = () => {
    setFilters({
      reagentType: "全部",
      purity: "全部",
      location: "全部",
      status: "全部",
      supplier: "全部",
      expiry: "全部",
      dateFrom: "",
      dateTo: "",
    });
    setSearch("");
  };

  const filtered = REAGENT_BOTTLES.filter((b) => {
    const keyword = search.trim().toLowerCase();
    const matchKeyword =
      !keyword ||
      b.reagent_name.toLowerCase().includes(keyword) ||
      b.cas_number.toLowerCase().includes(keyword) ||
      String(b.bottle_number).includes(keyword);
    const matchStatus =
      filters.status === "全部" || b.status === filters.status;
    const matchSupplier =
      filters.supplier === "全部" || b.supplier === filters.supplier;
    return matchKeyword && matchStatus && matchSupplier;
  });

  return (
    <div className="space-y-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-cyan/10">
            <Search className="h-5 w-5 text-accent-cyan" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text-main">综合查询</h1>
            <p className="text-sm text-text-sub">查询试剂库存、领用记录与操作日志</p>
          </div>
        </div>
      </motion.div>

      {/* Query Tabs */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="flex items-center gap-1 rounded-lg bg-bg-surface p-1 border border-border w-fit"
      >
        {QUERY_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab
                ? "bg-primary text-white shadow-sm"
                : "text-text-sub hover:text-text-main"
            }`}
          >
            {tab}
          </button>
        ))}
      </motion.div>

      {/* Search Bar & Filter Toggle */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-xl border border-border bg-bg-surface p-4 shadow-card"
      >
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索试剂名称、CAS号、瓶号..."
              className="w-full rounded-lg border border-border-medium bg-white py-2 pl-10 pr-4 text-sm text-text-main placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
            />
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
              showFilters
                ? "border-primary bg-primary-50 text-primary"
                : "border-border-medium bg-white text-text-sub hover:border-primary hover:text-primary"
            }`}
          >
            <Filter size={14} />
            高级筛选
            {showFilters ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        {/* Advanced Filters */}
        {showFilters && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="mt-4 pt-4 border-t border-border"
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              <div>
                <label className="mb-1 block text-xs text-text-sub">试剂类型</label>
                <select
                  value={filters.reagentType}
                  onChange={(e) => updateFilter("reagentType", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-2.5 py-1.5 text-sm text-text-main focus:border-primary focus:outline-none"
                >
                  {REAGENT_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-text-sub">纯度/规格</label>
                <select
                  value={filters.purity}
                  onChange={(e) => updateFilter("purity", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-2.5 py-1.5 text-sm text-text-main focus:border-primary focus:outline-none"
                >
                  {PURITY_OPTIONS.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-text-sub">存储位置</label>
                <select
                  value={filters.location}
                  onChange={(e) => updateFilter("location", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-2.5 py-1.5 text-sm text-text-main focus:border-primary focus:outline-none"
                >
                  {LOCATIONS.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-text-sub">库存状态</label>
                <select
                  value={filters.status}
                  onChange={(e) => updateFilter("status", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-2.5 py-1.5 text-sm text-text-main focus:border-primary focus:outline-none"
                >
                  {STATUS_OPTIONS.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-text-sub">供应商</label>
                <select
                  value={filters.supplier}
                  onChange={(e) => updateFilter("supplier", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-2.5 py-1.5 text-sm text-text-main focus:border-primary focus:outline-none"
                >
                  {SUPPLIERS.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-text-sub">有效期状态</label>
                <select
                  value={filters.expiry}
                  onChange={(e) => updateFilter("expiry", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-2.5 py-1.5 text-sm text-text-main focus:border-primary focus:outline-none"
                >
                  {EXPIRY_OPTIONS.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-text-sub">入库日期（起）</label>
                <input
                  type="date"
                  value={filters.dateFrom}
                  onChange={(e) => updateFilter("dateFrom", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-2.5 py-1.5 text-sm text-text-main focus:border-primary focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-text-sub">入库日期（止）</label>
                <input
                  type="date"
                  value={filters.dateTo}
                  onChange={(e) => updateFilter("dateTo", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-2.5 py-1.5 text-sm text-text-main focus:border-primary focus:outline-none"
                />
              </div>
            </div>
            <div className="mt-4 flex items-center gap-3">
              <button className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white shadow-primary transition-colors hover:bg-primary-dark">
                <Search size={14} />
                查询
              </button>
              <button
                onClick={resetFilters}
                className="flex items-center gap-1.5 rounded-lg border border-border-medium bg-white px-4 py-2 text-sm font-medium text-text-sub transition-colors hover:border-primary hover:text-primary"
              >
                <RotateCcw size={14} />
                重置
              </button>
            </div>
          </motion.div>
        )}
      </motion.div>

      {/* Results */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="rounded-xl border border-border bg-bg-surface shadow-card"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <span className="text-sm text-text-sub">
            共 <span className="font-semibold text-text-main">{filtered.length}</span> 条结果
          </span>
          <button className="flex items-center gap-1.5 rounded-lg border border-border-medium bg-white px-3 py-1.5 text-sm text-text-sub transition-colors hover:border-primary hover:text-primary">
            <Download size={14} />
            导出
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-bg-sub text-xs uppercase text-text-sub">
                <th className="px-3 py-3 text-left">瓶号</th>
                <th className="px-3 py-3 text-left">试剂名称</th>
                <th className="px-3 py-3 text-left">CAS号</th>
                <th className="px-3 py-3 text-left">规格</th>
                <th className="px-3 py-3 text-left">剩余量</th>
                <th className="px-3 py-3 text-left">存储位置</th>
                <th className="px-3 py-3 text-left">状态</th>
                <th className="px-3 py-3 text-left">供应商</th>
                <th className="px-3 py-3 text-left">入库日期</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((b) => (
                <tr
                  key={b.id}
                  className="border-b border-border-light hover:bg-primary-50 transition-colors"
                >
                  <td className="px-3 py-2.5 font-medium text-text-main">{b.bottle_number}</td>
                  <td className="px-3 py-2.5 text-text-main">
                    <span className="inline-flex items-center gap-1">
                      {b.reagent_name}
                      {b.is_controlled && (
                        <span title="管控试剂" className="text-amber-500 text-xs">⚠️</span>
                      )}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-text-sub font-mono text-xs">{b.cas_number || "—"}</td>
                  <td className="px-3 py-2.5 text-text-sub">{b.specification}</td>
                  <td className="px-3 py-2.5 text-text-sub">
                    {b.quantity} {b.unit}
                  </td>
                  <td className="px-3 py-2.5 text-text-sub">{b.storage_location}</td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[b.status]}`}
                    >
                      {b.status}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-text-sub">{b.supplier}</td>
                  <td className="px-3 py-2.5 text-text-sub whitespace-nowrap">{b.entry_date}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-3 py-12 text-center text-text-muted">
                    没有匹配的查询结果
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
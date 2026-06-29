import { useState } from "react";
import { Search, Package, AlertTriangle } from "lucide-react";
import { REAGENT_BOTTLES } from "@/data/mock";

const STATUS_STYLES: Record<string, string> = {
  可借: "bg-green-100 text-green-700",
  已借出: "bg-orange-100 text-orange-700",
  耗尽: "bg-gray-100 text-gray-500",
};

const STATUS_FILTERS = ["全部", "可借", "已借出", "耗尽"] as const;

export default function InventoryPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("全部");
  const [controlledOnly, setControlledOnly] = useState(false);

  const filtered = REAGENT_BOTTLES.filter((b) => {
    const keyword = search.trim().toLowerCase();
    const matchKeyword =
      !keyword ||
      b.reagent_name.toLowerCase().includes(keyword) ||
      b.cas_number.toLowerCase().includes(keyword);
    const matchStatus = statusFilter === "全部" || b.status === statusFilter;
    const matchControlled = !controlledOnly || b.is_controlled;
    return matchKeyword && matchStatus && matchControlled;
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-text-main">📦 实时库存</h1>

      {/* 筛选栏 */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border-light bg-white p-4 shadow-card">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="按试剂名称 / CAS号搜索"
            className="rounded-lg border border-border-medium bg-white py-2 pl-10 pr-4 text-sm focus:border-primary focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-2">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
                statusFilter === s
                  ? "bg-primary text-white"
                  : "bg-bg-sub text-text-sub hover:bg-primary-50"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <button
          onClick={() => setControlledOnly(!controlledOnly)}
          className={`ml-auto flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors ${
            controlledOnly
              ? "bg-amber-100 text-amber-700"
              : "bg-bg-sub text-text-sub hover:bg-amber-50"
          }`}
        >
          <AlertTriangle size={14} />
          管控试剂
        </button>
      </div>

      {/* 数据表格 */}
      <div className="overflow-x-auto rounded-xl border border-border-light bg-white shadow-card">
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
              <th className="px-3 py-3 text-left">类型</th>
              <th className="px-3 py-3 text-left">录入人</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((b) => (
              <tr key={b.id} className="border-b border-border-light hover:bg-primary-50">
                <td className="px-3 py-2.5 font-medium text-text-main">{b.bottle_number}</td>
                <td className="px-3 py-2.5 text-text-main">
                  <span className="inline-flex items-center gap-1">
                    {b.reagent_name}
                    {b.is_controlled && (
                      <span title="管控试剂" className="text-amber-500">
                        ⚠️
                      </span>
                    )}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-text-sub">{b.cas_number || "—"}</td>
                <td className="px-3 py-2.5 text-text-sub">{b.specification}</td>
                <td className="px-3 py-2.5 text-text-sub">
                  {b.quantity} {b.unit}
                </td>
                <td className="px-3 py-2.5 text-text-sub">{b.storage_location}</td>
                <td className="px-3 py-2.5">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[b.status]}`}>
                    {b.status}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-text-sub">{b.supplier}</td>
                <td className="px-3 py-2.5">
                  {b.is_controlled ? (
                    <span className="text-amber-600">管控</span>
                  ) : (
                    <span className="text-text-sub">普通</span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-text-sub">{b.creator}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={10} className="px-3 py-8 text-center text-text-muted">
                  没有匹配的试剂瓶
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 底部统计 */}
      <div className="flex items-center gap-2 text-sm text-text-sub">
        <Package size={16} className="text-primary" />
        共 <span className="font-semibold text-text-main">{filtered.length}</span> 个试剂瓶
      </div>
    </div>
  );
}

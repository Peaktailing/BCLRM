import { useState, type FormEvent } from "react";
import { motion } from "motion/react";
import { ArrowRightLeft, Search, User, FileText, Calendar, Check, Info, Package, FlaskConical } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { REAGENT_BOTTLES, BORROW_RECORDS } from "@/data/mock";

type Tab = "borrow" | "return" | "borrow-records" | "return-records";

const STATUS_STYLES: Record<string, string> = {
  待审批: "bg-yellow-100 text-yellow-700",
  已批准: "bg-green-100 text-green-700",
  已拒绝: "bg-red-100 text-red-700",
  已归还: "bg-gray-100 text-gray-500",
};

export default function BorrowPage() {
  const { can, user } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>("borrow");
  const [searchReagent, setSearchReagent] = useState("");
  const [selectedReagent, setSelectedReagent] = useState<typeof REAGENT_BOTTLES[0] | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [borrower, setBorrower] = useState("");
  const [purpose, setPurpose] = useState("实验用");
  const [returnDate, setReturnDate] = useState("");
  const [remark, setRemark] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const borrowableBottles = REAGENT_BOTTLES.filter((b) => b.status === "可借");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!selectedReagent || quantity <= 0) return;
    setSubmitted(true);
    setTimeout(() => {
      setSubmitted(false);
      setSelectedReagent(null);
      setQuantity(1);
      setBorrower("");
      setRemark("");
    }, 3000);
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "borrow", label: "领用登记" },
    { key: "return", label: "归还登记" },
    { key: "borrow-records", label: "领用记录" },
    { key: "return-records", label: "归还记录" },
  ];

  return (
    <div className="space-y-4">
      {/* Page Title */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-3"
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary">
          <ArrowRightLeft className="h-5 w-5 text-white" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold text-text-main">领用归还</h1>
          <p className="truncate text-sm text-text-sub">试剂领用和归还操作管理</p>
        </div>
      </motion.div>

      {/* Tab Bar */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="flex items-center gap-0 overflow-x-auto border-b border-border bg-bg-surface"
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center justify-center whitespace-nowrap px-5 py-3 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? "text-primary border-b-2 border-primary"
                : "text-text-sub hover:text-text-main"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </motion.div>

      {/* Tab Content */}
      {activeTab === "borrow" && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid grid-cols-1 gap-4 lg:grid-cols-12"
        >
          {/* Left: Form */}
          <div className="lg:col-span-8 rounded-lg border border-border bg-bg-surface p-6">
            <h2 className="mb-5 flex items-center gap-1.5 text-base font-semibold text-text-main">
              <Package className="h-4.5 w-4.5" />
              领用信息
            </h2>

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Reagent Search */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-main">试剂选择</label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
                  <input
                    type="text"
                    value={searchReagent}
                    onChange={(e) => setSearchReagent(e.target.value)}
                    placeholder="搜索试剂名称或编号..."
                    className="w-full rounded-md border border-border bg-bg-main py-2 pl-9 pr-3 text-sm text-text-main outline-none transition-colors focus:border-primary"
                  />
                </div>
              </div>

              {/* Quick Pick Chips */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">常用试剂</label>
                <div className="flex flex-nowrap gap-2 overflow-x-auto">
                  {borrowableBottles.slice(0, 5).map((b) => (
                    <button
                      key={b.id}
                      type="button"
                      onClick={() => setSelectedReagent(b)}
                      className={`shrink-0 inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm whitespace-nowrap transition-colors ${
                        selectedReagent?.id === b.id
                          ? "border-primary bg-primary-50 text-primary"
                          : "border-border bg-bg-main text-text-sub hover:border-primary hover:text-primary"
                      }`}
                    >
                      <FlaskConical className="h-3.5 w-3.5" />
                      {b.reagent_name}
                    </button>
                  ))}
                </div>
              </div>

              {/* Form Grid */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-main">领用数量</label>
                  <input
                    type="number"
                    min={1}
                    value={quantity}
                    onChange={(e) => setQuantity(Number(e.target.value))}
                    className="w-full rounded-md border border-border bg-bg-main px-3 py-2 text-sm text-text-main outline-none transition-colors focus:border-primary"
                  />
                </div>
                <div>
                  <label className="mb-1.5 flex items-center gap-1 text-sm font-medium text-text-main">
                    <User className="h-3.5 w-3.5" />
                    领用人
                  </label>
                  <input
                    type="text"
                    value={borrower}
                    onChange={(e) => setBorrower(e.target.value)}
                    placeholder="输入领用人姓名"
                    className="w-full rounded-md border border-border bg-bg-main px-3 py-2 text-sm text-text-main outline-none transition-colors focus:border-primary"
                  />
                </div>
                <div>
                  <label className="mb-1.5 flex items-center gap-1 text-sm font-medium text-text-main">
                    <FileText className="h-3.5 w-3.5" />
                    用途说明
                  </label>
                  <select
                    value={purpose}
                    onChange={(e) => setPurpose(e.target.value)}
                    className="w-full rounded-md border border-border bg-bg-main px-3 py-2 text-sm text-text-main outline-none transition-colors focus:border-primary"
                  >
                    <option>实验用</option>
                    <option>检测用</option>
                    <option>教学用</option>
                    <option>科研用</option>
                    <option>其他</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1.5 flex items-center gap-1 text-sm font-medium text-text-main">
                    <Calendar className="h-3.5 w-3.5" />
                    预计归还日期
                  </label>
                  <input
                    type="date"
                    value={returnDate}
                    onChange={(e) => setReturnDate(e.target.value)}
                    className="w-full rounded-md border border-border bg-bg-main px-3 py-2 text-sm text-text-main outline-none transition-colors focus:border-primary"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-main">备注</label>
                <textarea
                  rows={2}
                  value={remark}
                  onChange={(e) => setRemark(e.target.value)}
                  placeholder="输入备注信息..."
                  className="w-full resize-none rounded-md border border-border bg-bg-main px-3 py-2 text-sm text-text-main outline-none transition-colors focus:border-primary"
                />
              </div>

              <button
                type="submit"
                disabled={!selectedReagent}
                className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                <Check className="h-4 w-4" />
                确认领用
              </button>

              {submitted && (
                <p className="rounded-md bg-accent-green/10 px-3 py-2 text-sm text-accent-green">
                  领用申请已提交成功！
                </p>
              )}
            </form>
          </div>

          {/* Right: Reagent Preview + Notice */}
          <div className="lg:col-span-4 flex flex-col gap-4">
            {selectedReagent && (
              <div className="rounded-lg border border-border bg-bg-surface p-5">
                <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-text-main">
                  <Package className="h-4 w-4" />
                  试剂预览
                </h3>
                <div className="space-y-3">
                  {[
                    { label: "名称", value: selectedReagent.reagent_name },
                    { label: "CAS", value: selectedReagent.cas_number || "—" },
                    { label: "当前库存", value: `${selectedReagent.quantity} ${selectedReagent.unit}` },
                    { label: "存储位置", value: selectedReagent.storage_location },
                    { label: "状态", value: selectedReagent.status },
                  ].map((item) => (
                    <div key={item.label}>
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-sm text-text-sub">{item.label}</span>
                        <span className={`text-sm font-medium truncate ${item.label === "状态" ? (selectedReagent.status === "可借" ? "text-accent-green" : "text-accent-red") : "text-text-main"}`}>
                          {item.value}
                        </span>
                      </div>
                      <div className="mt-2 border-t border-border" />
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="rounded-lg border border-primary/15 bg-primary/5 p-5">
              <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-primary">
                <Info className="h-4 w-4" />
                领用须知
              </h3>
              <ul className="space-y-2 text-xs text-text-sub">
                <li>• 管控化学品领用需经管理员审批</li>
                <li>• 领用后请在预计归还日期前归还</li>
                <li>• 超期未还将影响后续领用权限</li>
                <li>• 试剂瓶剩余量不足时请及时登记</li>
              </ul>
            </div>
          </div>
        </motion.div>
      )}

      {activeTab === "borrow-records" && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="overflow-hidden rounded-lg bg-bg-surface"
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">记录编号</th>
                  <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">试剂名称</th>
                  <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">借用人</th>
                  <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">数量</th>
                  <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">借出日期</th>
                  <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">状态</th>
                  <th className="text-left whitespace-nowrap px-3 py-2.5 font-medium text-xs text-text-muted border-b border-border">审批人</th>
                </tr>
              </thead>
              <tbody>
                {BORROW_RECORDS.map((r) => (
                  <tr key={r.id} className="hover:bg-primary-50/50">
                    <td className="whitespace-nowrap px-3 py-2.5 font-medium text-text-main">{r.record_number}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-text-main">{r.reagent_name}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-text-sub">{r.borrower}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-text-sub">{r.quantity}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-text-sub">{r.borrow_date}</td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[r.status]}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-text-sub">{r.approver || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}

      {(activeTab === "return" || activeTab === "return-records") && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center justify-center rounded-lg bg-bg-surface py-16 text-text-muted"
        >
          <Package className="mb-3 h-10 w-10 opacity-30" />
          <p className="text-sm">归还功能开发中，敬请期待</p>
        </motion.div>
      )}
    </div>
  );
}
import { useState, type FormEvent } from "react";
import { motion } from "motion/react";
import { Send, AlertCircle } from "lucide-react";
import { BORROW_RECORDS, REAGENT_BOTTLES } from "@/data/mock";
import { useAuth } from "@/context/AuthContext";

const STATUS_STYLES: Record<string, string> = {
  待审批: "bg-yellow-100 text-yellow-700",
  已批准: "bg-green-100 text-green-700",
  已拒绝: "bg-red-100 text-red-700",
  已归还: "bg-gray-100 text-gray-500",
};

export default function BorrowPage() {
  const { can, user } = useAuth();
  const canBorrow = can("borrow");
  const borrowableBottles = REAGENT_BOTTLES.filter((b) => b.status === "可借");

  const [bottleNumber, setBottleNumber] = useState<string>("");
  const [quantity, setQuantity] = useState<number>(1);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!bottleNumber || quantity <= 0) return;
    setSubmitted(true);
    setTimeout(() => setSubmitted(false), 3000);
    setBottleNumber("");
    setQuantity(1);
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-text-main">📤 领用归还</h1>

      {/* 权限提示 */}
      {!canBorrow && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-700"
        >
          <AlertCircle size={20} className="flex-shrink-0" />
          <p className="text-sm">
            当前角色（{user?.display_name ?? "访客"}）无发起借出权限，仅可查看借还记录。
          </p>
        </motion.div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* 左侧：借还记录 */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="rounded-xl border border-border-light bg-white p-4 shadow-card lg:col-span-3"
        >
          <h2 className="mb-3 text-lg font-semibold text-text-main">借还记录</h2>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-bg-sub text-xs uppercase text-text-sub">
                  <th className="px-3 py-2.5 text-left">记录编号</th>
                  <th className="px-3 py-2.5 text-left">试剂名称</th>
                  <th className="px-3 py-2.5 text-left">借用人</th>
                  <th className="px-3 py-2.5 text-left">数量</th>
                  <th className="px-3 py-2.5 text-left">借出日期</th>
                  <th className="px-3 py-2.5 text-left">状态</th>
                  <th className="px-3 py-2.5 text-left">审批人</th>
                </tr>
              </thead>
              <tbody>
                {BORROW_RECORDS.map((r) => (
                  <tr key={r.id} className="border-b border-border-light hover:bg-primary-50">
                    <td className="px-3 py-2.5 font-medium text-text-main">{r.record_number}</td>
                    <td className="px-3 py-2.5 text-text-main">{r.reagent_name}</td>
                    <td className="px-3 py-2.5 text-text-sub">{r.borrower}</td>
                    <td className="px-3 py-2.5 text-text-sub">{r.quantity}</td>
                    <td className="px-3 py-2.5 text-text-sub">{r.borrow_date}</td>
                    <td className="px-3 py-2.5">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[r.status]}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-text-sub">{r.approver || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>

        {/* 右侧：发起借出 */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="rounded-xl border border-border-light bg-white p-4 shadow-card lg:col-span-2"
        >
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-text-main">
            <Send size={18} className="text-primary" />
            发起借出
          </h2>
          {canBorrow ? (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm text-text-sub">选择试剂瓶</label>
                <select
                  value={bottleNumber}
                  onChange={(e) => setBottleNumber(e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none"
                >
                  <option value="">请选择可借试剂瓶</option>
                  {borrowableBottles.map((b) => (
                    <option key={b.id} value={b.bottle_number}>
                      {b.bottle_number} - {b.reagent_name}（剩余 {b.quantity}
                      {b.unit}）
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm text-text-sub">借用数量</label>
                <input
                  type="number"
                  min={1}
                  value={quantity}
                  onChange={(e) => setQuantity(Number(e.target.value))}
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none"
                />
              </div>
              <button
                type="submit"
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-white shadow-primary transition-colors hover:bg-primary-dark"
              >
                <Send size={16} />
                提交借出申请
              </button>
              {submitted && (
                <p className="rounded-lg bg-green-50 px-3 py-2 text-center text-sm text-green-700">
                  借出申请已提交，等待审批。
                </p>
              )}
            </form>
          ) : (
            <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-text-muted">
              <AlertCircle size={32} className="text-amber-400" />
              <p className="text-sm">当前角色无借出权限</p>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}

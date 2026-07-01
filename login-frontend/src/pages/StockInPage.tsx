import { useState, type FormEvent } from "react";
import { motion } from "motion/react";
import { PackageOpen, Info, CheckCircle } from "lucide-react";

const SUPPLIERS = ["国药集团", "Sigma-Aldrich", "阿拉丁", "麦克林", "百灵威", "其他"];
const STORAGE_LOCATIONS = ["A-01", "A-02", "A-03", "A-04", "B-01", "B-02", "B-03", "B-04", "B-05", "C-01", "C-02", "C-03", "D-01", "D-02", "E-01", "E-02"];
const UNITS = ["g", "mL", "L", "kg", "瓶"];
const REAGENT_TYPES = ["无机试剂", "有机试剂", "生化试剂", "标准品", "指示剂", "其他"];

export default function StockInPage() {
  const [formData, setFormData] = useState({
    reagent_name: "",
    cas_number: "",
    specification: "",
    quantity: 1,
    unit: "mL",
    supplier: "",
    storage_location: "",
    production_date: "",
    entry_date: new Date().toISOString().split("T")[0],
    purity: "",
    reagent_type: "",
    is_controlled: false,
    remark: "",
  });
  const [submitted, setSubmitted] = useState(false);

  const handleChange = (field: string, value: string | number | boolean) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setTimeout(() => setSubmitted(false), 4000);
    setFormData({
      reagent_name: "",
      cas_number: "",
      specification: "",
      quantity: 1,
      unit: "mL",
      supplier: "",
      storage_location: "",
      production_date: "",
      entry_date: new Date().toISOString().split("T")[0],
      purity: "",
      reagent_type: "",
      is_controlled: false,
      remark: "",
    });
  };

  return (
    <div className="space-y-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-3"
      >
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-green/10">
          <PackageOpen className="h-5 w-5 text-accent-green" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text-main">试剂入库</h1>
          <p className="text-sm text-text-sub">新增试剂瓶入库登记与信息录入</p>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="rounded-xl border border-border bg-bg-surface p-5 shadow-card lg:col-span-2"
        >
          <h2 className="mb-5 text-lg font-semibold text-text-main">入库信息登记</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">
                  试剂名称 <span className="text-accent-red">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.reagent_name}
                  onChange={(e) => handleChange("reagent_name", e.target.value)}
                  placeholder="请输入试剂名称"
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">CAS号</label>
                <input
                  type="text"
                  value={formData.cas_number}
                  onChange={(e) => handleChange("cas_number", e.target.value)}
                  placeholder="如 64-17-5"
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">规格</label>
                <input
                  type="text"
                  value={formData.specification}
                  onChange={(e) => handleChange("specification", e.target.value)}
                  placeholder="如 500ml / 500g"
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">纯度</label>
                <input
                  type="text"
                  value={formData.purity}
                  onChange={(e) => handleChange("purity", e.target.value)}
                  placeholder="如 分析纯 / 99.5%"
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">
                  入库数量 <span className="text-accent-red">*</span>
                </label>
                <input
                  type="number"
                  required
                  min={1}
                  value={formData.quantity}
                  onChange={(e) => handleChange("quantity", Number(e.target.value))}
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">单位</label>
                <select
                  value={formData.unit}
                  onChange={(e) => handleChange("unit", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                >
                  {UNITS.map((u) => (
                    <option key={u} value={u}>{u}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">供应商</label>
                <select
                  value={formData.supplier}
                  onChange={(e) => handleChange("supplier", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                >
                  <option value="">请选择供应商</option>
                  {SUPPLIERS.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">存储位置</label>
                <select
                  value={formData.storage_location}
                  onChange={(e) => handleChange("storage_location", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                >
                  <option value="">请选择存储位置</option>
                  {STORAGE_LOCATIONS.map((loc) => (
                    <option key={loc} value={loc}>{loc}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">试剂类型</label>
                <select
                  value={formData.reagent_type}
                  onChange={(e) => handleChange("reagent_type", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                >
                  <option value="">请选择试剂类型</option>
                  {REAGENT_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">生产日期</label>
                <input
                  type="date"
                  value={formData.production_date}
                  onChange={(e) => handleChange("production_date", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-sub">入库日期</label>
                <input
                  type="date"
                  value={formData.entry_date}
                  onChange={(e) => handleChange("entry_date", e.target.value)}
                  className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_controlled"
                checked={formData.is_controlled}
                onChange={(e) => handleChange("is_controlled", e.target.checked)}
                className="h-4 w-4 rounded border-border-medium text-primary focus:ring-primary/20"
              />
              <label htmlFor="is_controlled" className="text-sm text-text-sub cursor-pointer select-none">
                管控化学品
              </label>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-text-sub">备注</label>
              <textarea
                value={formData.remark}
                onChange={(e) => handleChange("remark", e.target.value)}
                placeholder="请输入备注信息（可选）"
                rows={3}
                className="w-full rounded-lg border border-border-medium bg-white px-3 py-2 text-sm text-text-main placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/20 resize-none"
              />
            </div>

            <button
              type="submit"
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white shadow-primary transition-all hover:bg-primary-dark hover:shadow-primary-hover"
            >
              <PackageOpen size={16} />
              确认入库
            </button>

            {submitted && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-2 rounded-lg bg-accent-green/10 px-4 py-3 text-sm text-accent-green"
              >
                <CheckCircle size={16} />
                试剂入库成功！已生成瓶号并记录入库信息。
              </motion.div>
            )}
          </form>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="rounded-xl border border-border bg-bg-surface p-5 shadow-card lg:col-span-1"
        >
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-text-main">
            <Info size={18} className="text-accent-blue" />
            入库须知
          </h2>
          <div className="space-y-3 text-sm text-text-sub">
            {[
              { title: "信息准确性", desc: "请确保试剂名称、CAS号、规格等信息准确无误，以便后续库存管理。" },
              { title: "管控化学品", desc: "管控化学品入库需额外审批，系统将自动标记并通知管理员。" },
              { title: "存储位置", desc: "请根据试剂特性选择正确的存储位置，危险品请存放于指定区域。" },
              { title: "标签打印", desc: "入库成功后系统将自动生成瓶号标签，请在瓶身粘贴对应标签。" },
              { title: "入库记录", desc: "所有入库记录将被永久保存，支持后续查询和审计追溯。" },
            ].map((item, i) => (
              <div key={i} className="rounded-lg bg-bg-sub p-3">
                <p className="font-medium text-text-main">{i + 1}. {item.title}</p>
                <p className="mt-1 text-xs">{item.desc}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
import { motion } from "motion/react";
import { ShieldCheck, FlaskConical, GraduationCap, BookOpen, Database, Users, Package, Send } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { TEST_ACCOUNTS, REAGENT_BOTTLES, BORROW_RECORDS, ROLE_LABELS, ROLE_COLORS, type Role } from "@/data/mock";

const ROLE_DESCRIPTIONS: { role: Role; icon: typeof ShieldCheck; desc: string }[] = [
  { role: "super_admin", icon: ShieldCheck, desc: "系统数据维护、用户管理、系统设置" },
  { role: "admin", icon: FlaskConical, desc: "试剂瓶管理(新增/编辑/删除)、借出审批" },
  { role: "teacher", icon: GraduationCap, desc: "查看试剂、发起借出申请" },
  { role: "student", icon: BookOpen, desc: "仅查看试剂库存" },
];

const SYSTEM_INFO = [
  { label: "系统名称", value: "试剂库管理系统" },
  { label: "版本号", value: "v2.0.0" },
  { label: "数据库类型", value: "PostgreSQL 16" },
  { label: "默认单位", value: "ml / g" },
];

export default function SettingsPage() {
  const { user } = useAuth();

  const systemStats = [
    { label: "用户总数", value: TEST_ACCOUNTS.length, icon: Users, color: "#1971c2" },
    { label: "试剂瓶总数", value: REAGENT_BOTTLES.length, icon: Package, color: "#FF6B6B" },
    { label: "借出记录数", value: BORROW_RECORDS.length, icon: Send, color: "#f59e0b" },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-text-main">⚙️ 系统设置</h1>

      {/* 系统信息 */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="rounded-xl border border-border-light bg-white p-5 shadow-card"
      >
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-text-main">
          <Database size={18} className="text-primary" />
          系统信息
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {SYSTEM_INFO.map((item) => (
            <div key={item.label} className="rounded-lg bg-bg-sub p-3">
              <p className="text-xs text-text-sub">{item.label}</p>
              <p className="mt-1 font-medium text-text-main">{item.value}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          {systemStats.map((s) => {
            const Icon = s.icon;
            return (
              <div key={s.label} className="flex items-center gap-3 rounded-lg bg-bg-sub p-3">
                <div
                  className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg"
                  style={{ backgroundColor: `${s.color}15`, color: s.color }}
                >
                  <Icon size={20} />
                </div>
                <div>
                  <p className="text-2xl font-bold text-text-main">{s.value}</p>
                  <p className="text-xs text-text-sub">{s.label}</p>
                </div>
              </div>
            );
          })}
        </div>
      </motion.div>

      {/* 角色说明 */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
        className="rounded-xl border border-border-light bg-white p-5 shadow-card"
      >
        <h2 className="mb-4 text-lg font-semibold text-text-main">角色说明</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {ROLE_DESCRIPTIONS.map((r) => {
            const Icon = r.icon;
            const color = ROLE_COLORS[r.role];
            return (
              <div key={r.role} className="rounded-xl border border-border-light bg-white p-4 shadow-card">
                <div className="mb-2 flex items-center gap-2">
                  <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
                  <Icon size={18} style={{ color }} />
                  <span className="font-medium text-text-main">{ROLE_LABELS[r.role]}</span>
                </div>
                <p className="text-sm text-text-sub">{r.desc}</p>
              </div>
            );
          })}
        </div>
      </motion.div>

      {/* 当前登录用户 */}
      {user && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
          className="rounded-xl border border-border-light bg-white p-5 shadow-card"
        >
          <h2 className="mb-4 text-lg font-semibold text-text-main">当前登录用户</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <div className="rounded-lg bg-bg-sub p-3">
              <p className="text-xs text-text-sub">用户ID</p>
              <p className="mt-1 font-medium text-text-main">{user.user_id}</p>
            </div>
            <div className="rounded-lg bg-bg-sub p-3">
              <p className="text-xs text-text-sub">工号</p>
              <p className="mt-1 font-medium text-text-main">{user.work_id}</p>
            </div>
            <div className="rounded-lg bg-bg-sub p-3">
              <p className="text-xs text-text-sub">姓名</p>
              <p className="mt-1 font-medium text-text-main">{user.display_name}</p>
            </div>
            <div className="rounded-lg bg-bg-sub p-3">
              <p className="text-xs text-text-sub">角色</p>
              <p className="mt-1 flex items-center gap-1.5 font-medium text-text-main">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: ROLE_COLORS[user.role] }}
                />
                {ROLE_LABELS[user.role]}
              </p>
            </div>
            <div className="rounded-lg bg-bg-sub p-3">
              <p className="text-xs text-text-sub">部门</p>
              <p className="mt-1 font-medium text-text-main">{user.department}</p>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}

import { useState, useEffect, type FormEvent } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  User, Lock, Eye, EyeOff, LogIn, Loader2,
  AlertCircle, CheckCircle2, XCircle, Info,
  FlaskConical, ShieldCheck, GraduationCap, BookOpen,
} from "lucide-react";
import {
  mockLogin, TEST_ACCOUNTS, ROLE_COLORS, ROLE_LABELS,
  type User as AppUser,
} from "@/data/mock";
import { useAuth } from "@/context/AuthContext";
import { useNavigate } from "react-router-dom";
import BackgroundDecor from "@/components/BackgroundDecor";

type ToastType = "success" | "error" | "info";

const TOAST_CONFIG: Record<
  ToastType,
  { color: string; bg: string; border: string; icon: typeof CheckCircle2 }
> = {
  success: { color: "#2f9e44", bg: "#ebfbee", border: "#b2f2bb", icon: CheckCircle2 },
  error: { color: "#e03131", bg: "#fff5f5", border: "#ffc9c9", icon: XCircle },
  info: { color: "#1971c2", bg: "#e7f5ff", border: "#a5d8ff", icon: Info },
};

const ROLE_HIERARCHY = [
  { role: "super_admin" as const, icon: ShieldCheck, desc: "全系统权限 · 用户与系统管理" },
  { role: "admin" as const, icon: FlaskConical, desc: "试剂录入 · 借还审批" },
  { role: "teacher" as const, icon: BookOpen, desc: "试剂领用 · 归还管理" },
  { role: "student" as const, icon: GraduationCap, desc: "库存查看 · 信息浏览" },
];

const REMEMBER_KEY = "reagent_lab_remember_work_id";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [workId, setWorkId] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [rememberId, setRememberId] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{ type: ToastType; message: string } | null>(null);

  // 恢复记住的工号
  useEffect(() => {
    const saved = localStorage.getItem(REMEMBER_KEY);
    if (saved) {
      setWorkId(saved);
      setRememberId(true);
    }
  }, []);

  // Toast 自动消失
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(timer);
  }, [toast]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setToast(null);

    if (!workId.trim() || !password) {
      setToast({ type: "error", message: "请输入工号和密码" });
      setLoading(false);
      return;
    }

    const result = await mockLogin(workId, password);
    if (result.success && result.user) {
      if (rememberId) localStorage.setItem(REMEMBER_KEY, workId.trim());
      else localStorage.removeItem(REMEMBER_KEY);
      setToast({ type: "success", message: "登录成功，正在跳转..." });
      login(result.user);
      setTimeout(() => navigate("/"), 400);
    } else {
      setToast({ type: "error", message: result.message ?? "登录失败，请重试" });
    }
    setLoading(false);
  };

  const handleQuickFill = (account: AppUser) => {
    setWorkId(account.work_id);
    setPassword(account.password);
    setToast({ type: "info", message: `已填充「${ROLE_LABELS[account.role]}」账号：${account.work_id}` });
  };

  const ToastIcon = toast ? TOAST_CONFIG[toast.type].icon : null;

  return (
    <div className="relative flex min-h-screen bg-bg-sub">
      <BackgroundDecor />

      {/* 左侧品牌区 */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-gradient-to-br from-primary to-primary-dark p-12 text-white lg:flex">
        <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-white/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -left-10 h-72 w-72 rounded-full bg-white/10 blur-3xl" />

        {/* Logo + 系统名 */}
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5 }}
          className="relative flex items-center gap-3"
        >
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/20 backdrop-blur">
            <FlaskConical className="h-6 w-6" />
          </div>
          <div>
            <div className="text-lg font-semibold tracking-wide">试剂库管理系统</div>
            <div className="text-xs text-white/70">Reagent Lab Management</div>
          </div>
        </motion.div>

        {/* 标语 + 角色层级 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15 }}
          className="relative space-y-6"
        >
          <div>
            <h1 className="text-3xl font-bold leading-tight">高效管理 / 安全可控</h1>
            <p className="mt-2 text-base text-white/80">· 数据透明 · 全流程可追溯</p>
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm text-white/70">
              <Lock className="h-3.5 w-3.5" />
              <span>四层角色权限体系</span>
            </div>
            {ROLE_HIERARCHY.map(({ role, icon: Icon, desc }, idx) => (
              <motion.div
                key={role}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.4, delay: 0.3 + idx * 0.1 }}
                className="flex items-center gap-3 rounded-xl border border-white/20 bg-white/10 p-3 backdrop-blur-sm"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/20">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium">{ROLE_LABELS[role]}</div>
                  <div className="text-xs text-white/70">{desc}</div>
                </div>
                <span
                  className="h-2.5 w-2.5 rounded-full ring-2 ring-white/30"
                  style={{ background: ROLE_COLORS[role] }}
                />
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* 底部 */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.8 }}
          className="relative text-xs text-white/50"
        >
          © 2025 试剂库管理系统 · 实验室信息化
        </motion.div>
      </div>

      {/* 右侧登录区 */}
      <div className="relative flex w-full flex-col items-center justify-center p-6 lg:w-1/2">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="w-full max-w-md"
        >
          {/* 移动端标题 */}
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-white">
              <FlaskConical className="h-5 w-5" />
            </div>
            <span className="text-lg font-semibold text-text-main">试剂库管理系统</span>
          </div>

          <div className="rounded-2xl border border-border-light bg-white p-8 shadow-card-hover">
            <div className="mb-6">
              <h2 className="text-xl font-semibold text-text-main">欢迎登录</h2>
              <p className="mt-1 text-sm text-text-sub">请使用工号和密码登录系统</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* 工号 */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-main">工号</label>
                <div className="relative">
                  <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
                  <input
                    type="text"
                    value={workId}
                    onChange={(e) => setWorkId(e.target.value)}
                    placeholder="请输入工号"
                    autoComplete="username"
                    className="w-full rounded-lg border border-border-medium bg-white py-2.5 pl-10 pr-4 text-sm text-text-main outline-none transition-colors placeholder:text-text-muted focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>
              </div>

              {/* 密码 */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-main">密码</label>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
                  <input
                    type={showPwd ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="请输入密码"
                    autoComplete="current-password"
                    className="w-full rounded-lg border border-border-medium bg-white py-2.5 pl-10 pr-10 text-sm text-text-main outline-none transition-colors placeholder:text-text-muted focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPwd((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted transition-colors hover:text-primary"
                    tabIndex={-1}
                    aria-label={showPwd ? "隐藏密码" : "显示密码"}
                  >
                    {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {/* 记住工号 */}
              <div className="flex items-center justify-between">
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={rememberId}
                    onChange={(e) => setRememberId(e.target.checked)}
                    className="h-4 w-4 rounded border-border-medium accent-[#FF6B6B]"
                  />
                  <span className="text-sm text-text-sub">记住工号</span>
                </label>
                <button type="button" className="text-sm text-primary transition-colors hover:text-primary-dark">
                  忘记密码？
                </button>
              </div>

              {/* 登录按钮 */}
              <button
                type="submit"
                disabled={loading}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-primary to-primary-dark py-2.5 text-sm font-medium text-white shadow-primary transition-all hover:shadow-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <LogIn className="h-4 w-4" />
                )}
                {loading ? "登录中..." : "登 录"}
              </button>
            </form>

            {/* 快捷测试账号 */}
            <div className="mt-6">
              <div className="mb-2 flex items-center gap-1.5 text-xs text-text-sub">
                <AlertCircle className="h-3.5 w-3.5" />
                <span>快捷测试账号（悬停查看密码，点击填充）</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {TEST_ACCOUNTS.map((account) => (
                  <button
                    key={account.user_id}
                    type="button"
                    onClick={() => handleQuickFill(account)}
                    className="group flex flex-col items-start gap-0.5 rounded-lg border border-border-light bg-white px-3 py-2 text-left transition-all hover:border-primary/40 hover:shadow-card"
                  >
                    <div className="flex w-full items-center justify-between">
                      <span className="text-sm font-medium text-text-main">{account.work_id}</span>
                      <span className="text-[10px]" style={{ color: ROLE_COLORS[account.role] }}>
                        {ROLE_LABELS[account.role]}
                      </span>
                    </div>
                    <span className="text-xs text-text-muted opacity-0 transition-opacity group-hover:opacity-100">
                      密码 {account.password}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* Toast */}
      <AnimatePresence>
        {toast && ToastIcon && (
          <motion.div
            key="toast"
            initial={{ opacity: 0, y: -24, x: "-50%" }}
            animate={{ opacity: 1, y: 0, x: "-50%" }}
            exit={{ opacity: 0, y: -24, x: "-50%" }}
            transition={{ duration: 0.25 }}
            className="fixed left-1/2 top-6 z-50 flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm shadow-card-hover"
            style={{
              color: TOAST_CONFIG[toast.type].color,
              background: TOAST_CONFIG[toast.type].bg,
              borderColor: TOAST_CONFIG[toast.type].border,
            }}
          >
            <ToastIcon className="h-4 w-4" />
            <span>{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

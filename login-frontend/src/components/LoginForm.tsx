import { useState, useEffect, type FormEvent } from "react";
import { motion, AnimatePresence } from "motion/react";
import { User, Lock, Eye, EyeOff, LogIn, Loader2, AlertCircle } from "lucide-react";
import { mockLogin, type TestAccount } from "@/data/accounts";
import Toast, { type ToastType } from "./Toast";
import QuickAccounts from "./QuickAccounts";

const STORAGE_KEY = "reagent_lab_remember_work_id";

export default function LoginForm() {
  const [workId, setWorkId] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<{ workId?: string; password?: string }>({});
  const [toast, setToast] = useState<{ message: string; type: ToastType; visible: boolean }>({
    message: "",
    type: "info",
    visible: false,
  });
  const [loggedInUser, setLoggedInUser] = useState<TestAccount | null>(null);

  // 加载记住的工号
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      setWorkId(saved);
      setRemember(true);
    }
  }, []);

  const showToast = (message: string, type: ToastType) => {
    setToast({ message, type, visible: true });
    setTimeout(() => setToast((t) => ({ ...t, visible: false })), 3000);
  };

  const validate = () => {
    const newErrors: { workId?: string; password?: string } = {};
    if (!workId.trim()) {
      newErrors.workId = "请输入工号";
    }
    if (!password.trim()) {
      newErrors.password = "请输入密码";
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    const result = await mockLogin(workId, password);
    setLoading(false);

    if (result.success && result.user) {
      if (remember) {
        localStorage.setItem(STORAGE_KEY, workId.trim());
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
      setLoggedInUser(result.user);
      showToast(`登录成功！欢迎 ${result.user.display_name}`, "success");
    } else {
      showToast(result.message || "登录失败", "error");
    }
  };

  const handleQuickSelect = (account: TestAccount) => {
    setWorkId(account.work_id);
    setPassword(account.password);
    setErrors({});
  };

  // 登录成功后的欢迎面板
  if (loggedInUser) {
    return (
      <>
        <Toast {...toast} />
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          className="space-y-6"
        >
          <div className="text-center">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
              className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full border-2"
              style={{
                borderColor: "#00d4ff",
                background: "rgba(0, 212, 255, 0.1)",
                boxShadow: "0 0 30px rgba(0, 212, 255, 0.3)",
              }}
            >
              <User size={32} className="text-lab-cyan" strokeWidth={1.5} />
            </motion.div>
            <h3 className="font-display text-2xl font-bold text-lab-text text-glow-cyan">
              {loggedInUser.display_name}
            </h3>
            <p className="mt-1 font-mono text-sm text-lab-muted">
              {loggedInUser.department}
            </p>
            <div className="mt-2 flex items-center justify-center gap-2 font-mono text-xs text-lab-muted">
              <span>工号: {loggedInUser.work_id}</span>
              <span className="text-lab-border">|</span>
              <span>角色: {loggedInUser.role}</span>
            </div>
          </div>

          <div className="rounded-lg border border-lab-border bg-lab-card p-4 backdrop-blur-sm">
            <p className="text-center font-mono text-xs text-lab-muted">
              演示模式 - 登录成功后此处将跳转至对应角色的系统主页
            </p>
          </div>

          <button
            onClick={() => {
              setLoggedInUser(null);
              setWorkId("");
              setPassword("");
            }}
            className="w-full rounded-lg border border-lab-border bg-lab-card py-2.5 font-mono text-sm text-lab-muted transition-colors hover:border-lab-cyan/50 hover:text-lab-cyan"
          >
            重新登录
          </button>
        </motion.div>
      </>
    );
  }

  return (
    <>
      <Toast {...toast} />
      <form onSubmit={handleSubmit} className="space-y-5">
        {/* 工号输入 */}
        <div>
          <label className="mb-2 flex items-center gap-1.5 font-mono text-xs text-lab-muted">
            <User size={14} strokeWidth={2} />
            工号
          </label>
          <div className="relative">
            <input
              type="text"
              value={workId}
              onChange={(e) => {
                setWorkId(e.target.value);
                if (errors.workId) setErrors((p) => ({ ...p, workId: undefined }));
              }}
              placeholder="请输入工号"
              className={`w-full rounded-lg border bg-lab-card/50 px-4 py-3 pl-11 font-mono text-sm text-lab-text placeholder:text-lab-muted/50 backdrop-blur-sm outline-none transition-all focus:bg-lab-card focus:glow-cyan ${
                errors.workId
                  ? "border-red-500/50"
                  : "border-lab-border focus:border-lab-cyan/50"
              }`}
            />
            <User
              size={16}
              className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-lab-muted"
              strokeWidth={1.5}
            />
          </div>
          <AnimatePresence>
            {errors.workId && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-1.5 flex items-center gap-1 font-mono text-xs text-red-400"
              >
                <AlertCircle size={12} />
                {errors.workId}
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        {/* 密码输入 */}
        <div>
          <label className="mb-2 flex items-center gap-1.5 font-mono text-xs text-lab-muted">
            <Lock size={14} strokeWidth={2} />
            密码
          </label>
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (errors.password) setErrors((p) => ({ ...p, password: undefined }));
              }}
              placeholder="请输入密码"
              className={`w-full rounded-lg border bg-lab-card/50 px-4 py-3 pl-11 pr-11 font-mono text-sm text-lab-text placeholder:text-lab-muted/50 backdrop-blur-sm outline-none transition-all focus:bg-lab-card focus:glow-cyan ${
                errors.password
                  ? "border-red-500/50"
                  : "border-lab-border focus:border-lab-cyan/50"
              }`}
            />
            <Lock
              size={16}
              className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-lab-muted"
              strokeWidth={1.5}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-lab-muted transition-colors hover:text-lab-cyan"
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          <AnimatePresence>
            {errors.password && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-1.5 flex items-center gap-1 font-mono text-xs text-red-400"
              >
                <AlertCircle size={12} />
                {errors.password}
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        {/* 记住工号 */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setRemember(!remember)}
            className={`flex h-4 w-4 items-center justify-center rounded border transition-colors ${
              remember
                ? "border-lab-cyan bg-lab-cyan/20"
                : "border-lab-border"
            }`}
          >
            {remember && (
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                className="h-2 w-2 rounded-sm bg-lab-cyan"
              />
            )}
          </button>
          <span className="font-mono text-xs text-lab-muted">记住工号</span>
        </div>

        {/* 登录按钮 */}
        <motion.button
          type="submit"
          disabled={loading}
          whileHover={{ scale: loading ? 1 : 1.02 }}
          whileTap={{ scale: loading ? 1 : 0.98 }}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-lab-cyan/40 bg-gradient-to-r from-lab-cyan/20 via-lab-teal/20 to-lab-cyan/20 py-3 font-display text-sm font-semibold tracking-wider text-lab-cyan backdrop-blur-sm transition-all hover:from-lab-cyan/30 hover:via-lab-teal/30 hover:to-lab-cyan/30 hover:glow-cyan-strong disabled:opacity-50"
        >
          {loading ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              <span>验证中...</span>
            </>
          ) : (
            <>
              <LogIn size={18} strokeWidth={2} />
              <span>登 录 系 统</span>
            </>
          )}
        </motion.button>
      </form>

      <QuickAccounts onSelect={handleQuickSelect} />
    </>
  );
}

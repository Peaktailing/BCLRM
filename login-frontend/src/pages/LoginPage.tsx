import { motion } from "motion/react";
import { FlaskConical, ShieldCheck, Lock, GraduationCap, BookOpen } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import MolecularBackground from "@/components/MolecularBackground";
import LoginForm from "@/components/LoginForm";

interface RoleItem {
  Icon: LucideIcon;
  label: string;
  desc: string;
  color: string;
}

const ROLE_HIERARCHY: RoleItem[] = [
  { Icon: ShieldCheck, label: "超级管理员", desc: "系统数据维护", color: "#e03131" },
  { Icon: FlaskConical, label: "管理员", desc: "试剂瓶管理 + 审批", color: "#f59e0b" },
  { Icon: GraduationCap, label: "教师", desc: "借出试剂", color: "#2f9e44" },
  { Icon: BookOpen, label: "学生", desc: "仅查看", color: "#1971c2" },
];

function RoleHierarchyItem({ item, index }: { item: RoleItem; index: number }) {
  const { Icon, label, desc, color } = item;
  return (
    <motion.div
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.4 + index * 0.1, duration: 0.3 }}
      className="flex items-center gap-3"
    >
      <div
        className="flex h-9 w-9 items-center justify-center rounded-lg"
        style={{ background: `${color}15` }}
      >
        <Icon size={18} style={{ color }} strokeWidth={2} />
      </div>
      <div>
        <span className="text-sm font-semibold" style={{ color }}>
          {label}
        </span>
        <span className="ml-2 text-xs text-text-sub">{desc}</span>
      </div>
    </motion.div>
  );
}

export default function LoginPage() {
  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-bg-sub">
      {/* 背景装饰 */}
      <MolecularBackground />

      {/* 顶部状态栏 */}
      <div className="absolute left-0 right-0 top-0 z-20 flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2 text-xs text-text-sub">
          <span className="flex h-2 w-2 rounded-full bg-green-500" />
          <span>系统在线</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-text-sub">
          <span className="flex items-center gap-1">
            <Lock size={10} /> 安全连接
          </span>
          <span className="text-border-medium">|</span>
          <span>v2.0</span>
        </div>
      </div>

      {/* 主内容区 */}
      <div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-12">
        <div className="grid w-full max-w-5xl grid-cols-1 gap-8 lg:grid-cols-2 lg:gap-12">
          {/* 左侧品牌区 */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
            className="hidden flex-col justify-center lg:flex"
          >
            {/* Logo */}
            <div className="mb-8 flex items-center gap-3">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-primary shadow-primary">
                <FlaskConical size={28} className="text-white" strokeWidth={1.5} />
              </div>
              <div>
                <h1 className="text-xl font-bold text-text-main">试剂库管理系统</h1>
                <p className="text-xs text-text-sub">Reagent Lab Management System</p>
              </div>
            </div>

            {/* 主标题 */}
            <motion.h2
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2, duration: 0.4 }}
              className="text-4xl font-bold leading-tight text-text-main"
            >
              高效管理
              <br />
              <span className="text-primary">安全可控 · 数据透明</span>
            </motion.h2>

            {/* 描述 */}
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3, duration: 0.4 }}
              className="mt-5 max-w-md text-sm leading-relaxed text-text-sub"
            >
              四层分级权限体系，从系统维护到试剂审批，
              为实验室提供安全、可控的试剂管理方案。
            </motion.p>

            {/* 角色层级展示 */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.35, duration: 0.4 }}
              className="mt-8 space-y-3"
            >
              {ROLE_HIERARCHY.map((item, i) => (
                <RoleHierarchyItem key={i} item={item} index={i} />
              ))}
            </motion.div>
          </motion.div>

          {/* 右侧登录表单区 */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
            className="flex items-center justify-center"
          >
            <div className="w-full max-w-md">
              {/* 登录卡片 */}
              <div className="rounded-2xl border border-border-light bg-white p-8 shadow-card-hover">
                {/* 移动端 Logo */}
                <div className="mb-6 flex flex-col items-center lg:hidden">
                  <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-xl bg-primary shadow-primary">
                    <FlaskConical size={28} className="text-white" strokeWidth={1.5} />
                  </div>
                  <h1 className="text-lg font-bold text-text-main">试剂库管理系统</h1>
                </div>

                {/* 标题 */}
                <div className="mb-6">
                  <motion.h2
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2, duration: 0.3 }}
                    className="text-2xl font-bold text-text-main"
                  >
                    系统登录
                  </motion.h2>
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.3, duration: 0.3 }}
                    className="mt-1 text-sm text-text-sub"
                  >
                    请输入工号和密码进行身份验证
                  </motion.p>
                </div>

                {/* 表单 */}
                <LoginForm />
              </div>

              {/* 卡片底部信息 */}
              <div className="mt-4 flex items-center justify-center gap-2 text-xs text-text-muted">
                <ShieldCheck size={12} />
                <span>所有数据传输均经过加密处理</span>
              </div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* 底部版权 */}
      <div className="absolute bottom-0 left-0 right-0 z-10 flex items-center justify-center py-4">
        <p className="text-xs text-text-muted">
          © 2026 试剂库管理系统 · 权限系统演示 v2.0
        </p>
      </div>
    </div>
  );
}

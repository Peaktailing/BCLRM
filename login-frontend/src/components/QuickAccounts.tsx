import { motion } from "motion/react";
import { TEST_ACCOUNTS, ROLE_COLORS, type TestAccount } from "@/data/accounts";
import { ShieldCheck, FlaskConical, GraduationCap, BookOpen } from "lucide-react";
import type { LucideIcon } from "lucide-react";

const ICON_MAP: Record<string, LucideIcon> = {
  super_admin: ShieldCheck,
  admin: FlaskConical,
  teacher: GraduationCap,
  student: BookOpen,
};

interface QuickAccountsProps {
  onSelect: (account: TestAccount) => void;
}

export default function QuickAccounts({ onSelect }: QuickAccountsProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="h-px flex-1 bg-border-light" />
        <span className="text-xs text-text-sub">快捷测试账号</span>
        <div className="h-px flex-1 bg-border-light" />
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {TEST_ACCOUNTS.map((account, i) => {
          const color = ROLE_COLORS[account.role];
          const Icon = ICON_MAP[account.role] ?? BookOpen;
          return (
            <motion.button
              key={account.work_id}
              type="button"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 + i * 0.05, duration: 0.25 }}
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.96 }}
              onClick={() => onSelect(account)}
              className="group relative flex flex-col items-center gap-1 rounded-lg border border-border-light bg-white px-2 py-2.5 transition-all hover:border-primary/40 hover:shadow-card"
            >
              <Icon size={18} strokeWidth={2} style={{ color }} />
              <span className="text-xs font-semibold text-text-main">
                {account.work_id}
              </span>
              <span className="text-[10px] leading-tight text-text-sub">
                {account.display_name}
              </span>
              <span
                className="absolute -top-1.5 right-1 rounded px-1 py-0.5 text-[9px] opacity-0 transition-opacity group-hover:opacity-100"
                style={{ color, background: `${color}15` }}
              >
                {account.password}
              </span>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}

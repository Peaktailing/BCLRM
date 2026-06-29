import { motion } from "motion/react";
import { TEST_ACCOUNTS, ROLE_LABELS, ROLE_COLORS, type TestAccount } from "@/data/accounts";
import { ShieldCheck, FlaskConical, GraduationCap, BookOpen } from "lucide-react";

const ICON_MAP = {
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
        <div className="h-px flex-1 bg-gradient-to-r from-transparent via-lab-border to-transparent" />
        <span className="font-mono text-xs text-lab-muted">快捷测试账号</span>
        <div className="h-px flex-1 bg-gradient-to-r from-transparent via-lab-border to-transparent" />
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {TEST_ACCOUNTS.map((account, i) => {
          const color = ROLE_COLORS[account.role];
          const Icon = ICON_MAP[account.role];
          return (
            <motion.button
              key={account.work_id}
              type="button"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 + i * 0.06, duration: 0.3 }}
              whileHover={{ scale: 1.05, y: -2 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => onSelect(account)}
              className="group relative flex flex-col items-center gap-1.5 rounded-lg border border-lab-border bg-lab-card px-2 py-2.5 backdrop-blur-sm transition-colors hover:border-transparent"
              style={{
                ["--tw-border-opacity" as string]: "1",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = `${color}60`;
                e.currentTarget.style.boxShadow = `0 0 15px ${color}30`;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "";
                e.currentTarget.style.boxShadow = "";
              }}
            >
              <Icon
                size={18}
                strokeWidth={1.8}
                style={{ color }}
              />
              <span
                className="font-mono text-xs font-medium"
                style={{ color }}
              >
                {account.work_id}
              </span>
              <span className="font-mono text-[10px] leading-tight text-lab-muted">
                {account.display_name}
              </span>
              <span
                className="absolute -top-1.5 right-1 rounded px-1 py-0.5 font-mono text-[9px] opacity-0 transition-opacity group-hover:opacity-100"
                style={{
                  color,
                  background: `${color}20`,
                }}
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

import { ROLE_LABELS, ROLE_COLORS, type Role } from "@/data/accounts";
import { ShieldCheck, FlaskConical, GraduationCap, BookOpen } from "lucide-react";

const ICON_MAP = {
  ShieldCheck,
  FlaskConical,
  GraduationCap,
  BookOpen,
};

interface RoleBadgeProps {
  role: Role;
  size?: "sm" | "md";
}

export default function RoleBadge({ role, size = "sm" }: RoleBadgeProps) {
  const color = ROLE_COLORS[role];
  const label = ROLE_LABELS[role];
  const Icon = ICON_MAP[
    role === "super_admin" ? "ShieldCheck" : role === "admin" ? "FlaskConical" : role === "teacher" ? "GraduationCap" : "BookOpen"
  ] as typeof ShieldCheck;

  const sizeClasses = size === "md" ? "px-3 py-1.5 text-sm" : "px-2 py-1 text-xs";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border ${sizeClasses} font-mono font-medium`}
      style={{
        color: color,
        borderColor: `${color}40`,
        backgroundColor: `${color}10`,
      }}
    >
      <Icon size={size === "md" ? 16 : 12} strokeWidth={2} />
      {label}
    </span>
  );
}

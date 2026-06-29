import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { FlaskConical, LayoutDashboard, Package, Send, Settings, LogOut } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { ROLE_LABELS, ROLE_COLORS } from "@/data/mock";
import { cn } from "@/lib/utils";

const menuItems = [
  { to: "/", label: "首页", icon: LayoutDashboard, perm: "view" },
  { to: "/inventory", label: "实时库存", icon: Package, perm: "view" },
  { to: "/borrow", label: "领用归还", icon: Send, perm: "borrow" },
  { to: "/settings", label: "系统设置", icon: Settings, perm: "system_settings" },
];

export default function SystemLayout() {
  const { user, can, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (!user) return null;

  const visibleItems = menuItems.filter((item) => can(item.perm));
  const currentTitle =
    menuItems.find((item) => item.to === location.pathname)?.label ?? "首页";

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const avatar = user.display_name.charAt(0);
  const roleColor = ROLE_COLORS[user.role];

  return (
    <div className="flex h-screen bg-bg-sub">
      {/* 侧边栏 */}
      <aside className="flex w-60 flex-col border-r border-border-light bg-white">
        {/* Logo 区 */}
        <div className="flex items-center gap-3 border-b border-border-light p-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-white">
            <FlaskConical className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-text-main">试剂库管理系统</div>
            <div className="truncate text-xs text-text-sub">Reagent Lab</div>
          </div>
        </div>

        {/* 导航菜单 */}
        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {visibleItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-4 py-2.5 text-sm transition-colors",
                  isActive
                    ? "bg-primary-100 text-primary font-medium"
                    : "text-text-sub hover:bg-bg-sub hover:text-text-main"
                )
              }
            >
              <item.icon className="h-4 w-4" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* 底部用户信息 */}
        <div className="border-t border-border-light p-3">
          <div className="flex items-center gap-3">
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
              style={{ background: roleColor }}
            >
              {avatar}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-text-main">{user.display_name}</div>
              <div className="truncate text-xs text-text-sub">{ROLE_LABELS[user.role]}</div>
            </div>
            <button
              onClick={handleLogout}
              title="退出登录"
              className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-primary-50 hover:text-primary"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* 主区域 */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* 顶栏 */}
        <header className="flex h-14 items-center justify-between border-b border-border-light bg-white px-6">
          <h1 className="text-base font-semibold text-text-main">{currentTitle}</h1>
          <div className="flex items-center gap-3">
            <div
              className="flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium text-white"
              style={{ background: roleColor }}
            >
              {avatar}
            </div>
            <span className="text-sm font-medium text-text-main">{user.display_name}</span>
            <span
              className="rounded-full px-2 py-0.5 text-xs font-medium"
              style={{ color: roleColor, background: `${roleColor}1a` }}
            >
              {ROLE_LABELS[user.role]}
            </span>
          </div>
        </header>

        {/* 内容区 */}
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

import { useState } from "react";
import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import {
  FlaskConical, Home, Package, PlusCircle, ArrowRightLeft,
  Search, BarChart3, ShieldAlert, Settings, FileText,
  Bell, Menu, ChevronDown, LogOut, X,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { ROLE_LABELS, ROLE_COLORS, type Role } from "@/data/mock";
import { cn } from "@/lib/utils";

type NavItem = {
  to: string;
  key: string;
  label: string;
  icon: typeof Home;
  perm: string;
};

const navItems: NavItem[] = [
  { to: "/", key: "home", label: "首页", icon: Home, perm: "view" },
  { to: "/inventory", key: "inventory", label: "实时库存", icon: Package, perm: "view" },
  { to: "/stock-in", key: "stock-in", label: "试剂入库", icon: PlusCircle, perm: "inventory_manage" },
  { to: "/borrow", key: "borrow-return", label: "领用归还", icon: ArrowRightLeft, perm: "borrow" },
  { to: "/query", key: "query", label: "综合查询", icon: Search, perm: "view" },
  { to: "/dashboard", key: "dashboard", label: "数据看板", icon: BarChart3, perm: "view" },
  { to: "/chemical-info", key: "chemical-info", label: "化学品信息", icon: FlaskConical, perm: "view" },
  { to: "/controlled-list", key: "controlled-list", label: "管控化学品目录", icon: ShieldAlert, perm: "view" },
  { to: "/settings", key: "settings", label: "系统设置", icon: Settings, perm: "system_settings" },
];

export default function SystemLayout() {
  const { user, can, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

  if (!user) return null;

  const visibleItems = navItems.filter((item) => can(item.perm));
  const currentItem = navItems.find((item) => {
    if (item.to === "/") return location.pathname === "/";
    return location.pathname.startsWith(item.to);
  });
  const currentTitle = currentItem?.label ?? "首页";

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const avatar = user.display_name.charAt(0);
  const roleColor = ROLE_COLORS[user.role];
  const roleLabel = ROLE_LABELS[user.role];

  return (
    <div className="flex h-screen overflow-hidden bg-bg-main">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed left-0 top-0 z-50 flex h-full w-60 flex-col bg-bg-sidebar transition-transform duration-200 lg:static lg:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 border-b border-white/10 px-5 py-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary">
            <FlaskConical className="h-4.5 w-4.5 text-white" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-base font-semibold tracking-wide text-white">
              BCLRM
            </div>
            <div className="truncate text-xs text-slate-400">试剂库管理系统</div>
          </div>
          <button
            className="ml-auto lg:hidden text-slate-400 hover:text-white"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          <ul className="flex flex-col gap-0.5">
            {visibleItems.map((item) => {
              const isActive =
                item.to === "/"
                  ? location.pathname === "/"
                  : location.pathname.startsWith(item.to);
              const Icon = item.icon;
              return (
                <li key={item.key}>
                  <NavLink
                    to={item.to}
                    onClick={() => setSidebarOpen(false)}
                    className={cn(
                      "group flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors duration-150",
                      isActive
                        ? "border-l-[3px] border-primary bg-white/10 text-white"
                        : "border-l-[3px] border-transparent text-slate-400 hover:bg-white/5"
                    )}
                  >
                    <Icon className="h-5 w-5 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Version */}
        <div className="border-t border-white/10 px-5 py-3">
          <span className="text-xs text-slate-500">v2.0.0</span>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-bg-surface px-4 lg:px-6">
          {/* Left: Hamburger + Breadcrumb */}
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <button
              className="lg:hidden flex h-9 w-9 items-center justify-center rounded-md text-text-sub hover:bg-bg-main"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </button>
            <nav className="hidden sm:flex items-center gap-1.5 min-w-0 text-sm text-text-sub">
              <Home className="h-3.5 w-3.5" />
              <span className="text-text-muted">/</span>
              <span className="truncate text-text-main">{currentTitle}</span>
            </nav>
          </div>

          {/* Right: Notification + User */}
          <div className="flex items-center gap-4 shrink-0">
            {/* Notification */}
            <button className="relative flex h-9 w-9 items-center justify-center rounded-md text-text-sub hover:bg-bg-main">
              <Bell className="h-5 w-5" />
              <span className="absolute right-1.5 top-1.5 flex h-2 w-2 rounded-full bg-primary ring-2 ring-white" />
            </button>

            {/* User */}
            <div className="relative">
              <button
                className="flex items-center gap-2 rounded-md px-2 py-1 hover:bg-bg-main"
                onClick={() => setShowUserMenu(!showUserMenu)}
              >
                <div
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white"
                  style={{ backgroundColor: roleColor }}
                >
                  {avatar}
                </div>
                <span className="hidden sm:inline truncate text-sm text-text-main">
                  {user.display_name}
                </span>
                <ChevronDown className="hidden sm:inline h-4 w-4 text-text-muted" />
              </button>

              {showUserMenu && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setShowUserMenu(false)} />
                  <div className="absolute right-0 top-full z-20 mt-1 w-48 rounded-lg border border-border bg-bg-surface py-1 shadow-lg">
                    <div className="border-b border-border px-3 py-2">
                      <div className="text-sm font-medium text-text-main">{user.display_name}</div>
                      <div className="text-xs text-text-sub">{roleLabel}</div>
                    </div>
                    <button
                      onClick={() => { handleLogout(); setShowUserMenu(false); }}
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm text-text-sub hover:bg-bg-main"
                    >
                      <LogOut className="h-4 w-4" />
                      退出登录
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-3 lg:p-5">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
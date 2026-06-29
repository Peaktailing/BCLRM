/** 测试账号数据 - 与 permission_demo 种子数据一致 */

export type Role = "super_admin" | "admin" | "teacher" | "student";

export interface TestAccount {
  work_id: string;
  password: string;
  role: Role;
  display_name: string;
  department: string;
  user_id: string;
}

export const ROLE_LABELS: Record<Role, string> = {
  super_admin: "超级管理员",
  admin: "管理员",
  teacher: "教师",
  student: "学生",
};

export const ROLE_COLORS: Record<Role, string> = {
  super_admin: "#ef4444",
  admin: "#f59e0b",
  teacher: "#14b8a6",
  student: "#3b82f6",
};

export const ROLE_ICONS: Record<Role, string> = {
  super_admin: "ShieldCheck",
  admin: "FlaskConical",
  teacher: "GraduationCap",
  student: "BookOpen",
};

export const TEST_ACCOUNTS: TestAccount[] = [
  { user_id: "SA001", work_id: "root", password: "admin123", role: "super_admin", display_name: "系统管理员", department: "系统管理部" },
  { user_id: "AD001", work_id: "zhang", password: "123456", role: "admin", display_name: "张管理", department: "化学实验室" },
  { user_id: "AD002", work_id: "li", password: "123456", role: "admin", display_name: "李管理", department: "生物实验室" },
  { user_id: "TE001", work_id: "wang", password: "123456", role: "teacher", display_name: "王教授", department: "化学系" },
  { user_id: "TE002", work_id: "zhao", password: "123456", role: "teacher", display_name: "赵教授", department: "生物系" },
  { user_id: "ST001", work_id: "stu1", password: "123456", role: "student", display_name: "小学生", department: "化学系" },
  { user_id: "ST002", work_id: "stu2", password: "123456", role: "student", display_name: "中学生", department: "生物系" },
];

export interface LoginResult {
  success: boolean;
  user?: TestAccount;
  message?: string;
}

/** 模拟登录验证 */
export function mockLogin(workId: string, password: string): Promise<LoginResult> {
  return new Promise((resolve) => {
    setTimeout(() => {
      const account = TEST_ACCOUNTS.find(
        (a) => a.work_id === workId.trim() && a.password === password,
      );
      if (account) {
        resolve({ success: true, user: account });
      } else {
        resolve({ success: false, message: "工号或密码错误，请重试" });
      }
    }, 800);
  });
}

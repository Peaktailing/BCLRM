/** 系统数据层 - 账号、试剂瓶、借还记录的 mock 数据 */

export type Role = "super_admin" | "admin" | "teacher" | "student";

export interface User {
  user_id: string;
  work_id: string;
  password: string;
  role: Role;
  display_name: string;
  department: string;
}

export interface ReagentBottle {
  id: number;
  bottle_number: number;
  reagent_name: string;
  cas_number: string;
  specification: string;
  quantity: number;
  unit: string;
  storage_location: string;
  status: "可借" | "已借出" | "耗尽";
  supplier: string;
  is_controlled: boolean;
  entry_date: string;
  creator: string;
}

export interface BorrowRecord {
  id: number;
  record_number: string;
  bottle_number: number;
  reagent_name: string;
  borrower: string;
  quantity: number;
  borrow_date: string;
  status: "待审批" | "已批准" | "已拒绝" | "已归还";
  approver: string;
  approve_date: string;
}

export const ROLE_LABELS: Record<Role, string> = {
  super_admin: "超级管理员",
  admin: "管理员",
  teacher: "教师",
  student: "学生",
};

export const ROLE_COLORS: Record<Role, string> = {
  super_admin: "#e03131",
  admin: "#f59e0b",
  teacher: "#2f9e44",
  student: "#1971c2",
};

export const TEST_ACCOUNTS: User[] = [
  { user_id: "SA001", work_id: "root", password: "admin123", role: "super_admin", display_name: "系统管理员", department: "系统管理部" },
  { user_id: "AD001", work_id: "zhang", password: "123456", role: "admin", display_name: "张管理", department: "化学实验室" },
  { user_id: "AD002", work_id: "li", password: "123456", role: "admin", display_name: "李管理", department: "生物实验室" },
  { user_id: "TE001", work_id: "wang", password: "123456", role: "teacher", display_name: "王教授", department: "化学系" },
  { user_id: "TE002", work_id: "zhao", password: "123456", role: "teacher", display_name: "赵教授", department: "生物系" },
  { user_id: "ST001", work_id: "stu1", password: "123456", role: "student", display_name: "小学生", department: "化学系" },
  { user_id: "ST002", work_id: "stu2", password: "123456", role: "student", display_name: "中学生", department: "生物系" },
];

export const REAGENT_BOTTLES: ReagentBottle[] = [
  { id: 1, bottle_number: 1001, reagent_name: "无水乙醇", cas_number: "64-17-5", specification: "500ml", quantity: 350, unit: "ml", storage_location: "A-01", status: "可借", supplier: "国药集团", is_controlled: false, entry_date: "2025-03-15", creator: "张管理" },
  { id: 2, bottle_number: 1002, reagent_name: "浓盐酸", cas_number: "7647-01-0", specification: "500ml", quantity: 420, unit: "ml", storage_location: "B-02", status: "可借", supplier: "Sigma-Aldrich", is_controlled: true, entry_date: "2025-03-20", creator: "张管理" },
  { id: 3, bottle_number: 1003, reagent_name: "氢氧化钠", cas_number: "1310-73-2", specification: "500g", quantity: 480, unit: "g", storage_location: "C-03", status: "可借", supplier: "国药集团", is_controlled: false, entry_date: "2025-04-01", creator: "李管理" },
  { id: 4, bottle_number: 1004, reagent_name: "丙酮", cas_number: "67-64-1", specification: "500ml", quantity: 0, unit: "ml", storage_location: "A-04", status: "耗尽", supplier: "Sigma-Aldrich", is_controlled: true, entry_date: "2025-02-10", creator: "李管理" },
  { id: 5, bottle_number: 1005, reagent_name: "硫酸", cas_number: "7664-93-9", specification: "500ml", quantity: 250, unit: "ml", storage_location: "B-05", status: "已借出", supplier: "国药集团", is_controlled: true, entry_date: "2025-03-25", creator: "张管理" },
  { id: 6, bottle_number: 1006, reagent_name: "去离子水", cas_number: "", specification: "5L", quantity: 4800, unit: "ml", storage_location: "D-06", status: "可借", supplier: "实验室自制", is_controlled: false, entry_date: "2025-05-01", creator: "李管理" },
  { id: 7, bottle_number: 1007, reagent_name: "甲醇", cas_number: "67-56-1", specification: "500ml", quantity: 180, unit: "ml", storage_location: "A-07", status: "可借", supplier: "Sigma-Aldrich", is_controlled: true, entry_date: "2025-04-15", creator: "张管理" },
  { id: 8, bottle_number: 1008, reagent_name: "氯化钠", cas_number: "7647-14-5", specification: "500g", quantity: 500, unit: "g", storage_location: "C-08", status: "可借", supplier: "国药集团", is_controlled: false, entry_date: "2025-05-10", creator: "李管理" },
  { id: 9, bottle_number: 1009, reagent_name: "乙酸乙酯", cas_number: "141-78-6", specification: "1L", quantity: 800, unit: "ml", storage_location: "A-09", status: "可借", supplier: "国药集团", is_controlled: false, entry_date: "2025-05-20", creator: "张管理" },
  { id: 10, bottle_number: 1010, reagent_name: "硝酸银", cas_number: "7761-88-8", specification: "100g", quantity: 50, unit: "g", storage_location: "E-10", status: "可借", supplier: "Sigma-Aldrich", is_controlled: true, entry_date: "2025-06-01", creator: "李管理" },
];

export const BORROW_RECORDS: BorrowRecord[] = [
  { id: 1, record_number: "BR20250601001", bottle_number: 1005, reagent_name: "硫酸", borrower: "王教授", quantity: 250, borrow_date: "2025-06-01", status: "已批准", approver: "张管理", approve_date: "2025-06-01" },
  { id: 2, record_number: "BR20250615002", bottle_number: 1002, reagent_name: "浓盐酸", borrower: "赵教授", quantity: 80, borrow_date: "2025-06-15", status: "待审批", approver: "", approve_date: "" },
  { id: 3, record_number: "BR20250620003", bottle_number: 1007, reagent_name: "甲醇", borrower: "王教授", quantity: 50, borrow_date: "2025-06-20", status: "待审批", approver: "", approve_date: "" },
  { id: 4, record_number: "BR20250625004", bottle_number: 1001, reagent_name: "无水乙醇", borrower: "赵教授", quantity: 150, borrow_date: "2025-06-25", status: "已批准", approver: "张管理", approve_date: "2025-06-25" },
  { id: 5, record_number: "BR20250628005", bottle_number: 1003, reagent_name: "氢氧化钠", borrower: "王教授", quantity: 20, borrow_date: "2025-06-28", status: "已归还", approver: "李管理", approve_date: "2025-06-28" },
];

export function mockLogin(workId: string, password: string): Promise<{ success: boolean; user?: User; message?: string }> {
  return new Promise((resolve) => {
    setTimeout(() => {
      const account = TEST_ACCOUNTS.find((a) => a.work_id === workId.trim() && a.password === password);
      if (account) resolve({ success: true, user: account });
      else resolve({ success: false, message: "工号或密码错误，请重试" });
    }, 600);
  });
}

export function getInventoryStats() {
  const total = REAGENT_BOTTLES.length;
  const borrowable = REAGENT_BOTTLES.filter((b) => b.status === "可借").length;
  const exhausted = REAGENT_BOTTLES.filter((b) => b.status === "耗尽").length;
  const borrowed = REAGENT_BOTTLES.filter((b) => b.status === "已借出").length;
  const totalQuantity = REAGENT_BOTTLES.reduce((sum, b) => sum + b.quantity, 0);
  const pending = BORROW_RECORDS.filter((r) => r.status === "待审批").length;
  return { total, borrowable, exhausted, borrowed, totalQuantity, pending };
}

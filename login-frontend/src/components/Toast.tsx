import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2, XCircle, Info } from "lucide-react";

export type ToastType = "success" | "error" | "info";

interface ToastProps {
  message: string;
  type: ToastType;
  visible: boolean;
}

const TOAST_CONFIG: Record<
  ToastType,
  { icon: typeof CheckCircle2; color: string; bg: string; border: string }
> = {
  success: {
    icon: CheckCircle2,
    color: "#00d4ff",
    bg: "rgba(0, 212, 255, 0.1)",
    border: "rgba(0, 212, 255, 0.3)",
  },
  error: {
    icon: XCircle,
    color: "#ef4444",
    bg: "rgba(239, 68, 68, 0.1)",
    border: "rgba(239, 68, 68, 0.3)",
  },
  info: {
    icon: Info,
    color: "#14b8a6",
    bg: "rgba(20, 184, 166, 0.1)",
    border: "rgba(20, 184, 166, 0.3)",
  },
};

export default function Toast({ message, type, visible }: ToastProps) {
  const config = TOAST_CONFIG[type];
  const Icon = config.icon;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: -20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -10, scale: 0.95 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="fixed left-1/2 top-8 z-50 -translate-x-1/2"
        >
          <div
            className="flex items-center gap-3 rounded-lg border px-5 py-3 backdrop-blur-md"
            style={{
              background: config.bg,
              borderColor: config.border,
              boxShadow: `0 0 20px ${config.border}`,
            }}
          >
            <Icon size={20} style={{ color: config.color }} strokeWidth={2} />
            <span
              className="font-mono text-sm font-medium"
              style={{ color: config.color }}
            >
              {message}
            </span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

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
    color: "#2f9e44",
    bg: "#ebfbee",
    border: "#b2f2bb",
  },
  error: {
    icon: XCircle,
    color: "#e03131",
    bg: "#fff5f5",
    border: "#ffc9c9",
  },
  info: {
    icon: Info,
    color: "#1971c2",
    bg: "#e7f5ff",
    border: "#a5d8ff",
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
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="fixed left-1/2 top-6 z-50 -translate-x-1/2"
        >
          <div
            className="flex items-center gap-2.5 rounded-lg border px-4 py-3 shadow-card"
            style={{ background: config.bg, borderColor: config.border }}
          >
            <Icon size={18} style={{ color: config.color }} strokeWidth={2} />
            <span className="text-sm font-medium" style={{ color: config.color }}>
              {message}
            </span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

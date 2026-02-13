import { motion } from 'framer-motion';

export function ThinkingDots({ agent, status }: { agent: string; status: string }) {
  return (
    <motion.div
      className="flex items-center gap-3 px-3 py-2"
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2 }}
    >
      <div className="flex gap-1">
        <div
          className="animate-bounce h-1.5 w-1.5 rounded-full bg-brand"
          style={{ animationDelay: '0ms' }}
        />
        <div
          className="animate-bounce h-1.5 w-1.5 rounded-full bg-brand"
          style={{ animationDelay: '150ms' }}
        />
        <div
          className="animate-bounce h-1.5 w-1.5 rounded-full bg-brand"
          style={{ animationDelay: '300ms' }}
        />
      </div>
      <span className="text-xs text-text-secondary">
        {agent} — {status}
      </span>
    </motion.div>
  );
}

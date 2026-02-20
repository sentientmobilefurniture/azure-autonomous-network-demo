import { motion } from 'framer-motion';

export function ThinkingIndicator() {
  return (
    <motion.div
      className="flex items-center gap-3 px-3 py-2"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
    >
      <div className="flex gap-1">
        <div
          className="h-1.5 w-1.5 rounded-full bg-brand animate-bounce"
          style={{ animationDelay: '0ms' }}
        />
        <div
          className="h-1.5 w-1.5 rounded-full bg-brand animate-bounce"
          style={{ animationDelay: '150ms' }}
        />
        <div
          className="h-1.5 w-1.5 rounded-full bg-brand animate-bounce"
          style={{ animationDelay: '300ms' }}
        />
      </div>
      <span className="text-xs text-text-secondary">Thinking...</span>
    </motion.div>
  );
}

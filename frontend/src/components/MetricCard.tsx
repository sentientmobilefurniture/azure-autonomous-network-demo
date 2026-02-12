import { motion } from 'framer-motion';

interface MetricCardProps {
  label: string;
  value: string;
  colorClass: string;
  delta?: string;
  deltaColor?: string;
}

export function MetricCard({ label, value, colorClass, delta, deltaColor }: MetricCardProps) {
  return (
    <motion.div
      className="glass-card p-3 h-full flex flex-col justify-between"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
    >
      <span className="text-[10px] uppercase tracking-wider font-medium text-text-muted">
        {label}
      </span>
      <span className={`text-2xl font-bold ${colorClass} mt-1`}>{value}</span>
      {delta && (
        <span className={`text-[10px] mt-1 ${deltaColor ?? 'text-text-muted'}`}>
          {delta}
        </span>
      )}
    </motion.div>
  );
}

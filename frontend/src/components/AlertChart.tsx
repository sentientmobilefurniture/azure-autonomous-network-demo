import { motion } from 'framer-motion';

export function AlertChart() {
  return (
    <motion.div
      className="glass-card p-3 h-full relative overflow-hidden flex items-center"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut', delay: 0.15 }}
    >
      <img
        src="/images/link-telemetry-anomalies.png"
        alt="LinkTelemetry anomaly detection chart"
        className="w-full h-full object-cover rounded-lg opacity-90"
      />
      <div className="absolute bottom-2 left-3 bg-black/60 px-2 py-0.5 rounded text-[10px] text-text-muted">
        LinkTelemetry · 231 anomalies
      </div>
    </motion.div>
  );
}

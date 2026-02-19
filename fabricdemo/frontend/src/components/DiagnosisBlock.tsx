import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';

interface DiagnosisBlockProps {
  text: string;
  expanded: boolean;
  onToggle: () => void;
}

export function DiagnosisBlock({ text, expanded, onToggle }: DiagnosisBlockProps) {
  return (
    <div className="mt-3">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-xs font-medium text-text-muted
                   hover:text-text-primary transition-colors mb-1"
      >
        <span>{expanded ? '▾' : '▸'}</span>
        <span>Diagnosis</span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="prose prose-sm max-w-none bg-neutral-bg3 rounded-lg p-3">
              <ReactMarkdown>{text}</ReactMarkdown>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';

interface DiagnosisBlockProps {
  text: string;
}

export function DiagnosisBlock({ text }: DiagnosisBlockProps) {
  const [expanded, setExpanded] = useState(true); // auto-expand

  return (
    <div className="glass-card overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium
                   text-text-muted hover:text-text-primary transition-colors"
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
            <div className="prose prose-sm max-w-none px-3 pb-3">
              <ReactMarkdown>{text}</ReactMarkdown>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

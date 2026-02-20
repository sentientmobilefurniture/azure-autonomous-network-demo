import ReactMarkdown from 'react-markdown';

interface StreamingTextProps {
  text: string;
}

export function StreamingText({ text }: StreamingTextProps) {
  return (
    <div className="glass-card overflow-hidden">
      <div className="px-3 py-2 text-xs font-medium text-text-muted">
        Diagnosis
      </div>
      <div className="prose prose-sm max-w-none px-3 pb-3">
        <ReactMarkdown>{text}</ReactMarkdown>
        <span className="inline-block w-2 h-4 bg-brand animate-pulse ml-0.5 align-text-bottom rounded-sm" />
      </div>
    </div>
  );
}

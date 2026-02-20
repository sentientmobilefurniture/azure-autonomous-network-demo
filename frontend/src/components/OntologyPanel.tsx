import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function OntologyPanel() {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/config/ontology')
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .then((data) => setMarkdown(data.markdown))
      .catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="h-full w-full flex items-center justify-center text-red-400 text-sm">
        Failed to load ontology: {error}
      </div>
    );
  }

  if (markdown === null) {
    return (
      <div className="h-full w-full flex items-center justify-center text-text-muted text-sm">
        Loading ontology…
      </div>
    );
  }

  return (
    <div className="h-full w-full overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto prose prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      </div>
    </div>
  );
}

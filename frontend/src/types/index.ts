export interface StepEvent {
  step: number;
  agent: string;
  duration?: string;
  query?: string;
  response?: string;
  error?: boolean;
}

export interface ThinkingState {
  agent: string;
  status: string;
}

export interface RunMeta {
  steps: number;
  time: string;
}
